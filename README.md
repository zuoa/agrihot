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
- 标签：`tags` 应为独立短词（如 `["智慧农业","遥感"]`）。若 Agent 把关键词用空格/顿号拼成一条，服务端会自动切开并丢弃日期、过长项；历史数据可用 `python -m scripts.retag` 重切（`--dry-run` 只打印）
- 去重：`exact_url`（URL 规范化 + SHA-256）、`similar_title`（SimHash 海明距离 ≤6 或标题互相包含）；重复不报错，信源合并进已有条目（幂等，可安全重试）
- 限流：60 次/分钟/Key
- 删除：`DELETE /api/v1/ingest/items/{id}`（下架测试/违规内容，同时清理日报引用）
- 完整说明见站点 `/agent` 页或 `/docs`（OpenAPI）

## 自动精选评分

新条目入库后，后台调用 DeepSeek 评估：先做**相关性门槛**判断（与三农/农业信息化
无关直接出局），再按 5 个维度打分（满分 100）：影响力 30、信息增量 25、专业深度 20、
信源权威 15、时效性 10；同一次调用会**重写主题标签**（3–6 个可聚合短词），Agent
给的 tags 只作评分前的兜底，失败则保留切开后的原标签。每天（按入库日）总分 ≥
`SELECTION_THRESHOLD`（默认 75）的条目中，评分最高的前 `DAILY_TOP_N`（默认 5）篇
进入首页「精选」，每次评分后重算当天名单；评分请求失败时不进精选（fail-closed）。
总分与各维度明细会存库并在详情页展示。

环境变量：`DEEPSEEK_API_KEY`（留空则关闭评分）、`DEEPSEEK_BASE_URL`、
`DEEPSEEK_MODEL`（默认 `deepseek-chat`）、`SELECTION_THRESHOLD`、`DAILY_TOP_N`。

## 文献雷达（OpenAlex）

每天 `07:30`（`DAILY_TIMEZONE`）按 `backend/app/watchlist.yaml` 订阅的方向 / 期刊 / 学者，
从 [OpenAlex](https://openalex.org/) 增量拉取论文元数据。抓取不调用 AI；入库后走现有评分，
并对论文生成中文结构化卡片（速览 / 方法 / 发现 / 方向 / 机会点）。去重优先 DOI，
再 OpenAlex ID、URL、标题相似。论文不经 Jina 抓全文。

- 关注面：改 `watchlist.yaml`（ISSN、检索式、学者 OpenAlex ID）
- 手动跑一轮：`python -m scripts.fetch_literature`
- 环境变量：`OPENALEX_API_KEY`（可选）、`OPENALEX_MAILTO`、`LITERATURE_FETCH_ENABLED`、
  `LITERATURE_FETCH_TIME`（默认 `07:30`）
- 中文 OA 刊（如《智慧农业》）OpenAlex 覆盖差，后续用 DOAJ 补，不爬知网 / WoS / 期刊官网

旧数据补评分：`python -m scripts.rescore`（仅未评分条目；`--all` 全部重评）。

## 管理控制台

公开站右上角「管理」进入 `/admin`（独立宽布局，不混在阅读栏里）。密码来自环境变量
`ADMIN_PASSWORD`（留空则管理接口整体关闭）。令牌为带 7 天过期的 HMAC，请求头
`X-Admin-Token`；公开页登录后仍可在卡片上快捷编辑 / 删除。

后台页面：

- **总览**：条目 / 精选 / 日报计数，无全文与未评分积压，调度下次时间
- **内容**：筛选、编辑、删除、重抓全文、单条重评；支持批量删除与批量抓全文
- **任务**：手动跑一轮文献拉取、生成日报、补评未评分、重切标签（后台执行，防重叠）
- **配置**：精选阈值、名额、调度时刻等运营旋钮（热改写入数据库；密钥仍走环境变量，界面只显示是否已配置）
- **关注面**：编辑 OpenAlex 订阅（方向 / 期刊 / 学者 / 预筛词），保存进数据库
- **API Key**：签发（明文只显示一次）、停用 / 启用爬虫推送 Key

主要接口（均需管理令牌，登录除外）：

- `POST /api/v1/admin/login`（限流 10 次/分钟）
- `GET /api/v1/admin/me` · `GET /api/v1/admin/overview`
- `GET /api/v1/admin/items`（审核筛选）· `PATCH|DELETE /api/v1/admin/items/{id}`
- `POST /api/v1/admin/items/{id}/fetch-content` · `POST /api/v1/admin/items/{id}/rescore`
- `POST /api/v1/admin/items/batch-delete` · `POST /api/v1/admin/items/batch-fetch-content`
- `GET /api/v1/admin/jobs` · `POST /api/v1/admin/jobs/{name}/run`
- `GET|PATCH /api/v1/admin/settings` · `GET|PUT /api/v1/admin/watchlist`
- `GET|POST /api/v1/admin/api-keys` · `PATCH /api/v1/admin/api-keys/{id}`

## 公开只读 API

`GET /api/v1/items`（mode=selected|all、window=24h|7d、category、tag、q、page）
`GET /api/v1/items/{id}`、`GET /api/v1/dailies[/latest|/{date}]`、`GET /api/v1/tags`、`GET /api/v1/stats`

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
cp .env.example .env          # 设置 DB_PASSWORD（自动精选填 DEEPSEEK_API_KEY；文献雷达可选 OPENALEX_API_KEY）
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
