<template>
  <span v-if="provenance?.status === 'primary'" class="source-provenance" :title="`${provenance.label}：${provenance.explanation}`" :aria-label="`一手来源，${provenance.label}`">
    <span aria-hidden="true">✓</span>一手来源<span v-if="detail"> · {{ provenance.label }}</span>
  </span>
</template>
<script setup>
defineProps({ provenance: { type: Object, default: null }, detail: Boolean })
</script>
<style scoped>
.source-provenance { display: inline-flex; align-items: center; gap: 4px; color: var(--site-green, #234e22); font-size: 11px; font-weight: 500; line-height: 1.7; white-space: nowrap; }
</style>
