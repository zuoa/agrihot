# Agent 推送接入

内部爬虫 / 资讯聚合 Agent 使用推送专用 Key 提交内容。服务层自动去重后直接上线，
新条目经过相关性判断和多维评分，当天达阈值且评分最高的前 5 篇进入精选。
推送专用 Key 与公开 Agent 读取 Key 分开授权。

## 快速开始

在后台「API Key」签发用途为「推送」的 Key。每次请求携带 `X-API-Key`。

```bash
curl -X POST https://agrihot.com/api/v1/ingest/items \
  -H 'X-API-Key: <你的推送Key>' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "农业人工智能相关行业标准立项获批",
    "url": "https://example.com/news/agri-ai-standards",
    "summary": "新一批农业行业标准制修订计划覆盖农业机器人、农情监测与农业人工智能应用。",
    "source_name": "示例信源",
    "published_at": "2026-10-22T09:00:00+08:00",
    "category": "政策",
    "tags": ["农业人工智能", "行业标准"]
  }'
```

收到 `created` 即已收录上线。HTTP 401 表示 Key 缺失、无效或已停用；读取 Key 推送会返回 403。
默认每个推送 Key 每分钟 60 次，HTTP 429 时请指数退避重试。服务端只存 Key 的 SHA-256 哈希。

## 接口

| 方法 | 地址 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/ingest/items` | 单条推送 |
| POST | `/api/v1/ingest/items/batch` | 批量推送，`{"items": [...]}`，最多 50 条 |
| DELETE | `/api/v1/ingest/items/{id}` | 删除内容，并清理日报引用及召回索引；需要推送 Key |

## 字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 | 标题，4–500 字 |
| url | string | 是 | 原文 URL，最多 2000 字符；论文优先 DOI 链接 |
| summary | string | 是 | 摘要，至少 10 字；外文论文可用原始摘要 |
| source_name | string | 否 | 信源名，最多 200 字 |
| source_url | string | 否 | 信源首页 / 出处链接 |
| published_at | datetime | 否 | 原文发布时间，使用带时区 ISO 8601 |
| category | string | 否 | 政策 / 报道 / 论文 / 行业；缺省或其他值归为报道 |
| tags | string[] | 否 | 独立短主题数组，如 `["智慧农业","遥感"]`；不要拼成整句 |
| cover_url | string | 否 | 封面图 URL |
| content | string | 否 | Markdown 正文；缺失时非论文条目可由服务端补抓 |
| lang | string | 否 | 可选语种标记 |
| doi | string | 否 | 论文 DOI，去除 doi.org 前缀并规范化；未填时可从 DOI URL 提取 |

`published_at` 仅表示原文日期；公开列表和 Agent 时间范围按收录时间 `created_at`。
服务端会切开拼接标签；评分后按正文重写 3–6 个主题，原始 tags 只作兜底。
长尾 `search_phrases` 由评分生成，不作为 Tag 入库。

## 响应

```json
{
  "status": "duplicate",
  "item_id": 19,
  "duplicate_of": 19,
  "dup_reason": "similar_title",
  "message": "与已有条目标题相似，信源已合并"
}
```

- `created`：新建成功，`item_id` 为新条目 ID。
- `duplicate`：重复不是错误，信源已合并；`duplicate_of` 指向已有条目。
- `invalid`：该条失败，批量中不影响其他条目。

批量响应包含 `total`、`created`、`duplicate`、`invalid` 及逐条 `results`。
字段校验失败返回 422。错误正文的 `detail` 包含具体错误信息。

## 自动去重

- DOI / OpenAlex ID 精确去重：相同论文的出版社、DOI 与 OpenAlex 页面合并为一条。
- URL 精确去重：规范化 URL，去追踪参数和锚点，统一协议与大小写，取 SHA-256；返回 `exact_url`。
- 标题近似去重：清洗后计算 SimHash，与近 30 天条目比较，海明距离 ≤ 6 或标题互相包含时合并；返回 `similar_title`。
- 重复推送合并信源与热度，网络超时后可原样重试。填写准确的 `source_name`、`source_url` 便于展示多信源报道。

## Python 示例

```python
import os
import httpx

response = httpx.post(
    "https://agrihot.com/api/v1/ingest/items",
    headers={"X-API-Key": os.environ["AGRIHOT_PUSH_KEY"]},
    json={
        "title": "全国智慧农业现场会在江苏召开",
        "url": "https://example.com/news/smart-agri-conf",
        "summary": "会议展示农业机器人、人工智能农情监测等技术在农业生产中的应用。",
        "source_name": "我的爬虫",
        "category": "报道",
        "tags": ["智慧农业", "农业机器人"],
    },
    timeout=30,
)
response.raise_for_status()
print(response.json())
```

批量优于逐条调用。摘要和正文尽量完整，避免把关键词、日期或整条标题当作标签。
