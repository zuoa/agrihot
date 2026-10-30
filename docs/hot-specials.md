# 热点专题

首页在无分类筛选的第一页展示一个主专题和最多两个次专题，材料不足时按实际数量展示，暂无有效专题时保留单篇焦点。全部专题在 `/specials`，详情为 `/specials/{id}`。现有 `/topic` 分类目录和 `/api/v1/topics` 标签检索保持独立。

## 自动生成

默认按 `DAILY_TIMEZONE`（Asia/Shanghai）每天 08:30 运行，最多新建 3 个、更新 10 个。运营后台的「配置 → 热点专题」可修改时间、额度和开关；「任务」支持手动执行，「热点专题」支持编辑、关联文章、置顶、锁定、合并、下架和重新生成。

复用 `DEEPSEEK_API_KEY` 综合与检查内容。外部先查询 OpenAlex 原始论文摘要，配置 `TAVILY_API_KEY` 后同时搜索网页并使用现有 FulltextEngine 获取正文；最多 3 个查询、5 份补充资料。未配置 Tavily 时仍运行站内综合和学术补充，外部服务故障不会阻断具有充分站内证据的专题。外部资料独立保存在专题发布版本中，不进入新闻流，也不增加站内热点规模。

发现阶段在近 60 天收录/发表材料中按分类均衡抽取最多 300 篇；生产 PostgreSQL 下另使用已就绪、当前模型的 pgvector 索引召回最多 40 篇背景材料，不新增向量请求。模型判断具体事件或研究问题，不按宽泛标签直接聚合。已有议题范围保持固定。

事件至少 3 篇近 14 天核心文章，研究至少 3 篇近 60 天核心文章；其中至少一篇在最近 7 天发表，且有至少 2 组独立证据。无发表日期只作为背景。模型合并同一成果的转载与解读，并通过 DOI 关联进一步合并。热点由材料新近程度、质量及独立证据规模排序，不依赖浏览量。

所有事实块保存来源 ID 与逐字证据摘录。结构、引用存在性、摘录匹配、共同发现的独立证据数、比较引用及时间线日期先做程序检查，再进行一次独立模型检查。该检查不能保证事实完全准确。失败的新专题保留为可重试草稿；已有专题不覆盖上次发布内容。

网络请求在数据库会话外执行；发布前重新核对站内来源哈希，事务中写入关联文章和完整版本。输入未实质变化时跳过模型与外部查询，不更新内容日期。更换证据组名称或关联原因措辞不会单独触发重生成。失败可逐专题重试；worker 重启恢复队列任务，已经发布且输入未变的专题跳过。

超过 30 天没有实质更新转归档，保留地址并退出首页自动推荐。有新证据且重新通过检查后恢复。人工修改自动锁定对应字段，可在后台解锁。综合内容锁定期间不自动覆盖；文章关联修改在重新生成后进入公开版本。

## 来源变更

公开接口核对版本保存的站内来源与当前来源。最新版本失效时优先返回仍有效的旧版本；没有有效版本时专题从公开列表、详情和 sitemap 撤除，后台显示待重新核验。删除来源同样处理。后台仍能查看原发布版本的引用与历史。专题详情不设置 SWR，首页沿用现有 60 秒缓存。

## 配置与命令

Docker 的 API 与 worker 已传入以下变量：

```dotenv
SPECIALS_ENABLED=true
SPECIALS_TIME=08:30
SPECIALS_MAX_NEW=3
SPECIALS_MAX_UPDATES=10
TAVILY_API_KEY=
```

新表由现有 `ensure_schema` 创建，不回填或修改已有文章。升级仍使用既有 Docker 构建和部署流程。

在 backend 目录运行（先启动一次完成结构创建）：

```bash
.venv/bin/python -m scripts.specials --dry-run  # 模型选题预览；会调用模型，但不写数据库
.venv/bin/python -m scripts.specials            # 生成并自动发布通过检查的专题
.venv/bin/python -m scripts.specials --id 12    # 重新生成指定专题，保留锁定字段
```

初次上线先用 `--dry-run` 检查候选，按需用 `SPECIALS_ENABLED=false` 暂停自动发布。生产部署前应检查真实材料的聚类与综合效果。

## 接口

- `GET /api/v1/specials`：`kind=event|research`、`status=published|archived`、`q`、`item_id`、`page`、`page_size`。
- `GET /api/v1/specials/featured`：最多 3 个仍有有效证据的已发布专题。
- `GET /api/v1/specials/{id}`：结构化文档、引用、分页文章、相关分类及更新记录，支持 `category`、`page`、`page_size`。公开引用省略正文及内部哈希；引用摘录保留在各内容块中。
- 管理接口在 `/api/v1/admin/specials`，沿用 `X-Admin-Token`，不公开在 OpenAPI 中。

## 验证

```bash
cd backend
.venv/bin/python -m pytest tests/test_specials.py -q
# 仅允许 agrihot_specials_test_ 前缀的专用数据库；会清空其中的应用表：
AGRIHOT_TEST_SPECIALS_POSTGRES_URL=postgresql+asyncpg://localhost/agrihot_specials_test_local \
  .venv/bin/python -m pytest tests/test_specials.py -q
cd ../frontend
npm test
npm run build
```

浏览器验收使用本机 Chrome 和独立的本地样例库。手机/Android 模拟器不参与测试；真实手机及生产模型、外部服务的内容质量另行验收。
