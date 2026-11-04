# 关注点、一手来源与事件进展

文章的「关注点」说明具体信息增量与阅读价值，独立于摘要和评分简评。卡片显示最多两行，详情显示完整内容，最多120字；没有充分材料时不显示。

## 来源与人工编辑

一手来源分为政策原文、原始研究、原始数据或报告、主体公告。`backend/app/source_publishers.yaml`维护发布身份的域名规则，匹配完整域名及其子域名，不接受伪造后缀。匹配只证明发布身份；自动标识还要求模型判断内容属于原始发布，并提供与已收录材料逐字匹配的摘录。政府网站转载、政策解读、媒体引用、论文综述和证据不足的内容不标记；DOI本身不证明原始研究。企业自述不表示效果经过独立验证。

评分在原有一次DeepSeek请求中同时生成关注点及来源判断，不另开模型请求。新字段异常不影响评分；旧评分简评不自动转换为关注点。需要扩展来源时增加经过核实的域名及允许的资料类型，不能只按机构名称或政府后缀授予标识。

后台内容编辑支持修改、清空及分别锁定关注点与来源判断；重评分保留锁定结果。原文链接、标题、摘要、正文、来源、发表日期、分类或DOI变化后，旧信息隐藏并保留内部待核对记录。人工核对后可重新确认；模型调用期间若有人修改事实或锁定内容，过期结果不能覆盖新编辑。合并的其他信源不改变当前文章的来源标识。

公开文章完整、精简及Agent/MCP输出新增：

- `attention_point`：字符串或null。
- `source_provenance`：`status=primary|unknown`、`type=policy|research|report|announcement|null`、`label`、`explanation`。

后台通过`GET /api/v1/admin/items/{id}/editorial`查看判定依据和锁定状态；`PATCH /api/v1/admin/items/{id}`的`editorial`对象可修改`attention_point`、`source_provenance.type`、`attention_locked`、`provenance_locked`。内部摘录及锁定信息不随公开文章返回，精简列表的SQL也不读取内部依据、正文或评分明细。

## 事件专题

仅`event`专题增强时间线，`research`保留研究比较。详情先看速览与最新进展，再看时间线及关键发现；默认最新在前、显示5条，可切换顺序或展开当前版本全部节点。当前版本最多保留最新15个关键进展，旧版本仍保存历史内容。

`document.timeline`沿用`date`和`claim`，新增稳定`id`、简短`title`及`date_basis=event|published|unknown`。`event`日期须在所引摘录中有完整日期依据；否则使用来源发表日期（业务时区），不能用入库日期。`unknown`用于兼容历史文档，界面只标「日期」。

生成时输入上一发布版本的节点，同一进展的转载及改写沿用ID，只为新决定、新数据、新结果创建节点。仍有有效引用的历史节点被保留，失效节点不能继续提供事实依据。模型输出、引用、日期和连续性沿用程序校验及独立审查；失败保留原有效版本。

专题摘要新增`latest_progress`，详情同时提供完整节点和`new_progress_ids`。首次建立时间线不把所有节点标成「本次新增」；后续更新区分新增报道数量与新增进展数量。现有每日10:00调度保持不变。文章的关注点、来源标识及阅读次数变更不会使专题事实引用失效。

## 历史补全与升级

启动时由现有`ensure_schema`添加三个可空字段，不自动触发模型或历史重评分。API和worker应使用同版本镜像。首次升级后先预览，再小批补全：

```bash
cd backend
.venv/bin/python -m scripts.editorial_backfill --dry-run --limit 20
.venv/bin/python -m scripts.editorial_backfill --batch-id editorial-v1 --limit 20
# 使用相同batch-id继续；失败项会重试，成功项不重复处理
.venv/bin/python -m scripts.editorial_backfill --batch-id editorial-v1 --limit 20
```

预览只读取数据库，不调用模型、不写断点。实际补全需要`DEEPSEEK_API_KEY`，默认覆盖近30天精选和当前发布专题关联文章；每次最多20篇，可用`--limit`调整至1–1000。保留人工锁定，不改评分、精选、主题或标签。批次起始时间和游标持久化；需要重新扫描已走过的文章时使用新batch-id。

后台「任务 → 补全关注点与一手来源」默认只预览；取消勾选后执行小批补全。生产API只排队，由现有worker执行。任务详情记录生成、跳过、失败及模型用量，不记录密钥或完整模型响应。

已发布事件专题用现有后台「重新生成」升级时间线；即使资料未变化，旧生成版本也会升级一次。被锁定的综合内容不自动覆盖，旧版本始终兼容读取。

## 验证

```bash
cd backend
DATABASE_URL=sqlite+aiosqlite:////tmp/agrihot_test.db .venv/bin/python -m pytest -q
cd ../frontend
npm test
npm run build
```

浏览器验收使用独立样例数据库和本机Chrome，检查宽屏、窄屏、排序展开、引用跳转和人工编辑；不使用模拟器。单元与集成测试覆盖来源误标、原文变更、并发人工编辑、补全预览/续跑/重试、时间线连续性及既有发布回退。模型内容质量需要结合真实资料抽样判断，引用逐字匹配本身不等于结论已获事实认证。
