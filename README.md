# AgriHot · 农业信息化动态聚合

参考 aihot 形态的绿色主题农业信息化资讯站：政策 / 报道 / 学术论文聚合 + 每日《农业农村日报》，
爬虫 Agent 通过开放 API 推送内容，服务层自动去重（URL 精确 + 标题 SimHash 相似）后直接上线。

## 结构

- `backend/` — FastAPI + PostgreSQL（SQLAlchemy 2.0 async）
- `frontend/` — Vue 3 + Vite + Tailwind（绿色主题 SPA）

## 启动

### 后端（:8100）

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb agrihot                     # 需要本地 PostgreSQL
.venv/bin/uvicorn app.main:app --port 8100
```

首次启动自动建表。导入演示数据（2026-07-15 日报，18 条）：

```bash
.venv/bin/python -m scripts.seed_from_pdf
```

创建 Agent 推送用 API Key（原始 Key 只显示一次）：

```bash
.venv/bin/python -m scripts.create_api_key my-crawler
```

### 前端（:5173，/api 代理到 :8100）

```bash
cd frontend
npm install && npm run dev
```

## Agent 推送（摘要）

```bash
curl -X POST http://localhost:8100/api/v1/ingest/items \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"title":"…","url":"…","summary":"……（≥10字）","source_name":"…","category":"政策","tags":["智慧农业"]}'
```

- 批量：`POST /api/v1/ingest/items/batch`（≤50 条）
- 去重：`exact_url`（URL 规范化 + SHA-256）、`similar_title`（SimHash 海明距离 ≤6 或标题互相包含）；重复不报错，信源合并进已有条目（幂等，可安全重试）
- 限流：60 次/分钟/Key
- 删除：`DELETE /api/v1/ingest/items/{id}`（下架测试/违规内容，同时清理日报引用）
- 完整说明见站点 `/agent` 页或 `/docs`（OpenAPI）

## 自动精选评分

新条目入库后，后台调用 DeepSeek 按 5 个维度打分（满分 100）：主题相关性 30、
重要性 25、内容质量 20、信源可信度 15、时效性 10。总分 ≥ `SELECTION_THRESHOLD`
（默认 70）自动进入首页「精选」；评分请求失败时不进精选（fail-closed）。

环境变量：`DEEPSEEK_API_KEY`（留空则关闭评分）、`DEEPSEEK_BASE_URL`、
`DEEPSEEK_MODEL`（默认 `deepseek-chat`）、`SELECTION_THRESHOLD`。

## 管理控制台

页面右上角「管理」按钮输入密码登录后，每张卡片 / 详情页出现「编辑 / 删除」操作：
标题、摘要、分类、标签、热度、链接、是否精选均可修改；删除会同时清理日报引用。
密码通过环境变量 `ADMIN_PASSWORD` 预置（留空则管理接口整体关闭）。

- 登录：`POST /api/v1/admin/login`（限流 10 次/分钟防爆破），返回 HMAC 无状态令牌
- 编辑：`PATCH /api/v1/admin/items/{id}`（部分更新，仅提交要改的字段）
- 删除：`DELETE /api/v1/admin/items/{id}`
- 前端令牌存于 localStorage，请求头 `X-Admin-Token` 携带

## 公开只读 API

`GET /api/v1/items`（mode=selected|all、window=24h|7d、category、tag、q、page）
`GET /api/v1/items/{id}`、`GET /api/v1/dailies[/latest|/{date}]`、`GET /api/v1/tags`

## Docker 构建与部署

### GitHub Actions 自动构建（推送到 GHCR）

`.github/workflows/docker.yml` 在 push 到 `master`/`main` 或打 `v*` 标签时构建并推送两个镜像到
GitHub Container Registry，**无需配置任何 Secret**（使用自动注入的 `GITHUB_TOKEN`）：

- `ghcr.io/zuoa/agrihot-backend:latest`（+ `sha-xxxxxxx` / 版本标签）
- `ghcr.io/zuoa/agrihot-frontend:latest`

首次构建后包默认为私有，可在 https://github.com/zuoa?tab=packages 将两个包的
**Package settings → Change visibility** 设为 Public；私有包则需先在服务器执行
`docker login ghcr.io`（用一个有 `read:packages` 权限的 PAT）。

### 远程服务器部署（docker compose 拉取镜像）

```bash
cd deploy
cp .env.example .env          # 设置 DB_PASSWORD（自动精选需另填 DEEPSEEK_API_KEY）
docker compose up -d          # 启动 db + backend + frontend（前端 :80）

# 首次初始化：
docker compose exec backend python -m scripts.create_api_key my-crawler   # 签发推送 Key
docker compose exec backend python -m scripts.seed_from_pdf               # 可选：导入演示日报
```

升级到新版本：`docker compose pull && docker compose up -d`。

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```
