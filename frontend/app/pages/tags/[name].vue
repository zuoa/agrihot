<template>
  <div>
    <nav class="site-breadcrumb" aria-label="面包屑"><NuxtLink to="/tags"><ArticleIcon name="back" />全部标签</NuxtLink><ArticleIcon name="chevron" /><span aria-current="page">{{ name }}</span></nav>
    <PageHeading :eyebrow="isPhrase ? '组合检索 · 相关资讯' : '关键词 · 相关资讯与研究'" :title="heading" :description="isPhrase ? '' : `沿着“${name}”继续探索，共 ${total.toLocaleString('zh-CN')} 条内容。`">
      <template v-if="isPhrase && tokens.length" #description><p class="page-description">同时包含<template v-for="(token, index) in tokens" :key="token"><NuxtLink :to="tagPath(token)" class="text-leaf-700 hover:underline">{{ token }}</NuxtLink><span v-if="index < tokens.length - 1">、</span></template>的农业资讯，共 {{ total }} 条。</p></template>
    </PageHeading>
    <div class="site-columns"><div class="site-column-main">
      <PageSkeleton v-if="pending" />
      <div v-else-if="error" class="site-empty" role="alert"><h2>内容暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
      <div v-else-if="!items.length" class="site-empty"><h2>暂未找到相关内容</h2><p>可以换一个关键词，或按农业领域继续浏览。</p><NuxtLink to="/topic" class="site-button site-button-secondary">浏览农业主题</NuxtLink></div>
      <div v-else class="site-card-list"><ItemCard v-for="it in items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
      <ContentPagination v-if="!pending && !error" :page="page" :total="total" :page-size="pageSize" />
    </div><BrowseSidebar /></div>
  </div>
</template>

<script setup>
const route = useRoute()
const api = useApi()
const name = computed(() => decodeTagName(route.params.name))
const pageSize = 20
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))

if (import.meta.server && name.value) {
  const reqUrl = useRequestURL()
  if (/%25[0-9A-Fa-f]{2}/.test(reqUrl.pathname)) {
    await navigateTo({ path: tagPath(name.value), query: route.query }, { redirectCode: 301, replace: true })
  }
}

const { data, pending, error, refresh } = await useAsyncData(
  () => `topic-${name.value}-${page.value}`,
  () => api.topic(name.value, { page: page.value, page_size: pageSize }),
  { watch: [name, page] },
)

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total ?? items.value.length)
const tokens = computed(() => data.value?.tokens || [])
const isPhrase = computed(() => data.value?.kind === 'phrase')
const heading = computed(() => (isPhrase.value ? name.value : `#${name.value}`))

usePageSeo(() => ({
  title: isPhrase.value
    ? `${name.value} · AgriHot`
    : `#${name.value} · AgriHot`,
  description: isPhrase.value
    ? `与「${tokens.value.join('、')}」同时相关的农业资讯，共 ${total.value} 条。`
    : `农业信息化主题「${name.value}」相关资讯与论文，共 ${total.value} 条。`,
  path: `${tagPath(name.value)}${page.value > 1 ? `?page=${page.value}` : ''}`,
  noindex: items.value.length === 0,
  keywords: uniqueKeywords([name.value, tokens.value, '农业信息化', '主题']),
  jsonLd: (origin) => (data.value ? topicJsonLd(data.value, origin) : null),
}))
</script>
