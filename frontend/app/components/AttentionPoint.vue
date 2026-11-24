<template>
  <div v-if="text" class="attention-point" :class="{ 'attention-point-compact': compact }">
    <span class="attention-label">关注点</span><p>{{ text }}</p>
  </div>
</template>
<script setup>
defineProps({ text: { type: String, default: '' }, compact: Boolean })
</script>
<style scoped>
.attention-point {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 11px;
  margin-top: 18px;
  padding: 13px 16px;
  border-left: 3px solid #5d9855;
  background: linear-gradient(90deg, #f1f7ee 0%, #f7fbf5 100%);
  border-radius: 0 10px 10px 0;
}
.attention-label {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  margin-top: 2px;
  border-radius: 5px;
  background: #e3f0de;
  font-size: 10.5px;
  color: var(--site-green, #234e22);
  font-weight: 600;
  line-height: 1.7;
  white-space: nowrap;
}
.attention-point p { font-size: 13px; color: #3a4a3f; line-height: 1.85; overflow-wrap: anywhere; }
.attention-point-compact {
  padding: 9px 12px;
  gap: 9px;
  margin-top: 12px;
  border-left: 2px solid #8eb586;
  border-radius: 0 8px 8px 0;
  background: #f5f9f3;
}
.attention-point-compact p { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 12px; line-height: 1.75; }
</style>
