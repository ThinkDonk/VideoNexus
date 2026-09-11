# VideoNexus — GB28181 视频监管门户

一个面向多租户的最小视频监管门户：用户经 HTTPS 登录后，**只能访问被授权的摄像头通道**，可实时预览（动态水印）、按时间段回放录像、发起录像下载。视频能力（信令、拉流、转协议）完全复用现有 **WVP + ZLM**，门户自身只负责**账号、授权、审计、下载编排**，WVP 保持原样、仅内网访问。

## 架构

```
用户浏览器（公网唯一入口 443）
        │
      Nginx（portal-web 容器）
      ├── /            → Vue3 SPA
      ├── /api/        → 门户后端 FastAPI（portal-backend 容器）
      ├── /stream/     → ZLM（auth_request 鉴权后反代，ws-flv / hls）
      └── /protected-download/ → 录像文件 X-Accel 限速内部下发
        │
   门户后端（SQLite → MySQL，/data 卷）
   └── WvpClient（api-key → 内网 WVP REST）
        │ 内网
   WVP ── ZLM
```

核心设计：

- **通道级数据权限**：用户↔通道授权表（实时/回放/下载三开关 + 有效期），所有视频操作在服务端校验，不依赖前端隐藏
- **播放地址签名**：门户签发短时效 token 且绑定登录会话，Nginx `auth_request` 逐请求校验；RTP 流原始地址永不下发；鉴权失败记审计（可用于发现地址外泄）
- **下载为异步任务**：调用 WVP 倍速下载 → 轮询进度 → 从 ZLM 拉取 MP4 落盘 → 限时限速下发 → 到期自动清理
- **审计只追加**：登录、播放、回放、下载、授权变更、账号管理全程留痕，可按条件检索并导出 CSV
- **设备能力自适应**：例如设备不支持回放暂停/恢复时自动标记，前端置灰相应按钮

## 目录结构

```
backend/    FastAPI 后端（账号/授权/审计/播放/回放/下载编排 + WVP 客户端）
frontend/   Vue3 前端（实时预览/回放/下载/管理端，Jessibuca 播放器本地 vendor）
deploy/     docker compose 编排、Dockerfile、nginx 模板、备份脚本、部署文档
scripts/    第 0 期 WVP API 验证脚本（对接现网前先跑一遍）
```

## 快速开始

### 0）对接前验证（建议先做）

复制 `scripts/wvp_config.example.json` 为 `wvp_config.json` 并填入 WVP/ZLM 地址与密钥，按 [scripts/README.md](./scripts/README.md) 逐项验证：api-key 认证、通道列表、点播取流、录像查询、回放控制、下载落盘，以及摄像头的编码格式与播放性能。

### 1）本地开发（无需 Docker）

```bash
# 后端（Python 3.12）
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Linux/macOS: .venv/bin/pip
cp ../deploy/.env.example .env                        # 按需修改；本地开发设 DEV_STREAM_PROXY=true
.venv/Scripts/python -m uvicorn app.main:app --port 9000

# 前端（Node 22）
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 与 /stream 已代理到 127.0.0.1:9000
```

本地无 Nginx 时，设 `DEV_STREAM_PROXY=true` 让后端承担 `/stream/` 的鉴权与转发（与生产 Nginx 使用同一套鉴权逻辑，见 `backend/app/services/stream_auth.py`）。

首次启动自动创建管理员（`INITIAL_ADMIN_USERNAME`，默认 admin），首次登录强制修改密码。

### 2）后端测试

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -q    # 含越权矩阵
```

### 3）生产部署（Docker Compose）

见 [deploy/README.md](./deploy/README.md)：填好 `.env`（WVP/ZLM 地址、密钥）→ 放置 TLS 证书 → `docker compose build && docker compose up -d`。公网只需开放 443，WVP/ZLM 保持内网。

## 关键配置速查

| 环境变量 | 说明 |
|---|---|
| `WVP_BASE_URL` / `WVP_API_KEY` | WVP 地址与 API Key（优先；留空则用账号密码自动重登） |
| `ZLM_UPSTREAM` | ZLM HTTP 入口（compose/nginx 反代播放流用） |
| `JWT_SECRET` | 会话签名密钥，生产必填（`openssl rand -hex 48`） |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码（首启后立即修改） |
| `DOWNLOAD_MAX_DURATION_HOURS` / `FILE_RETENTION_DAYS` | 单次下载时段上限 / 文件保留天数 |
| `DEV_STREAM_PROXY` | 本地开发用：由后端承担流鉴权与转发（生产为 false，交给 Nginx） |

完整清单见 [deploy/.env.example](./deploy/.env.example)。

## 技术栈

- 后端：Python 3.12 · FastAPI · SQLAlchemy 2(async) · Alembic · APScheduler · SQLite（可切 MySQL）
- 前端：Vue 3 · Vite · Element Plus · Pinia · Jessibuca（ws-flv，本地 vendor）
- 部署：Docker Compose · Nginx（TLS / 限流 / auth_request / X-Accel 限速）

## 许可

[Apache License 2.0](./LICENSE)
