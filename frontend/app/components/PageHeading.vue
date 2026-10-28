<template>
  <header class="page-heading">
    <div class="page-heading-copy">
      <p v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="description" class="page-description">{{ description }}</p>
      <slot name="description" />
    </div>
    <div v-if="$slots.default" class="page-heading-actions"><slot /></div>
  </header>
</template>

<script setup>
defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
})
</script>
