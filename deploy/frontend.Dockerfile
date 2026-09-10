# =============================================================================
# VideoNexus 前端镜像（多阶段构建）：node 构建 Vite 产物 -> nginx 1.27 托管
# -----------------------------------------------------------------------------
# 前提：仓库根下存在 frontend/（含 package.json），构建产物输出到 frontend/dist。
# 在 deploy/ 目录执行：docker compose build portal-web
# =============================================================================

# ---------------- 阶段 1：构建前端 ----------------
FROM node:22-alpine AS build
WORKDIR /app

# 先拷依赖清单，利用层缓存（源码变动不重装依赖）
COPY frontend/package*.json ./

# registry 经 ENV 注入，对 npm ci / npm install 都生效（国内 npmmirror 镜像）
ENV npm_config_registry=https://registry.npmmirror.com
# 存在 package-lock.json 用 npm ci（可复现安装）；没有则退回 npm install。
# 注意不要写成 “npm ci || npm install”：ci 失败往往意味着 lockfile 与 package.json
# 不一致，静默退回会掩盖问题。
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build

# ---------------- 阶段 2：nginx 运行时 ----------------
FROM nginx:1.27-alpine
ENV TZ=Asia/Shanghai

# SPA 静态产物（含 index.html 与带 hash 的 js/css）
COPY --from=build /app/dist /usr/share/nginx/html

# nginx 官方镜像自带 20-envsubst-on-templates 机制：启动时将
# /etc/nginx/templates/*.template 中“容器环境中已定义的变量”做 envsubst，
# 输出到 /etc/nginx/conf.d/default.conf（同名覆盖镜像自带的 stock 配置）。
# 仅 $BACKEND_UPSTREAM / $ZLM_UPSTREAM（compose 注入）会被替换；
# $host、$uri、$request_uri 等 nginx 运行时变量不受影响（它们不是环境变量）。
COPY deploy/nginx/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80 443
