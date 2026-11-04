# RSS 扩充记录（2026-11-04）

本轮新增启用 11 个 RSS（含原候选 IRRI 转为 RSS 接入），加上原有 AgFunder News、HortiDaily、Seed World，当前共启用 **14 个 RSS**。另保存 FreshPlaza、爱荷华州立大学为停用 RSS 候选，共维护 16 个 RSS 入口。

验证直接请求官方 RSS，并通过项目实际 XML 解析、文章主机与路径限制、发布日期和摘要检查；使用真实源站只读预览，不写文章、采集断点或调用评分。HTTP 200 只表示本次可访问，记录的条数是源站当时返回的记录数，不是最终入库量。

## 新增启用的入口

| 信源与官方 RSS | 本次返回 | 用途与筛选 |
| --- | --- | --- |
| [USDA ARS](https://www.ars.usda.gov/rss/) | 20 条 | 农业研究机构发布，限定 `/news-events/news/research-news/`；最近记录为 10 月 27 日，近一周无新增属正常情况 |
| [Phys.org 农业](https://phys.org/rss-feed/biology-news/agriculture/) | 30 条 | 农业科研新闻，含作物传感器、畜牧减排与育种 |
| [ScienceDaily 农业与食品](https://www.sciencedaily.com/rss/plants_animals/agriculture_and_food.xml) | 60 条 | 研究报道；栏目混有其他生物学内容，按农业词预筛 |
| [Greenhouse Grower](https://www.greenhousegrower.com/feed/) | 10 条 | 温室控制、灌溉、育种与生产技术，过滤一般企业人事与宣传消息 |
| [Growing Produce](https://www.growingproduce.com/feed/) | 10 条 | 果蔬栽培、植保、营养和装备技术，按技术词预筛 |
| [CABI PlantwisePlus](https://blog.plantwise.org/feed/) | 10 条 | 植物健康、综合虫害管理、农药风险与数字植保 |
| [科学网全部新闻](https://www.sciencenet.cn/xml/news-0.aspx?news=0) | 20 条 | 中文科研新闻，按农业词筛选；未标时区的时间按北京时间解释，每 30 分钟检查 |
| [SciDev.Net](https://www.scidev.net/global/rss.xml/?type=header) | 20 条 | 农业与发展相关研究；全站流先按文章路径及农业词筛选 |
| [Nature Plants](https://www.nature.com/nplants.rss) | 8 条 | 期刊 RDF RSS；保留明确 DOI、作者、日期和摘要，按农业相关词筛选 |
| [Nature Food](https://www.nature.com/natfood.rss) | 8 条 | 期刊 RDF RSS；农业、食品系统、碳排放等方向，按 DOI 与其他论文源合并 |
| [IRRI](https://www.irri.org/rss.xml) | 10 条，7 条为正式新闻路径 | 仅允许 `/news-and-events/news/`，实际排除 Home-Test、人员与项目介绍页 |

综合源或技术预筛较严格的源，当前窗口可能没有符合本项目方向的条目。科学网、SciDev.Net、Greenhouse Grower、Growing Produce 本次样本即出现零匹配，这不等于解析故障；不为增加收录数而放宽到无关内容。

Nature 的部分记录只有短说明或没有可用摘要，仍按至少 40 字符的规则拒收。期刊也会发布评论、研究亮点等内容，`category: 论文` 与 DOI 不单独证明原始研究，继续执行现有内容证据判断。期刊引用信息段先从摘要中移除，避免当作论文发现生成卡片。

## 没有启用的入口

| 候选 | 本轮结果与处理 |
| --- | --- |
| [FreshPlaza](https://www.freshplaza.com/rss.xml) | 首次返回可解析的 81 条，之后多次超时或 403；配置中保存为 `enabled: false`，待部署环境复核 |
| [爱荷华州立大学作物管理](https://crops.extension.iastate.edu/rss/rss.xml) | 普通客户端返回 10 条，但项目采集器复测持续连接超时；配置中保存为 `enabled: false`，并已限定技术文章路径以排除活动报名页 |
| [Cornell Food & Agriculture](https://news.cornell.edu/taxonomy/term/14247/feed) | 官网明确列出 RSS，但直接请求 403；暂不接入 |
| Precision Farming Dealer、Farm Equipment | 请求超时或 TLS 握手超时；暂不接入 |
| Future Farming、CropLife、AGDAILY | 超时、403 或 406；暂不接入 |
| [科学网 HOT 论文](https://www.sciencenet.cn/xml/news-0.aspx?di=8) | 返回 200，但最新记录停在 2018 年，改用仍在更新的全部新闻流 |
| [USDA ARS Research News 参数入口](https://www.ars.usda.gov/rss/?productName=Research%20News) | 虽由官网列出，当前返回的最新内容停在 2025 年 1 月；改用仍在更新的 `/rss/` 总流 |
| [USDA NASS](https://www.nass.usda.gov/rss/news.xml) | 可解析，最新记录停在 2025 年 9 月，暂不接入 |
| [ICARDA](https://icarda.org/rss.xml) | 返回的主要是 2019 年网站内容页，不是当前科研新闻，暂不接入 |
| CGIAR / CIMMYT、ILRI 的尝试入口 | 旧 RSS 失效、访问限制或 404，未列为可用来源 |

既有 HortiDaily 在本轮也出现超时或 403，保留原配置及现有逐源错误监测；源站访问限制可能随时间、出口与请求频率变化，不将此前成功解析等同于持续可用。

## 配置与验证

所有启用项及两项停用 RSS 候选都维护在 `backend/app/sources.yaml`，没有使用搜索结果 RSS、第三方 RSS 转换代理或登录凭据。

```bash
cd backend
.venv/bin/python -m scripts.fetch_sources --dry-run --source-id nature-food-rss --limit 2
.venv/bin/python -m scripts.fetch_sources --dry-run --source-id irri-news --limit 2
.venv/bin/python -m scripts.fetch_sources --dry-run --source-id sciencenet-news --limit 2
.venv/bin/python -m pytest tests/test_sources.py tests/test_admin_console.py tests/test_openalex.py -q
```

测试覆盖期刊 RDF 的 DOI / 作者 / 摘要、移除引文头、缺 DOI 拒收、与 Crossref 合并、中文时间、空 description 回退 content、IRRI 路径过滤，以及后台 RSS 论文筛选。上线后沿用逐源检查次数、失败次数、最近成功时间和新增量监测；无需新建表或修改公开读取接口。
