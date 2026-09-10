# =============================================================================
# VideoNexus 后端镜像：FastAPI + SQLite（python:3.12-slim）
# -----------------------------------------------------------------------------
# 构建上下文 = 仓库根（见 deploy/docker-compose.yml），因此 COPY 路径以仓库根为
# 基准：backend/xxx、deploy/xxx。在 deploy/ 目录执行：
#   docker compose build portal-backend
# =============================================================================
FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1

WORKDIR /app

# tzdata：后端 zoneinfo 解析 Asia/Shanghai（app/core/timezone.py）依赖系统时区库，
# slim 基础镜像不带，必须安装
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# 先拷依赖清单再安装，最大化利用 Docker 层缓存（代码变动不触发重装依赖）
COPY backend/requirements.txt ./requirements.txt
# 默认走官方 PyPI；国内网络可改用清华镜像（去掉下一行注释并注释掉再下一行）：
# RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码与 alembic 迁移脚本（entrypoint 启动时执行 alembic upgrade head）
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/pytest.ini ./pytest.ini

# 入口脚本：alembic 迁移 -> 前台启动 uvicorn
COPY deploy/backend-entrypoint.sh /usr/local/bin/entrypoint.sh
# 防御：Windows 检出可能带来 CRLF（\r 会让 /bin/sh 报 “no such file or directory”）
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 9000

# 镜像级健康检查；deploy/docker-compose.yml 中同名配置会覆盖此处的参数，
# 两处保持一致（端点为 app/api/internal.py 的 /internal/health）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD ["python", "-c", "import urllib.request;urllib.request.urlopen('http://localhost:9000/internal/health', timeout=3)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
