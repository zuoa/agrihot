<template>
  <section class="score-panel" aria-label="AI 评分">
    <div class="score-heading"><h2>情报价值评估</h2><span>AI 评分</span></div>
    <div class="score-overview">
      <div class="score-number" :class="textColor">{{ score }}<span>/ 100</span></div>
      <span class="score-verdict" :class="textColor">{{ verdict }}</span>
    </div>
    <details v-if="hasDimensions" class="score-breakdown">
      <summary><span class="score-expand">查看评分明细</span><span class="score-collapse">收起评分明细</span><ArticleIcon name="chevron" /></summary>
      <div class="score-dimensions">
        <div v-for="dim in dims" :key="dim.key" class="score-dimension">
          <div class="dimension-label"><span>{{ dim.label }}</span><span>{{ dim.value }}<span class="dimension-max"> / {{ dim.max }}</span></span></div>
          <div class="dimension-track"><div :class="barColor(dim.value, dim.max)" :style="{ width: `${Math.max(0, Math.min(100, (dim.value / dim.max) * 100))}%` }"></div></div>
        </div>
      </div>
    </details>
    <p v-else class="score-unavailable">暂无分项评分</p>
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
const textColor = computed(() => ['text-stone-500', 'text-amber-700', 'text-leaf-700', 'text-leaf-800'][level.value])
const verdict = computed(() => ['未达精选线', '接近精选线', '精选', '重点推荐'][level.value])
const hasDimensions = computed(() => Object.keys(MAX).some(key => props.detail?.[key] != null))
const dims = computed(() => Object.entries(MAX).map(([key, max]) => ({
  key, max, label: LABELS[key], value: props.detail?.[key] ?? 0,
})))

function barColor(value, max) {
  const ratio = value / max
  return ratio >= 0.75 ? 'bg-leaf-600' : ratio >= 0.5 ? 'bg-leaf-400' : ratio >= 0.3 ? 'bg-amber-400' : 'bg-stone-300'
}
</script>

<style scoped>
.score-panel { padding: 22px; border: 1px solid #e1e8e0; border-radius: 14px; background: #fff; }
.score-heading { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.score-heading h2 { font-size: 13px; font-weight: 600; color: #20332a; }
.score-heading > span { font-size: 10px; color: #637168; }
.score-overview { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; margin-top: 17px; padding-bottom: 19px; border-bottom: 1px solid #e1e8e0; }
.score-number { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace; font-size: 42px; font-weight: 500; line-height: 1; letter-spacing: -.08em; }
.score-number > span { margin-left: 8px; color: #637168; font-size: 11px; font-weight: 400; letter-spacing: 0; }
.score-verdict { font-size: 11px; font-weight: 500; }
.score-breakdown summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 44px; color: #234e22; font-size: 11px; list-style: none; cursor: pointer; scroll-margin-top: 100px; }
.score-breakdown summary::-webkit-details-marker { display: none; }
.score-breakdown summary:hover { text-decoration: underline; text-underline-offset: 4px; }
.score-breakdown summary:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; border-radius: 3px; }
.score-breakdown summary svg { width: 14px; height: 14px; transform: rotate(90deg); }
.score-breakdown[open] summary svg { transform: rotate(-90deg); }
.score-collapse, .score-breakdown[open] .score-expand { display: none; }
.score-breakdown[open] .score-collapse { display: inline; }
.score-dimensions { display: grid; gap: 14px; padding-top: 6px; }
.dimension-label { display: flex; justify-content: space-between; font-size: 11px; color: #637168; }
.dimension-label > span:last-child { font-family: 'SFMono-Regular', Consolas, monospace; color: #20332a; }
.dimension-max { color: #637168; }
.dimension-track { height: 4px; margin-top: 7px; border-radius: 2px; background: #edf2eb; overflow: hidden; }
.dimension-track > div { height: 100%; border-radius: 2px; }
.score-unavailable { margin-top: 16px; font-size: 11px; color: #637168; }
@media (min-width: 768px) and (max-width: 1023px) { .score-panel { padding: 18px; } }
@media (max-width: 767px) { .score-breakdown summary { scroll-margin-top: 148px; } }
</style>
