# VideoNexus — GB28181 视频监管门户

面向仓库质押监管场景的最小门户：银行监管人员经 HTTPS 登录，**只能查看被授权的摄像头**，可实时预览（动态水印）、按时间段回放录像、发起录像下载。视频能力（信令、拉流、转协议）完全复用现有 WVP + ZLM，门户只做**账号、授权、审计、下载编排**四件事，WVP 保持原样、仅内网访问。

设计文档见 [最小门户方案设计.md](./最小门户方案设计.md)。

## 架构

```
银行用户浏览器（公网唯一入口 443）
        │
      Nginx（portal-web 容器）
      ├── /            → Vue3 SPA
      ├── /api/        → 门户后端 FastAPI（portal-backend 容器）
      ├── /stream/     → ZLM（auth_request 鉴权后反代，ws-flv/hls）
      └── /protected-download/ → 下载文件 X-Accel 限速内部下发
        │
   门户后端（SQLite→MySQL，/data 卷）
   └── WvpClient（api-key → 内网 WVP REST）
        │ 内网
   WVP ── ZLM
```

核心安全设计：
- 通道级数据权限：用户↔通道授权表（实时/回放/下载三开关 + 有效期），所有视频操作服务端校验；
- 播放地址由门户签发（短时效 token + 绑定登录会话），Nginx auth_request 逐请求校验，ZLM 原始地址永不下发，鉴权失败记审计（疑似外泄）；
- 下载为异步任务（WVP 倍速下载→落盘→限时限速下发→自动清理）；
- 审计 append-only：登录/播放/回放/下载/授权变更全留痕，可按条件检索并导出 CSV。

## 目录结构

```
backend/    FastAPI 后端（账号/授权/审计/播放/回放/下载编排 + WVP 客户端）
frontend/   Vue3 前端（实时预览/回放/下载/管理端，Jessibuca 本地 vendor）
deploy/     docker-compose 编排、Dockerfile×3、nginx 模板、备份脚本、部署文档
scripts/    第0期 WVP API 验证脚本（对接现网前先跑一遍）
```

## 快速开始

### 0）对接前验证（建议先做）

复制 `scripts/wvp_config.example.json` 为 `wvp_config.json` 填入真实 WVP 地址，按 [scripts/README.md](./scripts/README.md) 逐项验证（api-key、通道、点播、回放、下载落盘、H.265 播放性能），结果记入 `docs/phase0-验证结果.md`。

### 1）本地开发

```bash
# 后端（Python 3.12）
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS 用 .venv/bin/pip
DATA_DIR=./data JWT_SECRET=dev-secret INITIAL_ADMIN_PASSWORD=Admin@12345 PUBLIC_HTTPS=false \
  .venv/Scripts/python -m uvicorn app.main:app --port 9000 --reload

# 前端（Node 22）
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 已代理到 127.0.0.1:9000
```

首次启动自动创建管理员（`INITIAL_ADMIN_USERNAME`，默认 admin），首登强制改密。

### 2）后端测试

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -q   # 25 项，含越权矩阵
```

### 3）生产部署（Docker Compose）

见 [deploy/README.md](./deploy/README.md)：`cp .env.example .env` 填好 WVP/ZLM 地址与密钥 → 放证书 → `docker compose build && docker compose up -d`。公网只开 443；WVP/ZLM 保持内网。

## 里程碑与现状

- [x] 第0期验证脚本（scripts/）
- [x] 后端 MVP：账号/机构/授权/审计/实时/回放/下载任务（25 项测试全绿）
- [x] 前端 MVP：登录/实时预览（水印）/回放/下载/管理端
- [x] Docker Compose 部署编排（已静态校验，待部署机实测）
- [ ] 现网联调：跑第0期脚本 → 部署 → 与银行确认审计字段清单

## 关键配置速查

| 环境变量 | 说明 |
|---|---|
| `WVP_BASE_URL` / `WVP_API_KEY` | WVP 地址与 API Key（优先；留空则用账号密码自动重登） |
| `ZLM_UPSTREAM` | ZLM HTTP 地址（compose/nginx 反代播放流用） |
| `JWT_SECRET` | 会话签名密钥，生产必填（`openssl rand -hex 48`） |
| `INITIAL_ADMIN_PASSWORD` | 初始管理员密码（首启后立即修改） |
| `DOWNLOAD_MAX_DURATION_HOURS` / `FILE_RETENTION_DAYS` | 下载时段上限 / 文件保留天数 |
| `PUBLIC_HTTPS` | 签发 ws:// 还是 wss:// 播放地址（本地开发设 false） |

完整清单见 [deploy/.env.example](./deploy/.env.example)。
