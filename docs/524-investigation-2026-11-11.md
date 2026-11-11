# agrihot.com 524 排查记录（2026-11-11）

## 现场证据

本站 DNS 接入腾讯云 EdgeOne，响应头出现 `eo-log-uuid`、`eo-cache-status`。EdgeOne 的 524 表示节点已经连接源站，但源站没有在应答超时时间内返回数据；默认 HTTP 应答超时为 15 秒。[腾讯云排障文档](https://cloud.tencent.com/document/product/1552/118268)、[回源超时说明](https://cloud.tencent.com/document/product/1552/104992)。

从工作站经 EdgeOne 两条 IPv4 节点抽样：

| 路径 | 观测 | 用途 |
| --- | --- | --- |
| `/` | 一次 200，TTFB 16.2 秒，`eo-cache-status: MISS`；另一次 20 秒无响应 | SSR / 缓存回源 |
| `/api/health` | 一次 200，TTFB 15.8 秒；另一次 31.3 秒后返回 `HTTP/2 524`、`server: TencentEdgeOne`、`eo-log-uuid: 17330357931540160754` | Nuxt 代理 → FastAPI，不访问数据库 |
| `/robots.txt` | 一次 200，TTFB 14.9 秒 | Nuxt 代理 → FastAPI |
| `/feed`、`/api/v1/items?...`、`/api/v1/specials/featured` | 22 秒内无响应 | SSR / 数据库链路 |
| `/favicon.svg` | 首次 22 秒无响应；缓存命中时 1–2 秒返回，`eo-cache-status: HIT` | Nuxt 静态资源，不访问 FastAPI |

TLS 握手约 0.6–1 秒完成，之后一直等待 HTTP 首字节。静态资源和无需数据库的健康接口也慢，不能仅归因于文章列表 SQL。缓存命中能绕开慢回源。现有采样无法区分源站 Nginx、Nuxt 进程、源站网络或 EdgeOne 到源站的链路，需要以下源站侧对照。不要把 EdgeOne 节点 IP 当作源站 IP。

## 已在代码中处理

- 生产 API 不再运行文献拉取、日报生成定时任务；管理后台 `/jobs` 发起的长任务统一交给现有 worker 队列。避免这些任务占用 API 进程的事件循环和数据库连接池。单容器本地模式继续自行运行定时任务。旧版同步管理接口仍需单独迁移，普通访客不会调用这些接口。
- 后端重启时的 DOI 历史回填只读取 ID 和链接列，再批量更新命中的记录，避免每次启动加载所有未写 DOI 文章的正文及关联表。该改动缩短重启期间 API 不可用的窗口。
- FastAPI 响应增加 `Server-Timing: api;dur=...`，超过 1 秒的请求记录路径、状态和应用耗时；异常也记录耗时。日志不记录查询字符串或认证信息。
- Nuxt 增加不访问后端的 `/healthz`，响应含 `X-Agrihot-Layer: frontend` 和 `Cache-Control: no-store`。与 `/api/health` 配合判断卡在哪一层。
- Docker 的前端健康检查改用 `/healthz`，避免首页 SSR / 后端短暂变慢时误判 Nuxt 进程自身异常；仍须单独监测公开首页和 API。

这些改动需要同时更新 backend 和 frontend 镜像并在源站执行 `docker compose pull && docker compose up -d` 后才对线上生效。旧 API 与新 worker 短时共存可能让定时任务在两个进程各跑一次，升级时应尽量在同一轮重建两者。

## 源站侧定位

在部署机的 `deploy/` 目录执行。先记录故障的北京时间、请求路径和 `eo-log-uuid`；将工作站的公开域名请求与源站本机请求在同一分钟对照：

```bash
curl -sS -D - -o /dev/null -w 'public code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n' --max-time 25 https://agrihot.com/api/health
curl -sS -D - -o /dev/null -w 'nuxt code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n' --max-time 10 http://127.0.0.1:5820/healthz
curl -sS -D - -o /dev/null -w 'proxy code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n' --max-time 10 http://127.0.0.1:5820/api/health
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read().decode())"
docker compose ps
docker stats --no-stream
docker compose logs --since 30m --tail 300 frontend backend worker db
```

如果本机 `healthz` 慢，重点查源站 Nginx → 5820 连接、Nuxt CPU/内存/重启和容器日志。如果 `healthz` 快而本机 `/api/health` 慢，重点查 Nuxt 代理 → FastAPI；若直接请求 backend 也慢，查 FastAPI 事件循环和容器资源。如果本机三个都快，公开域名仍慢，查看 Nginx 访问日志和 EdgeOne 回源配置、安全策略与网络；按腾讯云文档用**实际源站 IP、协议、端口及 Host**做 `curl --resolve` 直连对照。若源站 Nginx 没收到对应请求，排查 EdgeOne 回源链路/防火墙，并用 `eo-log-uuid` 请求腾讯云定位回源节点。

源站 Nginx 访问日志应至少包含 `$request_time`、`$upstream_connect_time`、`$upstream_header_time`、`$upstream_response_time`、`$status`、`$upstream_status`、`$request_uri`。不要只看容器健康状态：当前静态资源也存在回源超时，且容器健康检查只能证明一次本机请求成功。后端应用日志中的 `duration_ms` 与 Nginx 的 `upstream_response_time` 可进一步区分应用内部与前置等待。

若怀疑数据库压力，在故障时查看 PostgreSQL 活动和等待，而非只查空闲时的平均值：

```bash
docker compose exec -T db psql -U agrihot -d agrihot -c "select state, wait_event_type, wait_event, count(*) from pg_stat_activity where datname = 'agrihot' group by 1,2,3 order by 4 desc;"
docker compose exec -T db psql -U agrihot -d agrihot -c "select pid, now()-query_start as age, state, wait_event_type, left(query, 160) as query from pg_stat_activity where datname = 'agrihot' and state <> 'idle' order by age desc limit 20;"
```

## 处理优先级

1. 查源站 CPU、内存、容器重启和 Nginx 上游耗时，先恢复 `/healthz` 与 `/api/health` 的稳定首字节。部署本次任务隔离改动，再在定时采集时段和正常时段分别复测。
2. EdgeOne 对指纹静态资源和公开可缓存页面设置合适缓存规则，核实 `eo-cache-status: HIT` 的比例。管理接口、健康接口、阅读计数等动态操作不缓存。缓存只能减轻回源请求量，不能替代源站修复。
3. 仅当源站直连稳定、确有合法请求超过 15 秒时，再按业务路径调整 EdgeOne HTTP 应答超时；优先把长任务异步化。直接把全站超时加到 60 秒会让普通访客等待更久，无法解决静态资源回源慢。

部署后目标：源站本机 `/healthz` 和 `/api/health` 稳定低于 1 秒；公开域名缓存未命中的健康接口也应稳定返回，且后端 `Server-Timing` 与 Nginx 上游耗时能解释差值。若仍出现 524，需要对应时间的源站 Nginx 日志、容器资源/日志与 `eo-log-uuid` 才能定责。
