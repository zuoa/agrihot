<template>
  <div v-if="text" class="attention-point" :class="{ 'attention-point-compact': compact }">
    <span class="attention-label">关注点</span><p>{{ text }}</p>
  </div>
</template>
<script setup>
defineProps({ text: { type: String, default: '' }, compact: Boolean })
</script>
<style scoped>
.attention-point { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; margin-top: 18px; padding: 14px 16px; border-left: 2px solid #9bb793; background: var(--site-soft, #f2f6ef); border-radius: 0 6px 6px 0; }
.attention-label { padding-top: 2px; font-size: 11px; color: var(--site-green, #234e22); font-weight: 600; line-height: 1.9; }
.attention-point p { font-size: 13px; color: #435046; line-height: 1.9; overflow-wrap: anywhere; }
.attention-point-compact { padding: 0; gap: 9px; margin-top: 12px; border: 0; border-radius: 0; background: transparent; }
.attention-point-compact p { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12px; }
</style>
