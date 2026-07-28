<template>
  <section class="rounded-2xl border border-leaf-200 bg-gradient-to-br from-leaf-50/60 to-white p-5 sm:p-6">
    <div class="flex items-center gap-5">
      <!-- 环形总分 -->
      <div class="relative shrink-0 w-24 h-24">
        <svg viewBox="0 0 96 96" class="w-24 h-24 -rotate-90">
          <circle cx="48" cy="48" r="40" fill="none" stroke="#e7f2e7" stroke-width="9" />
          <circle cx="48" cy="48" r="40" fill="none" :stroke="ringColor" stroke-width="9"
            stroke-linecap="round" :stroke-dasharray="`${dash} ${CIRC}`" class="transition-all duration-700" />
        </svg>
        <div class="absolute inset-0 grid place-items-center text-center">
          <div>
            <div class="text-2xl font-extrabold leading-none" :class="textColor">{{ score }}</div>
            <div class="text-[10px] text-stone-400 mt-1">AI 评分</div>
          </div>
        </div>
      </div>

      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-2 py-0.5 rounded-full text-xs font-bold" :class="badgeClass">{{ verdict }}</span>
          <span class="text-xs text-stone-400">精选阈值 {{ threshold }} 分</span>
        </div>
        <p v-if="detail?.comment" class="mt-2 text-sm text-stone-600 leading-6 italic">
          “{{ detail.comment }}”
        </p>
      </div>
    </div>

    <!-- 维度条形图 -->
    <div class="mt-5 space-y-2.5">
      <div v-for="d in dims" :key="d.key" class="flex items-center gap-3">
        <span class="w-16 shrink-0 text-xs text-stone-500">{{ d.label }}</span>
        <div class="flex-1 h-2 rounded-full bg-leaf-100/70 overflow-hidden">
          <div class="h-full rounded-full transition-all duration-700"
            :class="barColor(d.value, d.max)" :style="{ width: `${(d.value / d.max) * 100}%` }"></div>
        </div>
        <span class="w-12 shrink-0 text-right text-xs tabular-nums text-stone-500">{{ d.value }}/{{ d.max }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: Number, required: true },
  detail: { type: Object, default: null },
  threshold: { type: Number, default: 75 },
})

const CIRC = 2 * Math.PI * 40
const dash = computed(() => (props.score / 100) * CIRC)

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

const level = computed(() => (props.score >= 85 ? 3 : props.score >= props.threshold ? 2 : props.score >= 60 ? 1 : 0))

const ringColor = computed(() => ['#a8a29e', '#d97706', '#65a30d', '#15803d'][level.value])
const textColor = computed(() => ['text-stone-400', 'text-amber-600', 'text-lime-600', 'text-green-700'][level.value])
const badgeClass = computed(() => [
  'bg-stone-100 text-stone-500',
  'bg-amber-100 text-amber-700',
  'bg-lime-100 text-lime-700',
  'bg-green-100 text-green-800',
][level.value])
const verdict = computed(() => ['未达精选线', '接近精选线', '精选', '重点推荐'][level.value])

function barColor(value, max) {
  const r = value / max
  return r >= 0.75 ? 'bg-leaf-500' : r >= 0.5 ? 'bg-lime-500' : r >= 0.3 ? 'bg-amber-400' : 'bg-stone-300'
}
</script>
