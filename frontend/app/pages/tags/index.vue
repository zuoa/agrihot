<template>
  <div>
    <h1 class="text-xl font-bold text-leaf-800 mb-5">主题</h1>
    <div v-if="pending" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else class="flex flex-wrap gap-2.5">
      <NuxtLink v-for="t in tags" :key="t.name" :to="`/tags/${encodeURIComponent(t.name)}`"
        class="px-4 py-2 rounded-full bg-white border border-leaf-200 text-sm text-stone-700 hover:border-leaf-500 hover:text-leaf-700 transition-colors">
        #{{ t.name }}
        <span class="ml-1 text-xs text-stone-400">{{ t.count }}</span>
      </NuxtLink>
    </div>
  </div>
</template>

<script setup>
const api = useApi()
const { data, pending } = await useAsyncData('tags', () => api.tags())
const tags = computed(() => data.value || [])

usePageSeo({
  title: '主题 · AgriHot',
  description: '按主题浏览农业信息化资讯：智慧农业、数字乡村、遥感、政策等。',
  path: '/tags',
  keywords: uniqueKeywords(['主题', DEFAULT_KEYWORDS]),
})
</script>
