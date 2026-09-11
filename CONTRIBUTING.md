# 贡献指南

感谢参与改进 VideoNexus。以下是最小必要约定。

## 环境要求

- Python 3.12+、Node 22+
- 一个可访问的 WVP（≥ 2.7.x，启用 API Key）+ ZLMediaKit 环境（联调必需，纯改前端时可省略）

## 本地开发

```bash
# 后端
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt          # Linux/macOS: .venv/bin/pip
cp ../deploy/.env.example .env                          # 填 WVP/ZLM 地址与密钥
# 本地无 Nginx，需开启后端自带的流代理：
#   DEV_STREAM_PROXY=true
.venv/Scripts/python -m uvicorn app.main:app --port 9000

# 前端
cd frontend
npm install
npm run dev                                             # http://localhost:5173
```

提交前请确保：

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -q   # 全绿
cd frontend && npm run build                              # 通过
```

## 代码约定

- **后端**：FastAPI + SQLAlchemy(async)；业务逻辑放 `app/services/`，路由只做参数校验与编排；改动模型必须附 Alembic 迁移（`alembic revision --autogenerate`，新列务必带 `server_default`）
- **前端**：Vue 3 `<script setup>` + Element Plus；接口调用统一走 `src/api/index.js`（错误提示由响应拦截器统一处理）
- **注释**：只解释“为什么”，不复述代码在做什么
- **授权相关改动**：任何涉及视频/回放/下载的接口都必须在服务端校验授权（`app/services/grants.py`），不得只在界面上隐藏

## 提交与 PR

- 一个 PR 聚焦一件事；描述中写清动机、改法与影响面
- 涉及接口变更时同步更新 README 的接口/配置说明
- 涉及数据库变更时确认迁移可 `upgrade` 也可 `downgrade`

## ⚠️ 截图与隐私红线

**禁止提交任何包含真实监控画面的截图**。本项目的截图（`screenshots/`）会进入公开仓库：

- 只允许提交**不含视频画面**的界面截图（登录页、下载任务表、管理端列表等）
- 展示播放效果请使用自绘示意图，或对画面做重度模糊处理
- 同理，不要提交真实设备编号、公网地址、内网拓扑、账号密码、密钥

## 安全问题

请勿用公开 Issue 报告安全漏洞，见 [SECURITY.md](./SECURITY.md)。
