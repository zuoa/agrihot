<template>
  <div class="relative mt-3">
    <span class="absolute top-2 right-3 text-[10px] text-stone-400 font-mono">{{ lang }}</span>
    <pre class="rounded-xl bg-stone-900 text-leaf-100 text-xs leading-5 p-4 overflow-x-auto font-mono whitespace-pre">{{ code }}</pre>
  </div>
</template>

<script setup>
defineProps({
  lang: { type: String, default: '' },
  code: { type: String, default: '' },
})
</script>
