<template>
  <span class="inline-flex shrink-0 items-center justify-center align-middle"
    :class="inverse ? 'text-leaf-100' : 'text-leaf-600'"
    role="img" aria-label="已向量化" title="已向量化，可用于语义检索">
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="m3 6 7-3.5L17 6l-7 3.5L3 6Zm0 4 7 3.5 3-1.5M3 14l7 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      <path d="m13 15.5 1.5 1.5L18 13.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </span>
</template>

<script setup>
defineProps({ inverse: { type: Boolean, default: false } })
</script>
