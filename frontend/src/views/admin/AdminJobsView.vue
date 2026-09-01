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
        </div>
        <div class="mt-auto flex items-center gap-2">
          <input v-if="j.name === 'daily_generate'" v-model="dailyDate" type="date"
            class="px-2 py-1 text-xs rounded border border-stone-200" />
          <router-link v-if="j.name === 'fetch_content'" to="/admin/items?has_content=false"
            class="ml-auto px-3 py-1.5 text-xs rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50">
            去内容页勾选
          </router-link>
          <button v-else :disabled="j.status === 'running' || busy === j.name"
            @click="run(j)"
            class="ml-auto px-3 py-1.5 text-xs rounded-md bg-leaf-700 text-white hover:bg-leaf-800 disabled:opacity-40">
            {{ j.status === 'running' ? '运行中…' : '立即执行' }}
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api, fmtDateKey } from '../../api'
import JobBadge from '../../components/admin/JobBadge.vue'

const jobs = ref([])
const error = ref('')
const busy = ref('')
const dailyDate = ref(fmtDateKey(new Date()))
let timer = null

const hints = {
  literature_fetch: '按关注面从 OpenAlex 增量拉取一轮论文',
  daily_generate: '生成或覆盖指定日期的农业日报',
  rescore_unscored: '只给尚未评分的条目打分（需 DeepSeek）',
  retag: '把历史标签再切成短词并清理空标签',
  fetch_content: '从内容页批量勾选后触发；此处仅查看状态',
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
  if (j.name === 'literature_fetch') {
    return `新建 ${s.created ?? 0} · 重复 ${s.duplicate ?? 0} · 筛掉 ${s.screened_out ?? 0}`
  }
  if (j.name === 'daily_generate') {
    if (s.skipped) return s.reason || '当日无资讯，已跳过'
    return `${s.title || ''} · ${s.item_count ?? 0} 条`
  }
  if (j.name === 'rescore_unscored') return `评分 ${s.scored ?? 0} / ${s.total ?? 0}，失败 ${s.failed ?? 0}`
  if (j.name === 'retag') return `条目 ${s.items ?? 0}，改动 ${s.changed ?? 0}`
  if (j.name === 'fetch_content') return `抓取 ${s.fetched ?? 0} · 跳过 ${s.skipped ?? 0} · 失败 ${s.failed ?? 0}`
  return JSON.stringify(s)
}

async function load() {
  try {
    jobs.value = (await api.adminJobs()).jobs
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

async function run(j) {
  busy.value = j.name
  try {
    const body = j.name === 'daily_generate' && dailyDate.value ? { date: dailyDate.value } : {}
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
    if (jobs.value.some((j) => j.status === 'running')) await load()
  }, 2000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
