<template>
  <section class="rounded-2xl border border-leaf-200 bg-white overflow-hidden" :aria-label="heading">
    <header class="px-4 sm:px-5 py-3 flex items-center justify-between gap-4 border-b border-leaf-100 bg-leaf-50/70">
      <div class="text-xs font-bold text-leaf-800">{{ heading }}</div>
      <div v-if="hasScore" class="shrink-0 flex items-baseline gap-2">
        <span class="text-[26px] font-extrabold tabular-nums leading-none" :class="textColor">{{ score }}</span>
        <span class="text-[11px] font-bold" :class="textColor">{{ verdict }}</span>
      </div>
    </header>

    <div v-if="rows.length" class="px-4 sm:px-5 py-4 grid sm:grid-cols-2 gap-x-8 gap-y-4">
      <div v-for="row in rows" :key="row.key" :class="row.wide ? 'sm:col-span-2' : ''">
        <div class="text-[11px] font-bold tracking-wide text-leaf-700 mb-1">{{ row.label }}</div>
        <p class="text-sm text-stone-800 leading-6">{{ row.value }}</p>
      </div>
    </div>

    <div v-if="hasScore" :class="rows.length ? 'border-t border-leaf-100' : ''">
      <div class="px-4 sm:px-5 py-3.5 grid grid-cols-2 sm:grid-cols-5 gap-x-4 gap-y-3">
        <div v-for="d in dims" :key="d.key" class="min-w-0">
          <div class="flex items-baseline gap-1 mb-1">
            <span class="text-[11px] text-stone-500 truncate">{{ d.label }}</span>
            <span class="text-[11px] tabular-nums text-stone-400">{{ d.value }}</span>
          </div>
          <div class="h-1.5 rounded-full bg-leaf-100 overflow-hidden">
            <div class="h-full rounded-full motion-safe:transition-[width] motion-safe:duration-500"
              :class="barColor(d.value, d.max)" :style="{ width: `${(d.value / d.max) * 100}%` }"></div>
          </div>
        </div>
      </div>
      <p v-if="detail?.comment" class="px-4 sm:px-5 pb-4 text-sm text-stone-500 leading-6">
        {{ detail.comment }}
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  card: { type: Object, default: null },
  score: { type: Number, default: null },
  detail: { type: Object, default: null },
  threshold: { type: Number, default: 75 },
})

const hasScore = computed(() => props.score != null)
const heading = computed(() => (props.card ? '论文解读' : 'AI 评分'))

const rows = computed(() => {
  const c = props.card
  if (!c) return []
  return [
    { key: 'tldr', label: '速览', value: c.tldr, wide: true },
    { key: 'method', label: '方法', value: c.method, wide: false },
    { key: 'finding', label: '发现', value: c.finding, wide: false },
    { key: 'opportunity', label: '机会点', value: c.opportunity, wide: true },
  ].filter((r) => r.value)
})

const LABELS = {
  impact: '影响力',
  substance: '信息增量',
  depth: '专业深度',
  authority: '信源权威',
  freshness: '时效性',
}
const MAX = { impact: 30, substance: 25, depth: 20, authority: 15, freshness: 10 }

const dims = computed(() =>
  Object.entries(MAX).map(([key, max]) => ({
    key, max, label: LABELS[key], value: props.detail?.[key] ?? 0,
  }))
)

const level = computed(() => {
  const s = props.score ?? 0
  return s >= 85 ? 3 : s >= props.threshold ? 2 : s >= 60 ? 1 : 0
})
const textColor = computed(() => ['text-stone-400', 'text-amber-600', 'text-lime-700', 'text-green-700'][level.value])
const verdict = computed(() => ['未达精选线', '接近精选线', '精选', '重点推荐'][level.value])

function barColor(value, max) {
  const r = value / max
  return r >= 0.75 ? 'bg-leaf-500' : r >= 0.5 ? 'bg-lime-500' : r >= 0.3 ? 'bg-amber-400' : 'bg-stone-300'
}
</script>
