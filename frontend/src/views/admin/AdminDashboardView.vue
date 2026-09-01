<template>
  <div v-if="loading" class="text-sm text-stone-400 py-16 text-center">加载中…</div>
  <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>
  <div v-else-if="data" class="space-y-6">
    <section class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <div v-for="s in stats" :key="s.label" class="bg-white border border-stone-200 rounded-lg p-3">
        <div class="text-[11px] text-stone-400">{{ s.label }}</div>
        <div class="mt-1 text-xl font-semibold tabular-nums text-stone-900">{{ s.value }}</div>
      </div>
    </section>

    <section class="grid sm:grid-cols-2 gap-3">
      <router-link to="/admin/items?has_content=false"
        class="bg-white border border-stone-200 rounded-lg p-4 hover:border-leaf-400 transition-colors">
        <div class="text-[11px] text-stone-400">待处理积压</div>
        <div class="mt-1 text-lg font-semibold tabular-nums">{{ data.missing_content }} <span class="text-sm font-normal text-stone-500">条无全文</span></div>
        <div class="text-xs text-leaf-700 mt-2">去筛选并重抓 →</div>
      </router-link>
      <router-link to="/admin/items?scored=false"
        class="bg-white border border-stone-200 rounded-lg p-4 hover:border-leaf-400 transition-colors">
        <div class="text-[11px] text-stone-400">待处理积压</div>
        <div class="mt-1 text-lg font-semibold tabular-nums">{{ data.unscored }} <span class="text-sm font-normal text-stone-500">条未评分</span></div>
        <div class="text-xs text-leaf-700 mt-2">去筛选或补评 →</div>
      </router-link>
    </section>

    <section>
      <h2 class="text-xs font-bold text-stone-500 mb-2">调度</h2>
      <div class="grid sm:grid-cols-2 gap-3">
        <div v-for="(sch, key) in data.schedulers" :key="key"
          class="bg-white border border-stone-200 rounded-lg p-4 flex items-start justify-between gap-3">
          <div>
            <div class="text-sm font-medium">{{ key === 'daily_generate' ? '日报生成' : '文献拉取' }}</div>
            <div class="text-xs text-stone-400 mt-1">每天 {{ sch.time }} · {{ sch.timezone }}</div>
            <div class="text-xs text-stone-500 mt-1">下次 {{ fmtNext(sch.next_run_at) }}</div>
          </div>
          <span class="text-[11px] px-2 py-0.5 rounded-full"
            :class="sch.enabled ? 'bg-leaf-100 text-leaf-800' : 'bg-stone-100 text-stone-500'">
            {{ sch.enabled ? '开启' : '关闭' }}
          </span>
        </div>
      </div>
    </section>

    <section>
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-xs font-bold text-stone-500">最近任务</h2>
        <router-link to="/admin/jobs" class="text-xs text-leaf-700 hover:underline">全部任务</router-link>
      </div>
      <div class="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-xs text-stone-500">
            <tr>
              <th class="text-left font-medium px-3 py-2">任务</th>
              <th class="text-left font-medium px-3 py-2">状态</th>
              <th class="text-left font-medium px-3 py-2 hidden sm:table-cell">完成时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="j in data.jobs" :key="j.name" class="border-t border-stone-100">
              <td class="px-3 py-2">{{ j.label }}</td>
              <td class="px-3 py-2"><JobBadge :status="j.status" /></td>
              <td class="px-3 py-2 text-xs text-stone-400 hidden sm:table-cell">{{ fmtWhen(j.finished_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import JobBadge from '../../components/admin/JobBadge.vue'

const data = ref(null)
const loading = ref(true)
const error = ref('')

const stats = computed(() => data.value ? [
  { label: '条目', value: data.value.items },
  { label: '精选', value: data.value.selected },
  { label: '日报', value: data.value.dailies },
  { label: '标签', value: data.value.tags },
  { label: '无全文', value: data.value.missing_content },
  { label: '未评分', value: data.value.unscored },
] : [])

onMounted(async () => {
  try {
    data.value = await api.adminOverview()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function fmtNext(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>
