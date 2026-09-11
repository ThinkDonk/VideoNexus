#!/bin/sh
# =============================================================================
# 后端容器入口：先执行数据库迁移（alembic），再前台启动 uvicorn。
# 环境变量由 deploy/docker-compose.yml 注入（来源 deploy/.env）。
# =============================================================================
set -e

cd /app

echo "[entrypoint] applying database migrations (alembic upgrade head) ..."
alembic upgrade head

echo "[entrypoint] starting uvicorn on 0.0.0.0:9000 ..."
# --proxy-headers + forwarded-allow-ips：信任 nginx 传来的 X-Forwarded-*，
# 使后端取到真实客户端 IP（审计日志/登录锁定均依赖）
exec uvicorn app.main:app --host 0.0.0.0 --port 9000 --proxy-headers --forwarded-allow-ips='*'
