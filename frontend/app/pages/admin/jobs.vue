<template>
  <div class="space-y-4">
    <p class="text-sm text-stone-500">长任务在后台执行。同一任务不会重叠；进行中请等待完成后再点。</p>
    <p v-if="error" class="text-xs text-red-600">{{ error }}</p>

    <div class="grid md:grid-cols-2 gap-3">
      <article v-for="j in jobs" :key="j.name" class="bg-white border border-stone-200 rounded-lg p-4 flex flex-col gap-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-sm font-bold text-stone-900">{{ j.label }}</h2>
            <p class="text-xs text-stone-400 mt-0.5">{{ hint(j.name) }}</p>
          </div>
          <JobBadge :status="j.status" />
        </div>
        <div class="text-xs text-stone-500 space-y-1 min-h-[2.5rem]">
          <div v-if="j.progress">进度 {{ j.progress.done }} / {{ j.progress.total }}</div>
          <div v-if="j.error" class="text-red-600">{{ j.error }}</div>
          <div v-else-if="j.stats">{{ formatStats(j) }}</div>
          <div v-if="j.finished_at">上次完成 {{ fmtWhen(j.finished_at) }}</div>
          <div v-else-if="j.logs?.length">最近进展：{{ j.logs[j.logs.length - 1].message }}</div>
        </div>
        <details v-if="j.logs?.length" class="min-w-0 border-t border-stone-100 pt-3 text-xs">
          <summary class="cursor-pointer text-leaf-700">执行详情（{{ j.logs.length }} 条）</summary>
          <p class="mt-2 text-stone-400">保留本次执行最近 100 条记录；失败输出保留开头和结尾片段。</p>
          <ol class="mt-3 max-h-96 overflow-y-auto space-y-3 pr-1" :aria-label="`${j.label}执行记录`">
            <li v-for="(entry, index) in j.logs" :key="`${entry.at}-${index}`" class="min-w-0">
              <div class="flex flex-wrap gap-x-2 gap-y-1 text-stone-400">
                <time :datetime="entry.at">{{ fmtLogTime(entry.at) }}</time>
                <span>{{ stages[entry.stage] || entry.stage }}</span>
                <span v-if="entry.level === 'error'" class="text-red-600">错误</span>
                <span v-else-if="entry.level === 'warning'" class="text-amber-700">提醒</span>
              </div>
              <p class="mt-1 whitespace-pre-wrap break-words" :class="entry.level === 'error' ? 'text-red-700' : 'text-stone-700'">{{ entry.message }}</p>
              <p v-if="entry.details?.title" class="mt-1 break-words text-stone-500">{{ entry.details.special_id ? `#${entry.details.special_id} · ` : '' }}{{ entry.details.title }}</p>
              <p v-if="logMetrics(entry.details)" class="mt-1 break-words text-stone-500">{{ logMetrics(entry.details) }}</p>
              <details v-if="entry.details" class="mt-1">
                <summary class="cursor-pointer text-stone-500">诊断数据与输出片段</summary>
                <pre class="mt-2 max-h-64 overflow-y-auto rounded bg-stone-50 p-2 whitespace-pre-wrap break-words text-[11px] text-stone-600">{{ JSON.stringify(entry.details, null, 2) }}</pre>
              </details>
            </li>
          </ol>
        </details>
        <div class="mt-auto flex items-center gap-2">
          <label v-if="j.name === 'editorial_backfill'" class="text-xs text-stone-600 flex items-center gap-1"><input v-model="editorialPreview" type="checkbox">只预览</label>
          <input v-if="j.name === 'daily_generate'" v-model="dailyDate" type="date"
            class="px-2 py-1 text-xs rounded border border-stone-200" />
          <router-link v-if="j.name === 'fetch_content'" to="/admin/items?has_content=false"
            class="px-3 py-1.5 text-xs rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50">
            去内容页勾选
          </router-link>
          <button :disabled="['running', 'queued'].includes(j.status) || busy === j.name"
            @click="run(j)"
            class="ml-auto px-3 py-1.5 text-xs rounded-md bg-leaf-700 text-white hover:bg-leaf-800 disabled:opacity-40">
            {{ j.status === 'running' ? '运行中…' : j.status === 'queued' ? '排队中…' : '立即执行' }}
          </button>
        </div>
      </article>
    </div>
    <section class="rounded-lg border border-stone-200 bg-white p-4">
      <h2 class="text-sm font-bold text-stone-900">固定信源</h2>
      <router-link to="/admin/sources" class="mt-1 inline-block text-xs text-leaf-700 hover:underline">前往信源管理，新增、编辑或删除信源 →</router-link>
      <p class="mt-1 text-xs text-stone-500">已启用 {{ enabledSourceCount }} 个信源。开关自动保存，停用会保留内容与进度；正在读取的页面完成后暂停。</p>
      <p class="mt-1 text-xs text-stone-500">自动采集总开关在<router-link to="/admin/settings" class="text-leaf-700 hover:underline">配置</router-link>中，OpenAlex 文献订阅在<router-link to="/admin/watchlist" class="text-leaf-700 hover:underline">关注面</router-link>中管理。</p>
      <p v-if="sourceError" role="alert" class="mt-2 text-xs text-red-600">{{ sourceError }}</p>
      <p v-if="sourceMessage" role="status" class="mt-2 text-xs text-leaf-700">{{ sourceMessage }}</p>
      <ul class="mt-3 divide-y divide-stone-100">
        <li v-for="s in sources" :key="s.id" class="py-3 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <a :href="s.url" target="_blank" rel="noopener noreferrer" class="text-leaf-700 hover:underline">{{ s.name }}</a>
            <div class="flex items-center gap-3">
              <span :class="s.enabled && s.state.status === 'error' ? 'text-red-600' : 'text-stone-500'">{{ !s.can_toggle ? '尚未接入' : !s.enabled ? '已停用' : sourceStatuses[s.state.status] || '尚未运行' }}</span>
              <button type="button" role="switch" :aria-checked="s.enabled" :aria-label="`${s.name}采集`"
                :disabled="!!sourceBusy[s.id] || !s.can_toggle" :title="s.can_toggle ? '' : '该信源尚未接入采集，暂不能启用'"
                class="rounded-md border px-3 py-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                :class="s.enabled ? 'border-leaf-700 bg-leaf-700 text-white hover:bg-leaf-800' : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
                @click="toggleSource(s)">{{ sourceBusy[s.id] ? '保存中…' : s.enabled ? '已启用' : '已停用' }}</button>
            </div>
          </div>
          <p v-if="s.can_toggle" class="mt-1 text-stone-500">{{ s.kind }} · 每 {{ s.interval_minutes }} 分钟</p>
          <p v-if="s.note" class="mt-1 text-stone-500">{{ s.note }}</p>
          <p v-if="s.state.last_checked_at" class="mt-1 text-stone-500">上次检查 {{ fmtWhen(s.state.last_checked_at) }} · 上次成功 {{ fmtWhen(s.state.last_success_at) }}</p>
          <p v-if="s.state.stats" class="mt-1 text-stone-500">新建 {{ s.state.stats.created }} · 重复 {{ s.state.stats.duplicate }} · 过滤 {{ s.state.stats.screened_out }} · 无效 {{ s.state.stats.rejected }} · 失败 {{ s.state.stats.errors }}</p>
          <p v-if="s.state.totals" class="mt-1 text-stone-500">累计检查 {{ s.state.totals.runs }} 次 · 失败 {{ s.state.totals.failed_runs }} 次 · 新增 {{ s.state.totals.created }} 条</p>
          <p v-if="s.state.stats?.error" class="mt-1 break-words text-red-600">{{ s.state.stats.error }}</p>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

definePageMeta({
  layout: 'admin',
  title: '任务调度',
  middleware: 'admin-auth',
})

const api = useApi()
const jobs = ref([])
const sources = ref([])
const enabledSourceCount = computed(() => sources.value.filter(s => s.enabled).length)
const sourceBusy = ref({})
const sourceError = ref('')
const sourceMessage = ref('')
const sourceStatuses = { ok: '正常', partial: '未采完，下次续跑', paused: '已暂停', error: '失败，保留断点' }
let sourceRevision = 0
const error = ref('')
const busy = ref('')
const dailyDate = ref(fmtDateKey(new Date()))
const editorialPreview = ref(true)
let timer = null

const hints = {
  sources_fetch: '从固定 RSS、部委栏目及 Crossref 核心期刊采集，逐源记录状态',
  literature_fetch: '按关注面从 OpenAlex 增量拉取一轮论文',
  daily_generate: '生成或覆盖指定日期的农业日报',
  rescore_unscored: '只给尚未评分的条目打分（需 DeepSeek）',
  translate_abstracts: '给尚未翻译的外文论文摘要补中文译文（需 DeepSeek）',
  retag: '把历史标签再切成短词并清理空标签',
  taxonomy_backfill: '按主题规则回填历史内容；跳过人工锁定，评分和精选不变',
  fetch_content: '回补无全文的政策/报道/行业；论文不抓。也可从内容页勾选指定条目',
  specials_generate: '发现共同议题、提炼与补充引用，通过检查后自动发布',
  editorial_backfill: '每次补全20篇近30天精选及当前专题文章，断点续跑，不改变评分和精选',
}

const stages = {
  load: '读取资料', discover: '发现选题', candidate: '处理专题', sources: '站内来源',
  eligibility: '材料检查', reselect: '补选材料', research: '外部检索', compose: '撰写专题', repair: '修正文档', verify: '独立审查',
  publish: '发布', skip: '跳过', complete: '完成',
  editorial: '关注点与来源',
}

function fmtLogTime(iso) {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
}

function logMetrics(details) {
  if (!details) return ''
  const parts = []
  if (details.model) parts.push(details.model)
  if (details.completion_tokens != null) parts.push(`输出 ${details.completion_tokens} / ${details.max_tokens} tokens`)
  if (details.prompt_tokens != null) parts.push(`输入 ${details.prompt_tokens} tokens`)
  if (details.elapsed_seconds != null) parts.push(`耗时 ${details.elapsed_seconds} 秒`)
  if (details.finish_reason) parts.push(`结束原因 ${details.finish_reason}`)
  return parts.join(' · ')
}

function hint(name) {
  return hints[name] || ''
}

function fmtWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatStats(j) {
  const s = j.stats || {}
  if (j.name === 'literature_fetch' || j.name === 'sources_fetch') {
    return `新建 ${s.created ?? 0} · 重复 ${s.duplicate ?? 0} · 筛掉 ${s.screened_out ?? 0} · 失败 ${s.errors ?? 0}${s.truncated ? ' · 未采完，下次续跑' : ''}`
  }
  if (j.name === 'daily_generate') {
    if (s.skipped) return s.reason || '当日无资讯，已跳过'
    return `${s.title || ''} · ${s.item_count ?? 0} 条`
  }
  if (j.name === 'rescore_unscored') return `评分 ${s.scored ?? 0} / ${s.total ?? 0}，失败 ${s.failed ?? 0}`
  if (j.name === 'translate_abstracts') {
    return `译成 ${s.translated ?? 0} / ${s.total ?? 0}，跳过 ${s.skipped ?? 0}，失败 ${s.failed ?? 0}`
  }
  if (j.name === 'retag') return `条目 ${s.items ?? 0}，改动 ${s.changed ?? 0}`
  if (j.name === 'taxonomy_backfill') return `已处理 ${s.processed ?? 0} · 更新 ${s.changed ?? 0} · 锁定跳过 ${s.locked ?? 0} · 待复核 ${s.needs_review ?? 0}`
  if (j.name === 'fetch_content') return `抓取 ${s.fetched ?? 0} · 跳过 ${s.skipped ?? 0} · 失败 ${s.failed ?? 0}`
  if (j.name === 'specials_generate') return `新建 ${s.created ?? 0} · 更新 ${s.updated ?? 0} · 跳过 ${s.skipped ?? 0} · 失败 ${s.failed ?? 0}${s.reason ? ` · ${s.reason}` : ''}`
  if (j.name === 'editorial_backfill') return s.dry_run ? `预览 ${s.total ?? 0} 篇，未写入数据` : `生成 ${s.generated ?? 0} · 跳过 ${s.skipped ?? 0} · 失败 ${s.failed ?? 0}`
  return JSON.stringify(s)
}

async function load() {
  try {
    jobs.value = (await api.adminJobs()).jobs
    const revision = sourceRevision
    const nextSources = (await api.adminSources()).sources
    if (revision === sourceRevision) sources.value = nextSources
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

async function toggleSource(source) {
  if (!source.can_toggle || sourceBusy.value[source.id]) return
  sourceBusy.value[source.id] = true
  sourceError.value = ''
  sourceMessage.value = ''
  sourceRevision++
  try {
    const result = await api.adminPatchSource(source.id, !source.enabled)
    const current = sources.value.find(s => s.id === source.id)
    if (current) current.enabled = result.enabled
    sourceMessage.value = `${source.name}已${result.enabled ? '启用' : '停用'}`
  } catch (e) {
    sourceError.value = e.message
  } finally {
    sourceRevision++
    delete sourceBusy.value[source.id]
  }
}

async function run(j) {
  busy.value = j.name
  try {
    const body = j.name === 'daily_generate' && dailyDate.value ? { date: dailyDate.value } : j.name === 'editorial_backfill' ? { dry_run: editorialPreview.value } : {}
    await api.adminRunJob(j.name, body)
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

onMounted(async () => {
  await load()
  timer = setInterval(async () => {
    if (jobs.value.some((j) => ['running', 'queued'].includes(j.status))) await load()
  }, 2000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
