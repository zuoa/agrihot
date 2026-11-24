<template>
  <span v-if="provenance?.status === 'primary'" class="source-provenance" :title="`${provenance.label}：${provenance.explanation}`" :aria-label="`一手来源，${provenance.label}`">
    <span aria-hidden="true">✓</span>一手来源<span v-if="detail"> · {{ provenance.label }}</span>
  </span>
</template>
<script setup>
defineProps({ provenance: { type: Object, default: null }, detail: Boolean })
</script>
<style scoped>
.source-provenance {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #edf6ea;
  border: 1px solid #d3e6ce;
  color: var(--site-green, #234e22);
  font-size: 10.5px;
  font-weight: 500;
  line-height: 1.6;
  white-space: nowrap;
}
</style>
