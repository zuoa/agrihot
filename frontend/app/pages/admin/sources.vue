<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p class="text-sm text-stone-600">RSS 订阅、JSON 接口和 HTML 栏目都在这里管理。配置自动同步给采集任务。</p>
        <p class="mt-1 text-xs text-stone-500">已启用 {{ sources.filter(s => s.enabled).length }} / {{ sources.length }} 个信源 · <NuxtLink to="/admin/jobs" class="text-leaf-700 hover:underline">查看任务</NuxtLink></p>
      </div>
      <button type="button" :disabled="busy" class="rounded-lg bg-leaf-700 px-4 py-2 text-sm text-white hover:bg-leaf-800 disabled:opacity-50" @click="newSource">新增信源</button>
    </div>
    <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}</p>
    <p v-if="message" role="status" class="text-sm text-leaf-700">{{ message }}</p>
    <div class="grid items-start gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <section class="space-y-3">
        <input v-model="query" type="search" aria-label="搜索信源" placeholder="按名称或类型查找" class="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm">
        <p v-if="loading" class="py-6 text-center text-sm text-stone-500">正在加载信源…</p>
        <ul v-else class="max-h-[75vh] space-y-2 overflow-y-auto pr-1">
          <li v-for="s in filteredSources" :key="s.id" class="rounded-lg border bg-white p-3" :class="editingId === s.id ? 'border-leaf-600 ring-1 ring-leaf-600' : 'border-stone-200'">
            <button type="button" :disabled="busy" class="block w-full text-left disabled:opacity-60" @click="editSource(s)">
              <span class="block text-sm font-semibold text-stone-900">{{ s.name }}</span>
              <span class="mt-1 block truncate text-xs text-stone-400">{{ s.url }}</span>
            </button>
            <div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span class="rounded bg-stone-100 px-2 py-1 text-stone-600">{{ typeName(s.kind) }}</span>
              <span v-if="s.enabled && s.state.status === 'error'" class="text-red-600">采集失败</span>
              <button type="button" :disabled="busy || !s.can_toggle" class="ml-auto rounded border px-2.5 py-1 disabled:opacity-50" :class="s.enabled ? 'border-leaf-200 text-leaf-800' : 'border-stone-200 text-stone-500'" @click="toggleSource(s)">{{ s.enabled ? '已启用' : '已停用' }}</button>
              <button v-if="s.can_delete" type="button" :disabled="busy" class="rounded px-2 py-1 text-red-600 disabled:opacity-50" @click="deleteSource(s)">删除</button>
            </div>
          </li>
          <li v-if="!filteredSources.length" class="py-6 text-center text-sm text-stone-400">没有匹配的信源</li>
        </ul>
      </section>

      <section v-if="selectedSource && !selectedSource.can_edit" class="rounded-lg border border-stone-200 bg-white p-5">
        <h2 class="text-sm font-bold">{{ selectedSource.name }}</h2>
        <p class="mt-3 text-sm text-stone-500">这个期刊补漏源来自文献关注面，可在这里开关。期刊名称、ISSN 和目录在<NuxtLink to="/admin/watchlist" class="text-leaf-700 hover:underline">关注面</NuxtLink>中维护。</p>
      </section>
      <form v-else ref="editorElement" class="min-w-0 space-y-4 rounded-lg border border-stone-200 bg-white p-4 sm:p-5" @submit.prevent="saveSource">
        <h2 class="text-sm font-bold">{{ editingId ? '编辑信源' : '新增信源' }}</h2>
        <fieldset :disabled="busy" class="space-y-4 disabled:opacity-70">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs text-stone-500">名称<input v-model="form.name" required maxlength="200" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 text-sm"></label>
            <label class="block text-xs text-stone-500">采集方式<select v-model="form.kind" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm" @change="changeKind"><option value="rss">RSS / Atom</option><option value="json">JSON 接口 · JSONPath</option><option value="html">HTML 栏目 · XPath</option><option v-if="form.kind === 'moa'" value="moa">部委栏目（内置解析）</option><option v-if="form.kind === 'candidate'" value="candidate">待配置来源</option></select></label>
          </div>
          <label class="block text-xs text-stone-500">{{ form.kind === 'rss' ? 'RSS 地址' : form.kind === 'json' ? 'JSON GET 接口地址' : '栏目地址' }}<input v-model="form.url" type="url" required maxlength="2000" placeholder="https://example.org/feed.xml" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 text-sm"></label>
          <div class="grid gap-3 sm:grid-cols-3">
            <label class="block text-xs text-stone-500">检查间隔（分钟）<input v-model.number="form.interval_minutes" type="number" required min="1" max="10080" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 text-sm"></label>
            <label class="block text-xs text-stone-500">内容类型<select v-model="form.category" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm"><option>报道</option><option>政策</option><option>行业</option><option>论文</option></select></label>
            <label class="block text-xs text-stone-500">无时区日期使用<input v-model="form.default_timezone" required list="source-timezones" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 text-sm"><datalist id="source-timezones"><option value="UTC"></option><option value="Asia/Shanghai"></option></datalist></label>
          </div>
          <section v-if="isListSource" class="space-y-3 rounded-lg border border-stone-200 bg-stone-50 p-3">
            <div class="flex items-center justify-between gap-2"><h3 class="text-xs font-bold">{{ form.kind === 'json' ? 'JSONPath' : 'XPath' }} 字段映射</h3><button type="button" class="text-xs text-leaf-700" @click="form.parser = parserExample(form.kind)">填入示例规则</button></div>
            <p class="text-xs text-stone-500">{{ form.kind === 'json' ? '列表路径从整个响应取值；其余字段从每个条目取值。推荐列表路径返回数组。' : '条目 XPath 从整个页面选取文章；其余 XPath 相对每个条目取值。' }}</p>
            <label v-for="field in mappingFields" :key="field.key" class="block text-xs text-stone-500">{{ field.label }}<input v-model="form.parser[field.key]" :required="field.required || (field.key === 'doi' && form.category === '论文')" :placeholder="parserExample(form.kind)[field.key]" spellcheck="false" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 font-mono text-xs"></label>
            <label class="block text-xs text-stone-500">链接模板（可选，字段只有 ID 时使用）<input v-model="form.parser.url_template" placeholder="https://example.org/news/{value}" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 font-mono text-xs"></label>
            <label class="block text-xs text-stone-500">日期格式（可选）<input v-model="form.parser.date_format" placeholder="%Y年%m月%d日" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 font-mono text-xs"></label>
            <p class="text-xs text-stone-400">ISO 日期、秒和毫秒时间戳自动识别。摘要留空时会尝试读取原文正文。</p>
            <label class="block text-xs text-stone-500">分页<select v-model="pageMode" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm"><option value="none">单页列表</option><option value="next">从响应读取下一页链接</option><option value="page">递增 URL 中的页码参数</option></select></label>
            <label v-if="pageMode === 'next'" class="block text-xs text-stone-500">下一页 URL 路径（从整个响应取值）<input v-model="form.parser.next_page" required :placeholder="form.kind === 'json' ? '$.data.next_url' : '//a[@rel=&quot;next&quot;]/@href'" class="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 font-mono text-xs"></label>
            <div v-if="pageMode === 'page'" class="grid gap-2 sm:grid-cols-3">
              <label class="text-xs text-stone-500">页码参数名<input v-model="form.parser.page_parameter" required placeholder="page" class="mt-1 w-full rounded-md border border-stone-200 px-2 py-2 text-sm"></label>
              <label class="text-xs text-stone-500">起始页码<input v-model.number="form.parser.page_start" type="number" min="0" max="10000" class="mt-1 w-full rounded-md border border-stone-200 px-2 py-2 text-sm"></label>
              <label class="text-xs text-stone-500">每页条数<input v-model.number="form.parser.page_size" type="number" min="0" max="500" class="mt-1 w-full rounded-md border border-stone-200 px-2 py-2 text-sm"></label>
            </div>
            <p v-if="pageMode === 'page'" class="text-xs text-stone-400">每页条数用于判断末页，0 表示直到空页结束；接口的 pageSize 等参数请直接填写到采集地址中。列表按最新在前分页。</p>
          </section>
          <details class="rounded-lg border border-stone-200 p-3 text-xs text-stone-600" :open="isListSource">
            <summary class="cursor-pointer font-medium">原文范围与筛选</summary>
            <div class="mt-3 space-y-3">
              <label class="block">允许的原文域名（一行一个）<textarea v-model="form.hostsText" rows="3" placeholder="留空时使用采集地址的主机名" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 font-mono"></textarea></label>
              <label class="block">文章路径正则<input v-model="form.article_pattern" placeholder="^/.*$" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2 font-mono"></label>
              <label class="block">预筛词（一行一个，可留空）<textarea v-model="form.keywordsText" rows="3" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2"></textarea></label>
              <label class="block">备注<textarea v-model="form.note" rows="2" maxlength="2000" class="mt-1 w-full rounded-md border border-stone-200 px-3 py-2"></textarea></label>
            </div>
          </details>
          <label class="flex items-center gap-2 text-sm"><input v-model="form.enabled" type="checkbox" :disabled="form.kind === 'candidate'" class="accent-leaf-700">保存后启用采集</label>
          <div class="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-3">
            <button type="button" :disabled="form.kind === 'candidate'" class="rounded-lg border border-stone-200 px-3 py-2 text-sm hover:bg-stone-50 disabled:opacity-50" @click="previewSource">{{ action === 'preview' ? '正在读取…' : '测试解析' }}</button>
            <button type="submit" class="rounded-lg bg-leaf-700 px-4 py-2 text-sm text-white hover:bg-leaf-800">{{ action === 'save' ? '保存中…' : '保存信源' }}</button>
          </div>
        </fieldset>
        <section v-if="preview" class="space-y-3 border-t border-stone-200 pt-4" aria-live="polite">
          <h3 class="text-sm font-bold">解析预览</h3>
          <p class="text-xs text-stone-500">解析到 {{ preview.parsed }} 条，拒收 {{ preview.rejected }} 条，正文失败 {{ preview.failed || 0 }} 条，展示前 {{ preview.samples.length }} 条；本次没有入库或评分。</p>
          <p v-if="preview.next_page" class="break-all text-xs text-stone-500">下一页：{{ preview.next_page }}</p>
          <article v-for="(sample, i) in preview.samples" :key="i" class="rounded-md bg-stone-50 p-3">
            <a :href="sample.url" target="_blank" rel="noopener noreferrer" class="text-sm font-medium text-leaf-800 hover:underline">{{ sample.title }}</a>
            <p class="mt-1 text-xs text-stone-400">{{ sample.published_at }} · {{ sample.category }}</p>
            <p v-if="sample.error" class="mt-2 break-words text-xs text-red-600">{{ sample.error }}</p>
            <p class="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-stone-600">{{ sample.summary }}</p>
          </article>
        </section>
      </form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

definePageMeta({ layout: 'admin', title: '信源管理', middleware: 'admin-auth' })
const api = useApi()
const sources = ref([])
const query = ref('')
const loading = ref(true)
const action = ref('')
const busy = computed(() => !!action.value)
const error = ref('')
const message = ref('')
const editingId = ref(null)
const selectedSource = computed(() => sources.value.find(s => s.id === editingId.value))
const editorElement = ref(null)
const pageMode = ref('none')
const preview = ref(null)
const blankParser = () => ({ items: '', title: '', url: '', published_at: '', summary: '', content: '', doi: '', next_page: '', url_template: '', date_format: '', page_parameter: '', page_start: 1, page_size: 0 })
const blankForm = () => ({ name: '', kind: 'rss', url: '', enabled: false, interval_minutes: 240, category: '报道', default_timezone: 'UTC', article_pattern: '^/.*$', note: '', hostsText: '', keywordsText: '', parser: blankParser() })
const form = ref(blankForm())
const isListSource = computed(() => ['json', 'html'].includes(form.value.kind))
const filteredSources = computed(() => sources.value.filter(s => `${s.name} ${s.kind} ${s.url}`.toLowerCase().includes(query.value.toLowerCase())))
const mappingFields = [
  { key: 'items', label: '文章列表路径', required: true }, { key: 'title', label: '标题路径', required: true },
  { key: 'url', label: '原文链接 / ID 路径', required: true }, { key: 'published_at', label: '发布时间路径', required: true },
  { key: 'summary', label: '摘要路径（可选）' }, { key: 'content', label: '正文路径（可选）' }, { key: 'doi', label: 'DOI 路径（论文必填）' },
]

function typeName(kind) { return ({ rss: 'RSS', json: 'JSONPath', html: 'XPath', moa: '部委栏目', crossref: 'Crossref', candidate: '待配置' })[kind] || kind }
function parserExample(kind) {
  return { ...blankParser(), ...(kind === 'json'
    ? { items: '$.data.items', title: '$.title', url: '$.url', published_at: '$.published_at', summary: '$.summary' }
    : { items: '//ul[@class="news-list"]/li', title: './a', url: './a/@href', published_at: './time/@datetime', summary: './p/text()' }) }
}
watch(form, () => { preview.value = null }, { deep: true })
watch(pageMode, () => { preview.value = null })
function newSource() {
  if (busy.value) return
  editingId.value = null
  form.value = blankForm()
  pageMode.value = 'none'
  error.value = ''
  message.value = ''
}
function editSource(source) {
  if (busy.value) return
  error.value = ''
  message.value = ''
  preview.value = null
  editingId.value = source.id
  if (!source.definition) return
  const definition = JSON.parse(JSON.stringify(source.definition))
  form.value = { ...blankForm(), ...definition, enabled: source.enabled,
    article_pattern: definition.article_pattern || '^/.*$',
    parser: { ...blankParser(), ...definition.parser },
    hostsText: (definition.hosts || []).join('\n'), keywordsText: (definition.keywords || []).join('\n') }
  pageMode.value = form.value.parser.next_page ? 'next' : form.value.parser.page_parameter ? 'page' : 'none'
  error.value = ''
  message.value = ''
}
function changeKind() {
  form.value.parser = isListSource.value ? parserExample(form.value.kind) : blankParser()
  pageMode.value = 'none'
}
function definition() {
  const f = form.value
  const parser = isListSource.value ? { ...f.parser, next_page: pageMode.value === 'next' ? f.parser.next_page : '', page_parameter: pageMode.value === 'page' ? f.parser.page_parameter : '' } : blankParser()
  return { name: f.name, kind: f.kind, url: f.url, enabled: f.enabled, interval_minutes: f.interval_minutes,
    category: f.category, default_timezone: f.default_timezone, article_pattern: f.article_pattern || '^/.*$', note: f.note,
    hosts: f.hostsText.split('\n').map(s => s.trim()).filter(Boolean), keywords: f.keywordsText.split('\n').map(s => s.trim()).filter(Boolean), parser }
}
async function load() { sources.value = (await api.adminSources()).sources }
async function previewSource() {
  if (!editorElement.value?.reportValidity() || busy.value) return
  action.value = 'preview'; error.value = ''; message.value = ''; preview.value = null
  try { preview.value = await api.adminPreviewSource(definition()) }
  catch (e) { error.value = e.message }
  finally { action.value = '' }
}
async function saveSource() {
  if (busy.value) return
  action.value = 'save'; error.value = ''; message.value = ''
  try {
    const result = editingId.value ? await api.adminUpdateSource(editingId.value, definition()) : await api.adminCreateSource(definition())
    await load()
    editingId.value = result.id
    message.value = '信源已保存，采集任务会读取最新配置'
  } catch (e) { error.value = e.message }
  finally { action.value = '' }
}
async function toggleSource(source) {
  if (busy.value || !source.can_toggle) return
  action.value = 'toggle'; error.value = ''; message.value = ''
  try {
    await api.adminPatchSource(source.id, !source.enabled)
    await load()
    if (editingId.value === source.id) form.value.enabled = !source.enabled
    message.value = `${source.name}已${source.enabled ? '停用' : '启用'}`
  } catch (e) { error.value = e.message }
  finally { action.value = '' }
}
async function deleteSource(source) {
  if (busy.value || !confirm(`删除信源「${source.name}」？已收录的文章会保留。`)) return
  action.value = 'delete'; error.value = ''; message.value = ''
  try {
    await api.adminDeleteSource(source.id)
    await load()
    if (editingId.value === source.id) { editingId.value = null; form.value = blankForm(); pageMode.value = 'none' }
    message.value = '信源已删除，已收录的内容和历史进度保留'
  } catch (e) { error.value = e.message }
  finally { action.value = '' }
}
onMounted(async () => {
  try { await load() } catch (e) { error.value = e.message } finally { loading.value = false }
})
</script>
