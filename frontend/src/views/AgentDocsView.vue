<template>
  <div class="space-y-8">
    <header>
      <h1 class="text-2xl font-bold text-stone-900">Agent 接入说明</h1>
      <p class="mt-2 text-sm text-stone-500 leading-6">
        AgriHot 面向爬虫 / 资讯聚合 Agent 开放推送接口。推送的内容经服务层自动去重后<strong class="text-leaf-700">直接上线</strong>，
        无需人工审核。本页包含全部接入细节，也适合作为 LLM Agent 的上下文直接阅读。
      </p>
      <div class="mt-3 flex gap-2 text-xs">
        <a href="/docs" target="_blank" class="px-3 py-1.5 rounded-full bg-leaf-600 text-white hover:bg-leaf-700">OpenAPI 交互文档 ↗</a>
        <a href="#dedup" class="px-3 py-1.5 rounded-full border border-leaf-200 text-leaf-700 hover:bg-leaf-50">去重规则</a>
        <a href="#examples" class="px-3 py-1.5 rounded-full border border-leaf-200 text-leaf-700 hover:bg-leaf-50">代码示例</a>
      </div>
    </header>

    <!-- 快速开始 -->
    <Section title="① 快速开始" id="quickstart">
      <ol class="text-sm text-stone-700 space-y-2 list-decimal list-inside leading-6">
        <li>向站点管理员申请 API Key（形如 <Code>agri_xxxxxxxx</Code>）。</li>
        <li>每次请求在 HTTP 头携带：<Code>X-API-Key: &lt;你的Key&gt;</Code>。</li>
        <li>向 <Code>POST {{ base }}/api/v1/ingest/items</Code> 提交 JSON，收到 <Code>created</Code> 即上线。</li>
      </ol>
      <CodeBlock lang="bash" :code="quickstart" />
    </Section>

    <!-- 认证 -->
    <Section title="② 认证方式" id="auth">
      <table class="w-full text-sm">
        <tbody class="divide-y divide-leaf-100">
          <tr><td class="py-2 pr-4 font-medium text-stone-600 w-32">请求头</td><td><Code>X-API-Key: &lt;key&gt;</Code></td></tr>
          <tr><td class="py-2 pr-4 font-medium text-stone-600">缺失 / 无效</td><td class="text-stone-700">返回 <Code>401</Code>（Problem JSON）</td></tr>
          <tr><td class="py-2 pr-4 font-medium text-stone-600">频率限制</td><td class="text-stone-700">每个 Key 60 次/分钟，超限返回 <Code>429</Code>，请指数退避重试</td></tr>
          <tr><td class="py-2 pr-4 font-medium text-stone-600">Key 管理</td><td class="text-stone-700">服务端只存 SHA-256 哈希；不同爬虫建议各用一个 Key 以便溯源</td></tr>
        </tbody>
      </table>
    </Section>

    <!-- 接口 -->
    <Section title="③ 推送接口" id="endpoints">
      <div class="space-y-3 text-sm">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-2 py-0.5 rounded bg-leaf-600 text-white text-xs font-bold">POST</span>
          <Code>/api/v1/ingest/items</Code>
          <span class="text-stone-500">推送单条</span>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-2 py-0.5 rounded bg-leaf-600 text-white text-xs font-bold">POST</span>
          <Code>/api/v1/ingest/items/batch</Code>
          <span class="text-stone-500">批量推送，body 为 <Code>{"items": [...]}</Code>，一次 ≤ 50 条</span>
        </div>
      </div>

      <h3 class="font-bold text-stone-800 mt-5 mb-2 text-sm">字段说明</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-xs border border-leaf-100 rounded-lg overflow-hidden">
          <thead class="bg-leaf-50 text-leaf-800">
            <tr>
              <th class="text-left px-3 py-2">字段</th><th class="text-left px-3 py-2">类型</th>
              <th class="text-left px-3 py-2">必填</th><th class="text-left px-3 py-2">说明</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-leaf-100 text-stone-700">
            <tr v-for="f in fields" :key="f.name">
              <td class="px-3 py-2 font-mono">{{ f.name }}</td>
              <td class="px-3 py-2 text-stone-500">{{ f.type }}</td>
              <td class="px-3 py-2"><span :class="f.req ? 'text-leaf-700 font-bold' : 'text-stone-400'">{{ f.req ? '是' : '否' }}</span></td>
              <td class="px-3 py-2 leading-5">{{ f.desc }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 class="font-bold text-stone-800 mt-5 mb-2 text-sm">响应（HTTP 200，逐条结果）</h3>
      <CodeBlock lang="json" :code="respExample" />
      <ul class="text-xs text-stone-600 space-y-1.5 mt-2 leading-5">
        <li><Code>created</Code> — 新条目，已直接上线，<Code>item_id</Code> 为条目 ID。</li>
        <li><Code>duplicate</Code> — 判定为重复，<strong>不是错误</strong>；信源已合并到 <Code>duplicate_of</Code> 指向的条目。</li>
        <li><Code>invalid</Code> — 该条入库失败（批量模式下不影响其他条目）。</li>
      </ul>
    </Section>

    <!-- 去重规则 -->
    <Section title="④ 去重规则（服务层自动执行）" id="dedup">
      <div class="space-y-4 text-sm text-stone-700 leading-6">
        <div class="rounded-xl border border-leaf-200 bg-leaf-50/50 p-4">
          <div class="font-bold text-leaf-800 mb-1">第 1 级 · URL 精确去重 <Code>exact_url</Code></div>
          URL 先做规范化（去除 utm_*/from/ref 等追踪参数、统一协议与大小写、去锚点与末尾斜杠），再取 SHA-256。
          哈希已存在 → 判重。同一篇文章带不同追踪参数重复推送会被识别为同一条。
        </div>
        <div class="rounded-xl border border-leaf-200 bg-leaf-50/50 p-4">
          <div class="font-bold text-leaf-800 mb-1">第 2 级 · 标题相似去重 <Code>similar_title</Code></div>
          标题清洗（去标点空白、全角转半角）后计算 64 位 SimHash，与近 30 天条目比较：
          海明距离 ≤ 6，或标题互相包含（如「…指导意见」与「…指导意见（全文）」）→ 判重。
        </div>
        <div class="rounded-xl border border-leaf-200 bg-leaf-50/50 p-4">
          <div class="font-bold text-leaf-800 mb-1">第 3 级 · 合并而非拒绝</div>
          判重后推送<strong>不会被丢弃</strong>：新信源会并入已有条目的信源列表（前端展示「N 个信源同时报道」），
          热度随之提升。<strong>幂等安全</strong>：网络超时后原样重推即可，不会产生重复条目。
        </div>
        <p class="text-xs text-stone-500">提示：想让自己的信源出现在「多信源报道」里，请填好 <Code>source_name</Code> 与 <Code>source_url</Code>。</p>
      </div>
    </Section>

    <!-- 错误码 -->
    <Section title="⑤ 状态码与错误格式" id="errors">
      <table class="w-full text-sm">
        <tbody class="divide-y divide-leaf-100 text-stone-700">
          <tr><td class="py-2 pr-4 font-mono w-20">200</td><td>成功（含 duplicate 结果）</td></tr>
          <tr><td class="py-2 pr-4 font-mono">401</td><td>缺少或无效 API Key</td></tr>
          <tr><td class="py-2 pr-4 font-mono">422</td><td>字段校验失败（缺 title/url/summary、summary 过短等）</td></tr>
          <tr><td class="py-2 pr-4 font-mono">429</td><td>超出频率限制，稍后重试</td></tr>
        </tbody>
      </table>
      <p class="text-xs text-stone-500 mt-3">错误统一为 Problem JSON：<Code>{"title": "...", "status": 401, "detail": "..."}</Code></p>
    </Section>

    <!-- 示例 -->
    <Section title="⑥ 代码示例" id="examples">
      <h3 class="font-bold text-stone-800 mb-2 text-sm">Python（httpx）</h3>
      <CodeBlock lang="python" :code="pyExample" />
      <h3 class="font-bold text-stone-800 mt-5 mb-2 text-sm">批量推送（curl）</h3>
      <CodeBlock lang="bash" :code="batchExample" />
    </Section>

    <!-- 最佳实践 -->
    <Section title="⑦ 最佳实践" id="best-practices">
      <ul class="text-sm text-stone-700 space-y-2 list-disc list-inside leading-6">
        <li><strong>直接推原始 URL 即可</strong>，无需自行去追踪参数，服务端会规范化。</li>
        <li><strong>失败/超时请原样重试</strong>，接口幂等，重复推送只会合并信源。</li>
        <li>批量优于单条：一轮抓取打包成 ≤50 条一次推送，减少请求数。</li>
        <li><Code>published_at</Code> 用 ISO 8601 带时区（如 <Code>2026-07-15T08:00:00+08:00</Code>），缺省时按收录时间排序。</li>
        <li><Code>category</Code> 建议用 <Code>政策 / 报道 / 论文 / 行业</Code>，其他值会归为「报道」。</li>
        <li>摘要 ≥ 10 字、标题 ≥ 4 字，否则会被 422 拒绝。</li>
        <li>遵守 60 次/分钟限制；收到 429 时指数退避（1s → 2s → 4s…）。</li>
      </ul>
    </Section>
  </div>
</template>

<script setup>
import { h } from 'vue'

const base = window.location.origin

const Section = (props, { slots }) =>
  h('section', { id: props.id, class: 'bg-white rounded-2xl border border-leaf-100 p-5 sm:p-6' }, [
    h('h2', { class: 'text-lg font-bold text-leaf-800 mb-4' }, props.title),
    slots.default(),
  ])
Section.props = ['title', 'id']

const Code = (props, { slots }) =>
  h('code', { class: 'px-1.5 py-0.5 rounded bg-leaf-50 text-leaf-800 text-[0.85em] font-mono border border-leaf-100' }, slots.default())

const CodeBlock = (props) =>
  h('div', { class: 'relative mt-3' }, [
    h('span', { class: 'absolute top-2 right-3 text-[10px] text-stone-400 font-mono' }, props.lang),
    h('pre', { class: 'rounded-xl bg-stone-900 text-leaf-100 text-xs leading-5 p-4 overflow-x-auto font-mono whitespace-pre' }, props.code),
  ])
CodeBlock.props = ['lang', 'code']

const fields = [
  { name: 'title', type: 'string', req: true, desc: '标题，4–500 字' },
  { name: 'url', type: 'string', req: true, desc: '原文链接，去重主键（规范化后比对）' },
  { name: 'summary', type: 'string', req: true, desc: '摘要，≥10 字；论文建议附原文标题与作者' },
  { name: 'source_name', type: 'string', req: false, desc: '信源名称，如「农民日报」；多信源合并时展示' },
  { name: 'source_url', type: 'string', req: false, desc: '信源首页/出处链接' },
  { name: 'published_at', type: 'datetime', req: false, desc: '原文发布时间（ISO 8601 带时区）' },
  { name: 'category', type: 'string', req: false, desc: '政策 / 报道 / 论文 / 行业，缺省归「报道」' },
  { name: 'tags', type: 'string[]', req: false, desc: '标签数组，≤20 个，如 ["智慧农业","遥感"]' },
  { name: 'cover_url', type: 'string', req: false, desc: '封面图 URL' },
  { name: 'content', type: 'string', req: false, desc: '正文（可选，详情页展示）' },
  { name: 'lang', type: 'string', req: false, desc: '语种标记，如 zh / en' },
]

const quickstart = `# 推送第一条资讯
curl -X POST ${base}/api/v1/ingest/items \\
  -H "X-API-Key: <你的APIKey>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "8项农业人工智能标准立项获批 智慧农业迎来标准时刻",
    "url": "https://example.com/news/20260714-ai-standards",
    "summary": "2026年第二批农业国家和行业标准制修订计划中，8项农业人工智能相关行业标准获立项，覆盖农业机器人、农业农村大模型等领域。",
    "source_name": "示例信源",
    "published_at": "2026-07-14T09:00:00+08:00",
    "category": "政策",
    "tags": ["农业人工智能", "行业标准"]
  }'

# → {"status":"created","item_id":20,"message":"已收录并直接上线"}`

const respExample = `// 单条响应
{
  "status": "duplicate",          // created | duplicate | invalid
  "item_id": 19,
  "duplicate_of": 19,             // 重复时指向已有条目
  "dup_reason": "similar_title",  // exact_url | similar_title
  "message": "与已有条目「…」标题相似，信源已合并"
}

// 批量响应
{ "total": 3, "created": 2, "duplicate": 1, "invalid": 0,
  "results": [ /* 每条同上 */ ] }`

const pyExample = `import httpx

API = "${base}/api/v1/ingest/items"
KEY = "<你的APIKey>"

def push(item: dict) -> dict:
    r = httpx.post(API, json=item, headers={"X-API-Key": KEY}, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("限流，退避后重试")
    r.raise_for_status()
    return r.json()

result = push({
    "title": "全国智慧农业现场会在江苏召开",
    "url": "https://example.com/news/smart-agri-conf?utm_source=rss",  # 追踪参数无需处理
    "summary": "全国智慧农业现场会在江苏南京召开，展示农业机器人、AI农情监测等新技术。",
    "source_name": "我的爬虫",
    "category": "报道",
    "tags": ["智慧农业", "农业机器人"],
})
# 幂等：超时后原样重推不会生成重复条目
print(result["status"], result.get("item_id") or result.get("duplicate_of"))`

const batchExample = `curl -X POST ${base}/api/v1/ingest/items/batch \\
  -H "X-API-Key: <你的APIKey>" \\
  -H "Content-Type: application/json" \\
  -d '{"items": [
    {"title": "…", "url": "https://a.example/1", "summary": "……（≥10字）"},
    {"title": "…", "url": "https://a.example/2", "summary": "……（≥10字）"}
  ]}'`
</script>
