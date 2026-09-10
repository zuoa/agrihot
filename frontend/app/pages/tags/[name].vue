<template>
  <div>
    <div class="flex items-center gap-3 mb-5">
      <NuxtLink to="/tags" class="text-sm text-stone-400 hover:text-leaf-600">← 主题</NuxtLink>
      <h1 class="text-xl font-bold text-leaf-800">#{{ name }}</h1>
    </div>
    <div v-if="pending" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else-if="!items.length" class="text-center text-stone-400 py-16">该主题下暂无内容</div>
    <div v-else class="space-y-3">
      <ItemCard v-for="it in items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" />
    </div>
  </div>
</template>

<script setup>
const route = useRoute()
const api = useApi()
const name = computed(() => decodeURIComponent(String(route.params.name || '')))

const { data, pending, refresh } = await useAsyncData(
  () => `tag-${name.value}`,
  () => api.items({ tag: name.value, page_size: 100 }),
  { watch: [name] },
)

const items = computed(() => data.value?.items || [])

if (!pending.value && !items.value.length) {
  throw createError({ statusCode: 404, statusMessage: '主题不存在', fatal: true })
}

usePageSeo(() => ({
  title: `#${name.value} · AgriHot`,
  description: `农业信息化主题「${name.value}」相关资讯与论文，共 ${items.value.length} 条。`,
  path: `/tags/${encodeURIComponent(name.value)}`,
  noindex: items.value.length === 0,
  keywords: uniqueKeywords([name.value, '农业信息化', '主题']),
}))
</script>
