# VideoNexus 门户部署文档（Docker Compose）

GB28181 视频监管门户的一键部署编排：FastAPI 后端（SQLite）+ Vue3 前端 + Nginx 统一入口 + 每日数据库备份。

## 一、架构

```
                    公网/内网用户（浏览器）
                            │ https (443，唯一公网入口)
                            ▼
┌────────────────────────── deploy/ Docker Compose ──────────────────────────┐
│                                                                            │
│  ┌─────────────────┐   /api/ 代理    ┌──────────────────────────────────┐  │
│  │  portal-web     │ ──────────────► │  portal-backend                  │  │
│  │  nginx 1.27     │                 │  FastAPI (uvicorn :9000)         │  │
│  │  Vue3 静态资源  │  /stream/ 鉴权  │  alembic 迁移（启动时自动执行）  │  │
│  │  TLS 证书       │   后转发 ───┐   │  会话/审计/下载任务            │  │
│  │                 │             │   └───────┬──────────────────────────┘  │
│  │  /protected-    │             │           │ portal-data 卷 (/data)      │
│  │  download/ 静态 │             │   ┌───────▼──────────┐                  │
│  │  发送下载文件   │             │   │ portal.db (WAL)  │◄── portal-backup │
│  └─────────────────┘             │   │ /data/downloads  │    每日 03:00    │
│         ▲  X-Accel-Redirect      │   └──────────────────┘    sqlite .backup│
│         └────────────────────────┘           ▲                → /backups   │
│                                              │                             │
└──────────────────────────────────────────────┼─────────────────────────────┘
                                               │ 内网（不可暴露公网）
                            ┌──────────────────┴──────────────────┐
                            │  WVP-GB28181-pro (:18080)           │
                            │  ZLM 流媒体 (:80/8080...)           │
                            │  摄像机/GB28181 设备                │
                            └─────────────────────────────────────┘
```

链路要点：

- 用户只访问 `https://<门户地址>`（443）。80 端口仅做 301 跳转。
- `/api/*` → 后端；`/stream/*` → 先经后端 `/internal/stream/auth` 鉴权（auth_request），再转发 ZLM 播放流；下载文件由后端 `X-Accel-Redirect` 交给 nginx 从 `/data/downloads` 限速静态发送。
- 后端不暴露宿主端口；WVP/ZLM 也不暴露公网。

## 二、目录结构

```
deploy/
├── docker-compose.yml          # 编排（3 服务 + 2 卷）
├── backend.Dockerfile          # 后端镜像（python:3.12-slim）
├── backend-entrypoint.sh       # 后端入口：alembic 迁移 → uvicorn
├── frontend.Dockerfile         # 前端多阶段构建（node 构建 → nginx 托管）
├── backup.Dockerfile           # 备份镜像（alpine + sqlite + crond）
├── backup/backup.sh            # 备份脚本（每日 03:00，保留 30 份）
├── nginx/nginx.conf.template   # nginx 配置模板（envsubst 渲染）
├── certs/                      # TLS 证书（fullchain.pem/privkey.pem，不入库）
│   └── gen-selfsigned.sh       # 自签证书脚本（内网测试）
└── .env.example                # 环境变量清单 → 复制为 .env 使用
```

## 三、首次部署

> 前提：部署机已安装 Docker Engine 20.10+ 与 docker compose v2 插件；
> 仓库内 `frontend/` 目录已就绪（前端构建在镜像内完成，依赖 `npm run build` 产出 dist）。
> **本仓库的编写/检查环境没有 Docker，以下命令均在部署机执行。**

### 1. 准备环境变量

```bash
cd deploy
cp .env.example .env
# 生成 JWT 密钥并填入 .env 的 JWT_SECRET：
openssl rand -hex 48
# 按注释逐项填写：JWT_SECRET、WVP_BASE_URL、WVP_API_KEY、ZLM_SECRET、
# INITIAL_ADMIN_PASSWORD、ZLM_UPSTREAM（ZLM 的 HTTP 端口地址，必填）
```

### 2. 准备证书

```bash
# 内网测试：自签证书（CN=portal.local，825 天）
bash certs/gen-selfsigned.sh
# 正式环境：把 CA 签发的证书放为 certs/fullchain.pem、私钥放为 certs/privkey.pem
```

### 3. 构建并启动

```bash
cd deploy
docker compose build          # 首次构建较慢（拉取基础镜像 + npm/pip 依赖）
docker compose up -d
docker compose ps             # portal-backend 应显示 healthy
docker compose logs -f portal-backend   # 首启日志：迁移、初始管理员信息
```

后端启动入口会自动执行 `alembic upgrade head` 完成建表/迁移。

### 4. 初始化管理员

- 若 `.env` 设置了 `INITIAL_ADMIN_PASSWORD`：用 `admin` / 该密码登录。
- 若留空：在 `docker compose logs portal-backend | grep -i password` 中查看随机生成的一次性密码。

登录后**立即**在「个人中心/账号管理」修改密码。

### 5. 通道同步

登录后进入通道管理页面，点击手动同步（或等待后台定时同步，默认 `CHANNEL_SYNC_MINUTES=5` 分钟一次），确认 GB28181 通道列表拉取成功。

### 6. 建机构 / 用户 / 授权

1. 创建机构（默认存储配额 `ORG_DEFAULT_QUOTA_GB`，可在机构上调整）；
2. 创建普通用户并分配机构与角色；
3. 为用户/机构授予通道查看与播放权限；
4. 用普通账号验证：播放实时视频（`/stream/` 鉴权链路）、回放、发起下载并取回文件。

## 四、证书替换（正式证书）

1. 将正式证书与私钥覆盖为 `deploy/certs/fullchain.pem`、`deploy/certs/privkey.pem`；
2. `docker compose restart portal-web`（挂载是目录级绑定，重启即可生效，无需重建镜像）；
3. 浏览器验证证书链与有效期；建议开启 HSTS（模板已启用 `max-age=31536000`）。

## 五、备份与恢复

### 备份（自动）

`portal-backup` 容器每日 **03:00（Asia/Shanghai）** 执行：

1. `sqlite3 /data/portal.db ".backup ..."` 生成一致性快照（在线备份，不停止业务）；
2. gzip 压缩为 `/backups/portal_YYYYmmdd_HHMMSS.db.gz`（命名卷 `portal-backups`）；
3. 自动轮转，仅保留最近 **30** 份；
4. 备份日志：`/backups/backup.log`（`docker exec portal-backup tail -20 /backups/backup.log`）。

下载的 mp4 录像**不备份**（可由 ZLM 重新下载生成，且按 `FILE_RETENTION_DAYS` 过期清理），只备份数据库。

手动立即备份一次：

```bash
docker exec portal-backup bash /usr/local/bin/backup.sh
```

将备份导出宿主机：

```bash
docker run --rm -v videonexus_deploy_portal-backups:/backups -v "$PWD:/out" alpine \
    cp /backups/portal_YYYYmmdd_HHMMSS.db.gz /out/
```

（卷全名以 `docker volume ls` 实际显示为准，通常为 `<项目目录名>_portal-backups`。）

### 恢复

前提：门户已停止写入（否则恢复后数据会被覆盖）。

```bash
cd deploy
docker compose stop portal-backend portal-backup

# 1) 解压备份到临时目录，得到 portal.db
gunzip portal_YYYYmmdd_HHMMSS.db.gz    # → portal_YYYYmmdd_HHMMSS.db，重命名为 portal.db

# 2) 拷回数据卷（覆盖 portal.db，并删除残留的 WAL/SHM，避免旧事务日志干扰）
docker run --rm -v videonexus_deploy_portal-data:/data -v "$PWD:/src" alpine \
    sh -c "cp /src/portal.db /data/portal.db && rm -f /data/portal.db-wal /data/portal.db-shm"

# 3) 重启
docker compose up -d
```

验证：登录门户确认通道/用户/下载数据回到备份时点。下载目录 `/data/downloads` 无需恢复（相关任务记录会显示文件缺失，属预期）。

## 六、升级流程

```bash
cd <仓库根>
git pull                        # 拉取新版本（backend/、frontend/、deploy/）
cd deploy
docker compose build            # 重新构建（依赖未变时命中层缓存，很快）
docker compose up -d            # 滚动替换；后端 entrypoint 自动执行 alembic upgrade head
docker compose logs -f portal-backend   # 观察迁移与启动日志
```

说明：

- 数据库结构变更由 alembic 在容器启动时自动迁移，无需手工操作；
- 首次部署到新机器时，把旧机的 `deploy/.env`（含 JWT_SECRET）与备份文件带过来即可；
- 回滚：`git checkout <上一个版本>` 后重复 build/up，必要时按第五章恢复数据库备份。

## 七、防火墙与网络要求

| 端口/方向 | 要求 |
| --- | --- |
| 公网 → 门户 443 (TCP) | **唯一需要对外开放的端口**；80 可选（仅跳转） |
| 门户容器 → WVP (:18080) | 仅内网可达，公网禁止暴露 WVP 管理端 |
| 门户容器 → ZLM (HTTP 端口) | 仅内网可达；`ZLM_UPSTREAM` 填其 HTTP API 端口地址 |
| 门户容器 → 后端 :9000 | compose 内部网络，无需防火墙规则 |
| 摄像机 ↔ WVP/ZLM | GB28181 信令/媒体流，按 WVP 文档配置，均走内网 |

- 后端容器**不映射任何宿主端口**，外网无法绕过 nginx 直连 9000。
- WVP/ZLM 与门户部署在不同内网机器时，容器默认可直接路由；若 WVP/ZLM 就跑在**部署机本机**，Linux 上请放开 `docker-compose.yml` 中 `extra_hosts: ["host.docker.internal:host-gateway"]` 的注释，并把 `WVP_BASE_URL`/`ZLM_UPSTREAM` 写成 `http://host.docker.internal:<端口>`。

## 八、常见问题

**1. WVP 的 API Key 怎么获取？**
登录 WVP-pro 管理端 → 用户管理 → 找到对应用户的「API Key」（或个人 API 接口令牌）填入 `WVP_API_KEY`。未配置时门户会用 `WVP_USERNAME/WVP_PASSWORD` 自动登录换取 token（token 过期自动重登），生产建议优先用 API Key。

**2. H.265（HEVC）播放兼容性**
GB28181 国标设备多为 H.265。浏览器直接解码 H.265 支持有限：Chrome/Edge 须开启硬解且版本较新，Safari 支持较好；HTTP-FLV/WS-FLV 场景建议使用支持 HEVC 的播放器内核。若大量终端无法软解，可在 WVP/ZLM 侧开启转码或优先选用 H.264 子码流。此为浏览器生态限制，与门户部署无关。

**3. 时区**
全链路固定 `Asia/Shanghai`：后端容器（Dockerfile ENV）、备份 crontab、nginx 容器均在 `.env`/compose 中设置 `TZ=Asia/Shanghai`；数据库按 naive 本地时间存取（中国无夏令时，无歧义）。若日志/备份时间不对，检查三处 TZ 是否一致。

**4. `portal-web` 起不来，日志报 `ZLM_UPSTREAM` 相关错误**
`deploy/.env` 未配置 `ZLM_UPSTREAM`（compose 会直接 fail-fast），或填的值不带 `http://` 前缀（nginx 要求 proxy_pass 求值结果必须含 `://`），或 nginx 渲染后 `proxy_pass http://;` 非法。填成完整 URL，如 `ZLM_UPSTREAM=http://192.168.1.100:8080`，然后 `docker compose up -d` 重建。

**5. 备份日志报 `attempt to write a readonly database`**
备份容器对 `/data` 不能挂载 `:ro`：后端 SQLite 启用了 WAL 模式，读取需要对 `-shm/-wal` 文件的写权限。`docker-compose.yml` 中 portal-backup 的卷已按读写配置，请勿改成 `:ro`。

**6. 登录接口返回 429**
nginx 对 `/api/auth/login` 限流（10 次/分钟，burst=5）。多人在同一出口 IP（NAT）后测试时容易触发，属预期防护；如确有需要调整，改 `nginx.conf.template` 顶部 `limit_req_zone` 的 rate。

**7. 修改了 `deploy/backup/backup.sh` 不生效**
该目录挂载到容器 `/scripts`，crontab 优先执行宿主侧脚本，保存后下一次调度即生效（无需重建）；如用“替换文件”方式编辑（部分编辑器会换 inode），执行 `docker compose restart portal-backup` 重新绑定。
