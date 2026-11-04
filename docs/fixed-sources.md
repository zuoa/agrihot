# 固定信源采集

日常发现优先订阅明确的 RSS、部委栏目和核心期刊。搜索继续用于补充专题证据与发现新源；不把 Google News 搜索 RSS 当作直接信源。

## 已接入来源与运行方式

`backend/app/sources.yaml` 独立维护采集入口，不与判断发布主体身份的 `source_publishers.yaml` 混用。

| 信源 | 方式 | 频率 |
| --- | --- | --- |
| 农业农村部市场与信息化司 · 信息化推进 | 栏目、文章正文、静态分页 | 每天 |
| 农业农村部科学技术司 · 工作动态 | 栏目、文章正文、静态分页 | 每天 |
| AgFunder News | 官方 RSS | 每 2 小时 |
| HortiDaily | 官方 RSS | 每 2 小时 |
| Seed World | 官方 RSS | 每 4 小时 |
| USDA ARS 农业研究 | 官方 RSS，限定研究新闻路径 | 每天 |
| Phys.org 农业科研 | 官方农业栏目 RSS | 每 4 小时 |
| ScienceDaily 农业与食品研究 | 官方 RSS，农业词预筛 | 每 4 小时 |
| Greenhouse Grower 温室技术 | 官方 RSS，技术词预筛 | 每 6 小时 |
| Growing Produce 果蔬种植技术 | 官方 RSS，技术词预筛 | 每 6 小时 |
| CABI PlantwisePlus 植物健康 | 官方 RSS | 每 12 小时 |
| 科学网科研新闻 | 全部新闻 RSS，农业词预筛、北京时间 | 每 30 分钟 |
| SciDev.Net 农业与发展研究 | 官方 RSS，农业词预筛 | 每 12 小时 |
| Nature Plants / Nature Food | 期刊 RDF RSS，DOI、作者、摘要 | 每 12 小时 |
| IRRI 正式新闻 | 官方 RSS，仅正式新闻路径 | 每 12 小时 |
| 当前关注面中的核心期刊 | Crossref 按 ISSN 获取元数据 | 每天 |

文件默认启用 **14 个 RSS、2 个部委栏目和默认 6 本期刊的 Crossref 补漏**，共 22 个采集入口，实际启用清单以后台保存的选择为准。另保存 FreshPlaza、爱荷华州立大学 RSS 为停用候选：入口可读，但项目采集器复测出现持续超时或 403。RSS 的入口与内容验证、未启用来源见 [RSS 扩充记录](rss-sources-2026-11-04.md)。

Crossref 使用后台关注面中的期刊配置，默认 6 本；不复制独立的期刊清单。OpenAlex 文献雷达继续运行，期刊 RSS 与两者通过规范化 DOI 合并。Crossref 先收录的占位摘要可在后续 OpenAlex / Agent 提供真实摘要时补齐；已存在的正文与真实摘要不会被薄元数据覆盖。Crossref 不保证提供摘要或全文，论文原文仍按现有手动获取流程处理。

中国农大、棉花所、环境保护科研监测所、《智慧农业》DOAJ 保留为停用候选，附待验证原因。`kind: candidate` 没有采集适配器，不能只改 `enabled` 就启用；需验证和实现详情、日期、分页后再接入。IRRI 已通过 RSS 的正式新闻路径过滤接入；总院反爬、CGIAR 失效 RSS 等不作为已接通来源。

worker 每分钟检查到期信源，执行 `sources_fetch` 任务。生产 API 进程只负责排队；本地单进程应用在 lifespan 启停同一调度器。每源采集后复用 `ingest_item`、正文获取、分类、评分和论文卡片流程。来源为官网不自动意味着文章是一手发布，仍执行现有内容证据判断；企业自述也不代表独立验证。

## 操作与状态

后台「任务 → 固定信源」可逐项启用、停用 RSS、部委栏目和 Crossref 期刊补漏源，开关自动保存；同页显示每个源的地址、频率、上次检查/成功时间、错误、过滤数和新增数，以及累计检查、失败次数和新增量。`can_toggle=false` 的来源尚未接入采集，页面禁用开关、接口拒绝启用；已有 RSS 适配的停用候选可由管理员手动启用，页面保留其访问验证说明。

开关按信源 ID 独立保存在数据库 `pipeline_state` 的 `source_enabled:<id>`，覆盖文件默认值，容器重建或 worker 重启后保留。自动调度、手动任务、正式 CLI 采集均读取这些选择；手动强制执行也不会绕过逐源停用。API 与 worker 直接读取数据库，不依赖跨进程缓存。

停用不删除内容或采集进度：任务在启动来源及读取下一页前检查开关，已开始读取的页面处理完成后暂停，之后启用可从保留的窗口和分页断点续跑。自动采集总开关开启时，重新启用的来源在下一次分钟检查时即可安排采集，无需等待原采集间隔。总开关仍在「配置」中；OpenAlex 文献订阅由「关注面」管理，关闭某期刊的 Crossref 补漏不等于取消其 OpenAlex 订阅。

管理员接口：`GET /api/v1/admin/sources` 返回清单、`enabled`、`can_toggle`、开关更新时间与采集状态；`PATCH /api/v1/admin/sources/{id}` 接收 `{"enabled": true}` 或 `{"enabled": false}`，返回保存后的 ID 和开关。未知 ID 返回 404，未接入来源或无效请求返回 422；仅允许修改开关，不接受 URL 等字段。既有 `POST /api/v1/admin/jobs/sources_fetch/run` 触发采集全部已启用来源。公开读取接口不变。

```bash
cd backend
# 真实源站只读预览：不初始化数据库、不写内容或断点、不调用评分。
.venv/bin/python -m scripts.fetch_sources --dry-run --limit 2
.venv/bin/python -m scripts.fetch_sources --dry-run --source-id crossref-0168-1699 --limit 2
# 部委栏目近期可能无更新；扩大初始预览窗口验证文章正文。
SOURCES_BOOTSTRAP_DAYS=90 .venv/bin/python -m scripts.fetch_sources --dry-run --source-id moa-informatization --limit 1
# 实际采集，初始化结构并沿用配置、后台关注面、入库和评分。
.venv/bin/python -m scripts.fetch_sources
.venv/bin/python -m scripts.fetch_sources --source-id agfunder
```

只读预览使用文件中的默认启用清单和期刊配置，不读取后台开关或数据库；实际采集使用后台启用选择和数据库关注面覆盖。`--source-id` 必须指向相应清单中的已启用来源；失败以非零状态退出。CLI 与部署 worker 不应同时执行实际采集，任务锁沿用当前单 worker 进程模型。

环境变量默认值：

```dotenv
SOURCES_FETCH_ENABLED=true
SOURCES_BOOTSTRAP_DAYS=7
SOURCES_LOOKBACK_DAYS=2
SOURCES_MAX_NEW_PER_SOURCE=20
```

`SOURCES_PATH` 可替换打包的 YAML；容器使用时需自行挂载文件并将变量传入 API 和 worker。持久化状态复用 `pipeline_state`，无需新增表或历史回填。升级后 worker 首次检查即开始采集；停用开关仅关闭自动调度，管理员仍可手动执行。

## 过滤、断点与限制

- RSS 校验 XML、官方主机、文章路径、明确发布日期和至少 40 字符的摘要；不将栏目页、测试页或仅有标题的条目入库。配置中的技术词与现有关注面预筛词共同筛选，招聘和明确行政活动标题先过滤，最终相关性、精选仍交给现有模型。
- 期刊 RSS 配置 `category: 论文`，要求明确 DOI，并保留发布者、作者与摘要；Nature 摘要前的期刊名、日期和 DOI 引用段落会先移除，防止把引文元数据当作摘要。论文来源标为 `rss`，后台可按「RSS 论文」筛选；评论、研究亮点等是否属原始研究仍依赖现有内容证据判断。
- RSS 中未带时区的时间按 `default_timezone` 解释，默认 UTC，科学网使用 `Asia/Shanghai`；显式时区优先。RSS 只有十几或几十条记录，科学网仅保留 20 条，故提高到每 30 分钟检查；停机期间被源站移除的记录无法靠当前 RSS 补齐。
- 部委栏目使用列表显示的日期（北京时间），不把 URL 中的上传日期当成原始发布时间；正文至少 200 字符才入库，区分政策文件与一般报道。每轮最多 5 页，完成页持久化后再翻页；失败页会重试，单篇失败仍可收录同页其他有效文章。
- Crossref 以 DOI 首次登记时间建立固定的起止窗口，避免论文出版日期回填造成漏采；保留论文实际出版日期，包括已登记的未来期次。使用游标分页，每页 50 条，整页完成才保存下一游标；无效游标重置后重放同一窗口。编辑委员会、目录等固定刊务条目被过滤。
- 每个源独立保存 `source:<id>` 状态。完整窗口成功才更新 `watermark`；失败和达到新建/页数上限均保留窗口，不跳到当前时间。记录逐篇提交，后续失败或评分失败不会撤回已保存内容。重跑通过 DOI、URL 和标题规则去重，已有部委 URL 不重复下载正文。
- RSS 只能覆盖源站当前保留的记录，部委分页也可能移动；无法承诺长时间停机后补齐所有历史。默认 2 天重叠窗口用于常见延迟，超出该窗口的补发需单独回溯。每源每轮最多新建 20 条；调高上限会增加现有评分与卡片调用量。

上线后一周在后台逐源观察失败率、正文获取、新增与过滤数，并抽查日期、分页和重复条目；“正常但零新增”需结合源站是否更新判断。启用第二批之前先完成同样验证。

## 验证

```bash
cd backend
.venv/bin/python -m pytest tests/test_sources.py tests/test_openalex.py tests/test_admin_console.py tests/test_pool_and_worker.py -q
```

覆盖重复运行、新建上限后续跑、HTTP/正文失败保留断点、分页中断、游标重置、RSS 压缩、非文章路径、真实日期、期刊 DOI 合并、摘要补齐、只读预览和调度开关；另验证后台逐源选择持久化、默认停用 RSS 启用、手动任务遵守停用、重新启用及时调度、采集中停用与断点恢复。真实源站只读验证使用上面的 `--dry-run`。
