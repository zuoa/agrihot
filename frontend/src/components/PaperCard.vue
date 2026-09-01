<template>
  <section class="rounded-xl border border-leaf-100 bg-leaf-50/60 overflow-hidden">
    <div class="px-4 pt-4 pb-2 flex items-center gap-2 flex-wrap">
      <span class="text-xs font-bold text-leaf-800">论文卡片</span>
      <span v-if="card.direction"
        class="px-2 py-0.5 rounded-full bg-white text-leaf-700 border border-leaf-100 text-[11px]">
        {{ card.direction }}
      </span>
    </div>
    <dl class="divide-y divide-leaf-100/80">
      <div v-for="row in rows" :key="row.key" class="px-4 py-3 grid grid-cols-[4.5rem_1fr] gap-3">
        <dt class="text-xs font-bold text-leaf-700 pt-0.5">{{ row.label }}</dt>
        <dd class="text-sm text-stone-700 leading-6">{{ row.value }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
})

const rows = computed(() => [
  { key: 'tldr', label: '速览', value: props.card.tldr },
  { key: 'method', label: '方法', value: props.card.method },
  { key: 'finding', label: '发现', value: props.card.finding },
  { key: 'opportunity', label: '机会点', value: props.card.opportunity },
].filter((r) => r.value))
</script>
