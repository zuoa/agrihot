# 论文 PDF 下载

站点清单见 [逐站核验 CSV](paper-pdf-site-audit.csv)。本次检查覆盖公开 feed 的 3,992 篇论文，分成 153 个直接域名及 488 个 DOI 注册前缀，共 641 组，全部取样尝试。样本中 31 组的原文链接直接返回 PDF，283 组发现 PDF 链接且核验了文件头；其余包括无明确 PDF 链接、站点拒绝访问、超时、验证码或 PDF 入口返回错误。[逐篇 DOI 落地清单](paper-pdf-doi-landings.csv)检查了全部 3,267 个 DOI，3,216 个解析成功，发现 525 个出版域名；未解析成功的 51 个保留了错误状态。[出版站点样本清单](paper-pdf-publisher-audit.csv)为 525 个域名逐站列出结果：27 个样本直接返回 PDF，295 个样本的 PDF 链接通过文件头核验，其余记录了访问失败或无入口等情况。三份清单均无待核验行。`pdf_header_verified` 只表示入口返回了 `%PDF-` 文件头，正式下载仍须验证整个文件。不同论文或未来的站点状态可能变化，可重跑 `scripts.audit_paper_pdfs`、`scripts.audit_doi_landings` 和 `scripts.audit_publisher_sites`。

下载器位于 `backend/app/services/paper_pdf.py`。插件按站点选择候选链接，通用插件读取 `citation_pdf_url` 和明确的 PDF 链接；arXiv、Nature、MDPI、Frontiers 与 aeeisp 补充各自的地址规则。aeeisp 的公开 PDF 地址对不同 HTTP 客户端响应不一致，因此只针对该站点增加受限下载回退；当前样本偶尔仍返回验证码，届时记录失败并等待重试。已知链接仍失败时，按 DOI 查询 OpenAlex 的开放获取 PDF 位置。候选文件须经过完整下载和 PDF 结构解析，才会保存。网页、验证码和错误页不会作为 PDF 入库。
MDPI 论文优先按 DOI 查询 Crossref 的期刊名、卷号和文章编号，再尝试该出版社公开的 `mdpi-res.com` PDF 地址；没有 DOI 的 MDPI 链接则用 URL 中的 ISSN、卷号、期号和文章编号查询 Crossref，并逐项核对返回记录后使用同一 CDN。这是其官网对云服务器返回 403 时的回退路径。Nature、Springer 返回 `Client Challenge` 网页时记录访问受限，不将网页保存为 PDF。

`fetch_paper_pdfs` 是独立后台任务：先恢复标记为 `pdf_file_missing` 的文件，再按 ID 断点扫描新旧论文；已有正文的论文也会尝试下载。恢复批次不推进普通扫描游标。每批最多 20 篇、同时最多 3 篇；失败最多自动重试 3 次，每次间隔至少 24 小时。管理员可在任务页运行批次，也可从论文详情页对单篇重新排队。状态记录在 `paper_pdfs`，文件以 SHA-256 为名存放在 `PAPER_PDF_DIR`；生产部署的 API 和 worker 共用 `paperpdfs` 卷。单文件最多 25 MiB，可通过 `PAPER_PDF_MAX_BYTES` 调整；下载总时限由 `PAPER_PDF_TIMEOUT` 控制，默认 180 秒。

页面只在文件已保存时显示站内“下载 PDF”。扫描件仍可供下载；没有文字层时不会把摘要写成全文。遇登录、付费、验证码或站点拒绝访问时保留失败原因，并继续保留原文链接。
