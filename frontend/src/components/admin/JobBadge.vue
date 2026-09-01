<template>
  <span class="inline-flex items-center gap-1.5 text-xs">
    <span class="w-1.5 h-1.5 rounded-full" :class="dot"></span>
    <span :class="text">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'idle' },
})

const map = {
  idle: { label: '未运行', dot: 'bg-stone-300', text: 'text-stone-500' },
  running: { label: '进行中', dot: 'bg-sky-500 animate-pulse', text: 'text-sky-700' },
  ok: { label: '成功', dot: 'bg-leaf-500', text: 'text-leaf-800' },
  error: { label: '失败', dot: 'bg-red-500', text: 'text-red-700' },
}

const label = computed(() => (map[props.status] || map.idle).label)
const dot = computed(() => (map[props.status] || map.idle).dot)
const text = computed(() => (map[props.status] || map.idle).text)
</script>
