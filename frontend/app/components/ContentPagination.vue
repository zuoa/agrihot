<template>
  <nav v-if="totalPages > 1" aria-label="分页" class="flex justify-center gap-3 mt-6">
    <NuxtLink v-if="page > 1" :to="pageLink(page - 1)"
      class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white hover:border-leaf-400">上一页</NuxtLink>
    <span v-else class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white opacity-40">上一页</span>
    <span class="text-sm text-stone-500 self-center">{{ page }} / {{ totalPages }}</span>
    <NuxtLink v-if="page < totalPages" :to="pageLink(page + 1)"
      class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white hover:border-leaf-400">下一页</NuxtLink>
    <span v-else class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white opacity-40">下一页</span>
  </nav>
</template>

<script setup>
const props = defineProps({
  page: { type: Number, required: true },
  total: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
})
const route = useRoute()
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

function pageLink(page) {
  const query = { ...route.query }
  if (page <= 1) delete query.page
  else query.page = String(page)
  return { path: route.path, query }
}
</script>
