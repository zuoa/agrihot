<template>
  <section class="rounded-xl border border-leaf-100 bg-white p-4" aria-label="AI 评分">
    <div class="flex items-baseline justify-between gap-3">
      <span class="text-xs font-bold text-stone-500">AI 评分</span>
      <span class="text-xs font-bold" :class="textColor">{{ verdict }}</span>
    </div>
    <div class="mt-1 text-[28px] font-extrabold tabular-nums leading-none" :class="textColor">{{ score }}</div>
    <div class="mt-3 space-y-2">
      <div v-for="dim in dims" :key="dim.key">
        <div class="flex items-baseline justify-between text-[11px] text-stone-500">
          <span>{{ dim.label }}</span>
          <span class="tabular-nums text-stone-400">{{ dim.value }}/{{ dim.max }}</span>
        </div>
        <div class="mt-1 h-1.5 rounded-full bg-leaf-100 overflow-hidden">
          <div class="h-full rounded-full motion-safe:transition-[width] motion-safe:duration-500"
            :class="barColor(dim.value, dim.max)" :style="{ width: `${(dim.value / dim.max) * 100}%` }"></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
const LABELS = { impact: '影响力', substance: '信息增量', depth: '专业深度', authority: '信源权威', freshness: '时效性' }
const MAX = { impact: 30, substance: 25, depth: 20, authority: 15, freshness: 10 }

const props = defineProps({
  score: { type: Number, required: true },
  detail: { type: Object, default: null },
})

const level = computed(() => {
  const score = props.score ?? 0
  return score >= 85 ? 3 : score >= 75 ? 2 : score >= 60 ? 1 : 0
})
const textColor = computed(() => ['text-stone-400', 'text-amber-600', 'text-lime-700', 'text-green-700'][level.value])
const verdict = computed(() => ['未达精选线', '接近精选线', '精选', '重点推荐'][level.value])
const dims = computed(() => Object.entries(MAX).map(([key, max]) => ({
  key, max, label: LABELS[key], value: props.detail?.[key] ?? 0,
})))

function barColor(value, max) {
  const ratio = value / max
  return ratio >= 0.75 ? 'bg-leaf-500' : ratio >= 0.5 ? 'bg-lime-500' : ratio >= 0.3 ? 'bg-amber-400' : 'bg-stone-300'
}
</script>
