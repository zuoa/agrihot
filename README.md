# AgriHot · 农业科技情报与前沿洞察

追踪农业政策、前沿研究与技术进展，让有价值的信息更早被看见。绿色主题农业科技情报站：政策 / 报道 / 学术论文聚合 + 每日《农业农村日报》，
通过 Agent Skill / MCP 检索内容；内部爬虫通过推送专用 Key 提交内容，服务层自动去重后上线。

## 结构

- `backend/` — FastAPI + PostgreSQL（SQLAlchemy 2.0 async）
- `frontend/` — Nuxt 4 + Vue 3 + Tailwind（公开页 SSR，`/admin` 客户端渲染）

## 启动

### 后端（:8100）

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb agrihot                     # 需要 PostgreSQL 16 与 pgvector 扩展
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

### 前端（:3000，公开页 SSR；`/api` 代理到 :8100）

```bash
cd frontend
npm install && npm run dev
```

## 微信分享

公开页面在服务端输出分享标题、简介与图片，通用预览使用 `/og-image.png`（1200×630），
微信默认使用 `/share-icon.png`（600×600 方形缩略图）；有封面的文章优先使用文章封面。
首页、文章、日报与主题页的分享内容随页面切换更新。

微信朋友圈 / 好友的自定义缩略图通过[微信 JS-SDK](https://developers.weixin.qq.com/doc/offiaccount/OA_Web_Apps/JS-SDK.html)设置，
仅配置 Open Graph 元信息不能保证微信采用指定图片。启用方式：

1. 准备具有 `updateAppMessageShareData` / `updateTimelineShareData` 权限的公众号，在公众号后台配置网站的 **JS 接口安全域名**、域名验证文件及服务器出口 **IP 白名单**。
2. Docker 部署时在 `deploy/.env` 填入 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`，重新创建前端容器。
   本地前端可设置 `NUXT_WECHAT_APP_ID`、`NUXT_WECHAT_APP_SECRET`；`NUXT_PUBLIC_SITE_URL` 必须与实际访问的网站源站一致。
3. 用真实手机微信打开首页、文章或日报，再从右上角菜单分享给好友或朋友圈，检查标题与图片。

签名接口 `/wechat/signature` 只签署配置的本站 URL，密钥与 ticket 留在服务端。
access token 与 ticket 按有效期提前 5 分钟刷新，同进程合并并发刷新；失败后冷却 60 秒。
缓存按 Nuxt 进程隔离，当前单前端容器可直接使用；多实例部署需共享凭据缓存。
未配置公众号时自动停用 SDK，页面继续提供通用分享元信息与日报分享长图。

修改分享图源文件后，可用 `rsvg-convert frontend/public/og-image.svg -o frontend/public/og-image.png`
及 `rsvg-convert frontend/public/share-icon.svg -o frontend/public/share-icon.png` 重新生成 PNG。

## Agent 读取接入

公开 `/agent` 提供 Skill 与远程 MCP 配置，以及读取 Key 申请表。管理员在 `/admin/agent`
查看申请、审批并复制一次性明文 Key，人工交付给申请人；已有 Key 可在 `/admin/keys` 停用。
读取与推送权限隔离，历史 Key 自动迁移为推送用途。网页原有匿名接口继续兼容。

- Skill 安装：`/agrihot-skill/README.md`；独立文件 `/agrihot-skill/SKILL.md`
- 使用说明：`/api/v1/agent`；站点索引：`/llms.txt`
- MCP：`/api/v1/mcp`，Streamable HTTP，支持自定义认证头的客户端
- 业务认证：`Authorization: Bearer <读取Key>`；默认每 Key 每分钟 60 次（单进程共享预算）
- MCP 工具：`search_content`、`list_items`、`get_item`、`list_dailies`、`get_daily`
- REST：`POST /api/v1/agent/search`、`POST /api/v1/agent/items`、`GET /api/v1/agent/items/{id}`、
  `GET /api/v1/agent/dailies`、`GET /api/v1/agent/dailies/{date|latest}`

```bash
curl http://localhost:8100/api/v1/agent/search \
  -H "Authorization: Bearer $AGRIHOT_API_KEY" -H 'Content-Type: application/json' \
  -d '{"q":"农业遥感","category":"论文","limit":5}'
# 管理员也可用 CLI 签发读取 Key（明文只输出一次）：
.venv/bin/python -m scripts.create_api_key research-assistant --purpose read
```

检索支持 `q`、`category`、`tags`（全部匹配）、`direction`、`since`、`until`、`limit`（1–50）。
时间范围按收录时间，建议传带时区 ISO 8601。最新/精选列表以 `before_id` 游标翻页；
日报以 `before` 日期翻页。检索只返回摘要和片段，详情另含已收录正文、论文卡片、
`site_url`、`original_url`、`has_fulltext`。站点不为 Agent 额外抓取缺失正文。

### GLM 混合召回与索引

配置 `EMBEDDING_API_KEY`，默认使用智谱 `embedding-3`、1024 维，接口基址
`https://open.bigmodel.cn/api/paas/v4`。支持独立的 `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、
`EMBEDDING_DIMENSIONS`、`EMBEDDING_TIMEOUT`，与 DeepSeek 评分配置无关。

中文分词全文检索 + pgvector 余弦召回，经 RRF 融合并按文章去重。PostgreSQL 使用 GIN
全文索引与精确向量距离排序；本期不引入近似向量索引。标题、摘要、标签与正文分段建索引。
内容变更在同一数据库事务中排入持久化队列，后台每 5 秒检查；失败按指数退避重试，
进程中断后可续跑。更换模型或维度自动回填，未完成时不会混用旧模型向量。

查询与回填在单进程内串行发送向量请求，默认至少间隔 1 秒，可用
`EMBEDDING_MIN_INTERVAL` 调整。收到 HTTP 429 时整体暂停请求，初始冷却由
`EMBEDDING_RATE_LIMIT_COOLDOWN` 控制（默认 60 秒），连续限流会指数延长至 1 小时，
并遵循更长的 `Retry-After`（最多 24 小时）。冷却期间新查询立即降级为关键词检索，
已缓存的查询向量仍可使用；后台保留待处理任务，冷却结束自动继续。
这些限制按进程生效，多实例或另开 CLI 回填时需分别留出账户额度。

智谱的 HTTP 429 也可能表示欠费，不能仅凭状态码判断：业务码 `1302` 是速率限制，
`1305` 是模型繁忙，`1113` 是账户欠费。后端只记录安全的数字业务码，管理后台可见
`provider_http_429_1302` 等原因；欠费显示 `provider_insufficient_balance` 并暂停请求
1 小时，需要在智谱控制台充值后重试。
详见[智谱错误码文档](https://docs.bigmodel.cn/cn/api/api-code)。

无凭据、API 异常或索引不全时返回关键词结果及 `degraded` / `degradation_reasons`。
后台 `/admin/agent` 展示覆盖率与错误；可点击补建，或运行：

```bash
.venv/bin/python -m scripts.reindex --run
.venv/bin/python -m scripts.reindex --force --run  # 重查哈希、重试失败，复用未变化的成功向量
```

`SEARCH_INDEX_ENABLED=false` 暂停自动索引，不影响查询现有索引。生产使用 PostgreSQL，
SQLite 仅供业务测试。GLM 凭据留空时仍可建立关键词索引，页面明确显示语义召回未启用。
文章卡片、详情和后台列表上的绿色层叠勾选图标表示已按当前模型完成向量索引。
文章内容更新或切换模型后，需重新索引成功才会显示。

## Agent 推送接入（内部维护）

```bash
curl -X POST http://localhost:8100/api/v1/ingest/items \
  -H "X-API-Key: <key>" -H "Content-Type: application/json" \
  -d '{"title":"…","url":"…","summary":"……（≥10字）","source_name":"…","category":"政策","tags":["智慧农业"]}'
```

- 批量：`POST /api/v1/ingest/items/batch`（≤50 条）
- 标签：`tags` 应为独立短词（如 `["智慧农业","遥感"]`）。若 Agent 把关键词用空格/顿号拼成一条，服务端会自动切开并丢弃日期、过长项；历史数据可用 `python -m scripts.retag` 重切（`--dry-run` 只打印）
- 长尾检索：`/tags/花生` 仍是原子主题；`/tags/四川省农科院%20花生%20大豆` 按词 AND 查询（必要时回退到标题/摘要），**不写进标签表**。评分会另给 `search_phrases`，详情页「相关检索」内链这些地址；`/n/{slug}-{id}` 301 到 `/items/{id}`
- 去重：`exact_url`（URL 规范化 + SHA-256）、`similar_title`（SimHash 海明距离 ≤6 或标题互相包含）；重复不报错，信源合并进已有条目（幂等，可安全重试）
- 重复推送携带正文时，会补入已有文章的空正文，不覆盖已保存的原文。服务端补抓正文逐篇提交，评分失败或后续任务中断不会撤回已保存内容；自动回补轮流处理缺正文记录，避免反复失败的文章阻塞队列。
- 原文获取采用可扩展的 `FulltextFetcher` 接口：DOI 解析、Frontiers XML、PDF、政务网页和通用网页分别处理，失败后使用 Jina 兜底，也会尝试已知的开放获取链接。接入与扩展方法见 [原文获取工具](docs/fulltext-fetchers.md)。
- 手动抓取失败会返回可读原因及 `reason`、`upstream_status`，区分原站证书异常、抓取服务限流、访问限制和超时。广西农业农村厅公共站点 `nynct.gxzf.gov.cn` 的 HTTPS 原文遇到证书错误时，会重试已验证可用的同路径 HTTP 文章；原文链接保持不变。
- 限流：60 次/分钟/Key
- 删除：`DELETE /api/v1/ingest/items/{id}`（下架测试/违规内容，同时清理日报引用）
- 完整说明仅在管理员登录后的 `/admin/agent-push`；公共 OpenAPI 不包含推送或管理接口。

## 自动精选评分

新条目入库后，后台调用 DeepSeek 评估：先做**相关性门槛**判断（与三农/农业信息化
无关直接出局），再按 5 个维度打分（满分 100）：影响力 30、信息增量 25、专业深度 20、
信源权威 15、时效性 10；同一次调用会**重写主题标签**（3–6 个可聚合短词），并另给 0–2 条检索短语（空格分词长尾，不入库为 Tag）；Agent
给的 tags 只作评分前的兜底，失败则保留切开后的原标签。每天（按入库日）总分 ≥
`SELECTION_THRESHOLD`（默认 75）的条目中，评分最高的前 `DAILY_TOP_N`（默认 5）篇
进入首页「精选」，每次评分后重算当天名单；评分请求失败时不进精选（fail-closed）。
总分与各维度明细会存库并在详情页展示。

环境变量：`DEEPSEEK_API_KEY`（留空则关闭评分）、`DEEPSEEK_BASE_URL`、
`DEEPSEEK_MODEL`（默认 `deepseek-chat`）、`SELECTION_THRESHOLD`、`DAILY_TOP_N`。

## 两级主题与分类

首页另提供「热点专题」：围绕同一事件或研究问题自动组织文章、综合发现与引用，
支持主体和理论方法扩展；每天默认 08:30 更新，首页展示 1 个主专题和最多 2 个次专题。
后台「热点专题」可编辑、锁定、置顶、合并、下架及重新生成。
专题生成复用 DeepSeek，外部学术补充使用 OpenAlex，可选 `TAVILY_API_KEY` 扩展网页检索。
配置、试跑、接口及来源变更处理见 [热点专题说明](docs/hot-specials.md)。

`/topic` 提供 10 个一级频道与 62 个二级方向，支持内容类型、技术多选、主题内搜索和分页。
父级频道按文章去重聚合子主题的主辅归属；`/tags` 和已有标签/组合检索地址继续可用。
机构规范词支持标签与关键词搜索中的别名查询，遥感等上下位技术词保持独立。目录、规则、技术词和机构别名维护在
`backend/app/taxonomy.yaml`，`code` / `slug` 保持稳定。

新文章及标题、摘要、正文、标签变更自动执行规则分类，不依赖评分和 DeepSeek。
证据不足进入待分类或待复核；可在后台内容页按状态筛选、编辑主辅主题，或点击「重分主题」。
人工选择默认锁定，重评分、补抓正文、历史回填均保留锁定归属。后台「任务 → 回填主题分类」
可运行独立回填，不修改分数和精选。区域与机构已区分标签类型，本期主题页面先开放技术筛选。

升级后先同步结构和字典，再预览历史分类（Docker 可在 `docker compose exec backend` 后执行同样命令）：

```bash
cd backend
.venv/bin/python -m scripts.taxonomy sync
.venv/bin/python -m scripts.taxonomy backfill --dry-run --report /tmp/taxonomy-preview.json
.venv/bin/python -m scripts.taxonomy backfill --batch-id initial-taxonomy --report /tmp/taxonomy-result.json
# 中断后传相同 batch-id 续跑；可用 --limit 先跑少量、--batch-size 控制读取批量。
.venv/bin/python -m scripts.taxonomy backfill --batch-id initial-taxonomy
# 配置 DEEPSEEK_API_KEY 后，按需对规则待复核项调用模型，产生 API 用量：
.venv/bin/python -m scripts.taxonomy backfill --use-model --batch-id taxonomy-model-review
# 仅撤回该批次且之后未改动、未人工锁定的归属；保留审计记录：
.venv/bin/python -m scripts.taxonomy rollback initial-taxonomy
```

默认启动只创建新增结构并同步目录，不自动回填历史文章。回填记录规则版本、输入哈希、
逐篇结果和断点；跨版本续跑须使用新批次。`--force` 重算相同版本，仍不会覆盖人工锁定。
`--dry-run` 只读取规则预览，不调用模型或写入分类与断点；须先完成结构同步。

公开接口：`GET /api/v1/taxonomy`、`GET /api/v1/taxonomy/{slug}`、
`GET /api/v1/taxonomy/facets?topic=rice`，文章查询增加 `topic` 和重复的 `technologies` 参数。
Agent REST 和 MCP 使用相同筛选规则；MCP 新增 `list_topics`。

功能范围、全量公开元数据回放和验证结果见 [主题系统实现与验收记录](docs/taxonomy-implementation-2026-10-22.md)。

```bash
# 专用测试库，会清空其中的应用表；使用真实 PostgreSQL + pgvector：
AGRIHOT_TEST_TAXONOMY_POSTGRES_URL=postgresql+asyncpg://localhost/agrihot_taxonomy_test \
  .venv/bin/python -m pytest tests/test_taxonomy.py -q
```

## 文献雷达（OpenAlex）

每天 `07:30`（`DAILY_TIMEZONE`）按 `backend/app/watchlist.yaml` 订阅的方向 / 期刊 / 学者，
从 [OpenAlex](https://openalex.org/) 增量拉取论文元数据。抓取不调用 AI；入库后走现有评分，
并对论文生成中文结构化卡片（速览 / 方法 / 发现 / 方向 / 机会点）。去重优先 DOI，
再 OpenAlex ID、URL、标题相似。自动文献流程使用摘要与卡片；论文支持在后台手动或显式批量获取全文。

- 关注面：改 `watchlist.yaml`（ISSN、检索式、学者 OpenAlex ID）
- 手动跑一轮：`python -m scripts.fetch_literature`
- 环境变量：`OPENALEX_API_KEY`（可选）、`OPENALEX_MAILTO`、`LITERATURE_FETCH_ENABLED`、
  `LITERATURE_FETCH_TIME`（默认 `07:30`）
- 中文 OA 刊（如《智慧农业》）OpenAlex 覆盖差，后续用 DOAJ 补，不爬知网 / WoS / 期刊官网

旧数据补评分：`python -m scripts.rescore`（仅未评分条目；`--all` 全部重评）。

## 管理控制台

公开站页脚「管理」进入 `/admin`（独立宽布局，不混在阅读栏里）。密码来自环境变量
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

网页列表使用 `compact=true`：文章列表、主题检索、相关文章及日报内的文章省略正文、
评分明细与分类审计信息，数据库查询也跳过这些字段。原接口默认返回完整格式；文章详情始终保留全文。
首页与标签页每页 20 条，可翻页查看历史内容；从卡片编辑时先读取完整详情。API 在客户端支持时启用 gzip 压缩。

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
docker compose up -d          # 启动 db + backend + frontend（Nitro SSR，:80）

# 首次初始化：
docker compose exec backend python -m scripts.create_api_key my-crawler   # 签发推送 Key
docker compose exec backend python -m scripts.seed_from_pdf               # 可选：导入演示日报
```

### 从原 PostgreSQL 镜像升级

本版本数据库镜像改为 `pgvector/pgvector:pg16-bookworm`，保持 PostgreSQL 16。
原版使用 Alpine，不能直接假定其数据目录与 Bookworm 的区域设置兼容。
升级前用旧镜像执行 `pg_dump -Fc` 保存完整备份并验证可读取；停止业务写入后，
保留旧卷，使用新卷初始化 pgvector 镜像，再用 `pg_restore` 恢复数据。
确认表、条目数量及旧 Key 均保留后启动新版后端。不要执行 `docker compose down -v`。

全文抓取在独立的 `worker` 容器里运行（`python -m app.services.content_worker`）。
API 容器设置 `AGRIHOT_PROCESS=api`，只接请求，不再在抓原文时占用数据库连接。
连接池等满 5 秒返回 503。四个容器的 json 日志限制为单个 20MB、保留 3 个。

后端首次启动自动启用 vector 扩展、迁移历史 Key 用途并创建索引表；数据库账号需要创建扩展权限，
托管数据库可由管理员预先执行 `CREATE EXTENSION IF NOT EXISTS vector`。
配置 `EMBEDDING_API_KEY` 后，历史内容在后台逐步回填。
回滚时恢复旧应用、原数据库镜像和保留的旧卷；回滚前导出上线期间新增数据，避免丢失。

完成首次数据库迁移后，日常升级：`docker compose pull && docker compose up -d`。

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 对专用测试数据库运行真实 PostgreSQL + pgvector 接入测试（会清空该库的应用表）：
AGRIHOT_TEST_POSTGRES_URL=postgresql+asyncpg://localhost/agrihot_agent_test \
  .venv/bin/python -m pytest tests/test_agent_access.py -q
# 同时配置 AGRIHOT_LIVE_EMBEDDING_API_KEY 时，还会执行真实 GLM 向量化与召回测试（产生 API 用量）。
# 凭据未配置时自动跳过；不会以替代服务冒充 GLM 联调成功。
```
