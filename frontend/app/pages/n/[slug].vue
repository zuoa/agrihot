<script setup>
const route = useRoute()
const slug = String(route.params.slug || '')
const id = slug.split('-').pop()
if (!/^\d+$/.test(id)) {
  throw createError({ statusCode: 404, statusMessage: '条目不存在', fatal: true })
}
await navigateTo(`/items/${id}`, { redirectCode: 301, replace: true })
</script>

<template>
  <div class="text-center text-stone-400 py-16">跳转中…</div>
</template>
