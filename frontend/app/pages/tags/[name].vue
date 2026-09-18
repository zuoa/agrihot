<template>
  <div>
    <div class="flex items-center gap-3 mb-3">
      <NuxtLink to="/tags" class="text-sm text-stone-400 hover:text-leaf-600">← 主题</NuxtLink>
      <h1 class="text-xl font-bold text-leaf-800">{{ heading }}</h1>
    </div>
    <p v-if="isPhrase && tokens.length" class="text-sm text-stone-500 mb-4 leading-6">
      同时包含
      <template v-for="(t, i) in tokens" :key="t">
        <NuxtLink :to="tagPath(t)" class="text-leaf-700 hover:underline">{{ t }}</NuxtLink>
        <span v-if="i < tokens.length - 1">、</span>
      </template>
      的农业资讯，共 {{ total }} 条。
    </p>
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
  () => `topic-${name.value}`,
  () => api.topic(name.value, { page_size: 100 }),
  { watch: [name] },
)

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total ?? items.value.length)
const tokens = computed(() => data.value?.tokens || [])
const isPhrase = computed(() => data.value?.kind === 'phrase')
const heading = computed(() => (isPhrase.value ? name.value : `#${name.value}`))

if (!pending.value && !items.value.length) {
  throw createError({ statusCode: 404, statusMessage: '主题不存在', fatal: true })
}

usePageSeo(() => ({
  title: isPhrase.value
    ? `${name.value} · AgriHot`
    : `#${name.value} · AgriHot`,
  description: isPhrase.value
    ? `与「${tokens.value.join('、')}」同时相关的农业资讯，共 ${total.value} 条。`
    : `农业信息化主题「${name.value}」相关资讯与论文，共 ${total.value} 条。`,
  path: tagPath(name.value),
  noindex: items.value.length === 0,
  keywords: uniqueKeywords([name.value, tokens.value, '农业信息化', '主题']),
  jsonLd: (origin) => (data.value ? topicJsonLd(data.value, origin) : null),
}))
</script>
