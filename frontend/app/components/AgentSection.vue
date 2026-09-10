<template>
  <section :id="id" class="bg-white rounded-2xl border border-leaf-100 p-5 sm:p-6">
    <h2 class="text-lg font-bold text-leaf-800 mb-4">{{ title }}</h2>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  id: { type: String, default: '' },
})
</script>
