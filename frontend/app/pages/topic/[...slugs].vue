<template>
  <div>
    <PageSkeleton v-if="!node" label="正在加载主题…" />
    <template v-else>
      <nav aria-label="主题路径" class="site-breadcrumb"><NuxtLink to="/topic">主题索引</NuxtLink><template v-if="parent"><ArticleIcon name="chevron" /><NuxtLink :to="parent.path">{{ parent.name }}</NuxtLink></template><ArticleIcon name="chevron" /><span aria-current="page">{{ node.name }}</span></nav>
      <PageHeading :eyebrow="parent ? `${parent.name} · 细分方向` : '农业领域 · 主题专题'" :title="node.name" :description="node.description"><span class="topic-total"><strong>{{ node.count.toLocaleString('zh-CN') }}</strong> 篇内容</span></PageHeading>
      <details v-if="siblings.length" class="topic-mobile-directions site-surface">
        <summary>{{ parent ? '切换同领域方向' : '浏览细分方向' }}</summary>
        <nav class="site-filter-pills" aria-label="切换主题方向">
          <NuxtLink v-if="parent" :to="parent.path">全部</NuxtLink>
          <NuxtLink v-for="child in siblings" :key="child.code" :to="child.path" :aria-current="child.code === node.code ? 'page' : undefined">{{ child.name }}<span class="opacity-60">{{ child.count }}</span></NuxtLink>
        </nav>
      </details>
      <div class="site-columns">
        <div class="site-column-main">
          <div class="topic-filter-panel site-surface">
            <form class="site-search" role="search" @submit.prevent="search"><ArticleIcon name="search" /><label class="sr-only" for="topic-search">在主题内搜索</label><input id="topic-search" v-model="searchInput" type="search" placeholder="在这个主题内搜索…" /><button class="site-button" type="submit">搜索</button></form>
            <nav aria-label="内容类型" class="site-tabs"><NuxtLink v-for="c in ['', '政策', '报道', '论文', '行业']" :key="c" :to="filterLink({ category: c })" :aria-current="category === c ? 'page' : undefined">{{ c || '全部类型' }}</NuxtLink></nav>
            <details v-if="technologies.length || selectedTech.length" class="technology-filter" :open="selectedTech.length > 0"><summary>按技术筛选<span v-if="selectedTech.length"> · 已选 {{ selectedTech.length }} 项</span></summary><div class="site-filter-pills"><NuxtLink v-for="technology in technologies" :key="technology.name" :to="technologyLink(technology.name)" :aria-current="selectedTech.includes(technology.name) ? 'page' : undefined">{{ technology.name }}<span class="opacity-60">{{ technology.count }}</span></NuxtLink><NuxtLink v-if="selectedTech.length" :to="filterLink({ technology: [] })">清除技术筛选</NuxtLink></div></details>
          </div>
          <div class="site-result-meta" aria-live="polite"><span>{{ q ? `“${q}”的搜索结果 · ` : '' }}{{ total.toLocaleString('zh-CN') }} 篇内容</span><NuxtLink v-if="hasFilters" :to="node.path">清除全部筛选</NuxtLink></div>
          <PageSkeleton v-if="pending" />
          <div v-else-if="error" class="site-empty" role="alert"><h2>内容暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
          <div v-else-if="!items.length" class="site-empty"><h2>{{ hasFilters ? '当前筛选下暂无内容' : '这个方向还没有内容' }}</h2><p>{{ hasFilters ? '试试其他关键词或减少筛选条件。' : '先看看同领域的其他方向。' }}</p><NuxtLink :to="hasFilters ? node.path : (parent?.path || '/topic')" class="site-button site-button-secondary">{{ hasFilters ? '清除筛选' : '浏览更多主题' }}</NuxtLink></div>
          <div v-else class="site-card-list"><ItemCard v-for="it in items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
          <ContentPagination v-if="!pending && !error" :page="page" :total="total" :page-size="20" />
        </div>
        <aside class="browse-sidebar" aria-label="主题导航">
          <details v-if="siblings.length" class="topic-siblings site-surface" open><summary>{{ parent ? '同领域方向' : '细分方向' }}</summary><nav><NuxtLink v-if="parent" :to="parent.path"><span>查看全部 {{ parent.name }}</span><ArticleIcon name="external" /></NuxtLink><NuxtLink v-for="child in siblings" :key="child.code" :to="child.path" :aria-current="child.code === node.code ? 'page' : undefined"><span>{{ child.name }}</span><span>{{ child.count }}</span></NuxtLink></nav></details>
          <section v-if="facets?.keywords?.length" class="topic-keywords site-surface"><h2>相关热词</h2><div><NuxtLink v-for="tag in facets.keywords.slice(0, 8)" :key="tag.name" :to="tagPath(tag.name)">#{{ tag.name }}</NuxtLink></div></section>
          <NuxtLink to="/topic" class="site-text-link"><ArticleIcon name="back" />浏览全部领域</NuxtLink>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
const api = useApi()
const route = useRoute()
const router = useRouter()
const { data: directory, error: directoryError } = await useAsyncData('taxonomy', () => api.taxonomy())
const slugs = computed(() => Array.isArray(route.params.slugs) ? route.params.slugs : [route.params.slugs])
const topicSlug = computed(() => slugs.value[slugs.value.length - 1])
const parent = computed(() => slugs.value.length === 2 ? directory.value?.topics.find(t => t.slug === slugs.value[0]) : null)
const node = computed(() => slugs.value.length === 1
  ? directory.value?.topics.find(t => t.slug === slugs.value[0])
  : parent.value?.children.find(t => t.slug === slugs.value[1]))
const nodeError = computed(() => {
  if (directoryError.value) return { statusCode: 503, message: '主题加载失败，请稍后重试' }
  if (directory.value && (!node.value || slugs.value.length > 2)) return { statusCode: 404, message: '主题不存在' }
  return null
})
watch(nodeError, error => { if (error) showError(error) }, { immediate: true })
const siblings = computed(() => parent.value?.children || node.value?.children || [])
const category = computed(() => ['政策', '报道', '论文', '行业'].includes(route.query.category) ? route.query.category : '')
const selectedTech = computed(() => Array.isArray(route.query.technology) ? route.query.technology : (route.query.technology ? [route.query.technology] : []))
const q = computed(() => String(route.query.q || '').trim())
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))
const searchInput = ref(q.value)
watch(q, value => { searchInput.value = value })
const hasFilters = computed(() => Boolean(category.value || selectedTech.value.length || q.value))
const [{ data, pending, error, refresh }, { data: facets }] = await Promise.all([
  useAsyncData(
    () => `taxonomy-items:${route.fullPath}`,
    () => api.items({ topic: topicSlug.value, category: category.value, technologies: selectedTech.value, q: q.value, page: page.value, page_size: 20 }),
  ),
  useAsyncData(
    () => `taxonomy-facets:${topicSlug.value}:${category.value}`,
    () => api.taxonomyFacets({ topic: topicSlug.value, category: category.value }),
  ),
])
const technologies = computed(() => facets.value?.technologies || [])
const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total || 0)
function filterLink(changes, resetPage = true) {
  const query = { ...route.query, ...changes }
  if (resetPage) delete query.page
  for (const key of Object.keys(query)) if (!query[key] || (Array.isArray(query[key]) && !query[key].length) || (key === 'page' && query[key] <= 1)) delete query[key]
  return { path: node.value.path, query }
}
function technologyLink(name) {
  const selected = selectedTech.value.includes(name) ? selectedTech.value.filter(t => t !== name) : [...selectedTech.value, name]
  return filterLink({ technology: selected })
}
function search() { router.push(filterLink({ q: searchInput.value.trim() })) }
usePageSeo(() => ({
  title: `${node.value?.name || '主题'} · AgriHot`, description: node.value?.description,
  path: `${node.value?.path || '/topic'}${page.value > 1 ? `?page=${page.value}` : ''}`, noindex: hasFilters.value,
  keywords: [node.value?.name, parent.value?.name, '农业信息化'].filter(Boolean),
  jsonLd: origin => ({ '@context': 'https://schema.org', '@type': 'CollectionPage', name: node.value?.name,
    url: absUrl(node.value?.path || '/topic', origin), hasPart: items.value.map(it => ({ '@type': 'Article', name: it.title, url: absUrl(`/items/${it.id}`, origin) })) }),
}))
</script>

<style scoped>
.topic-total { color: #637168; font-size: 11px; white-space: nowrap; }
.topic-mobile-directions { display: none; }
.topic-total strong { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 28px; font-weight: 500; color: #234e22; letter-spacing: -.06em; margin-right: 5px; }
.topic-filter-panel { padding: 20px; }
.topic-filter-panel .site-search { background: #f8faf7; }
.topic-filter-panel .site-tabs { border: none; padding: 0; margin: 16px 0 0; gap: 5px; }
.topic-filter-panel .site-tabs a { flex: 1; padding-inline: 10px; }
.technology-filter { border-top: 1px solid #e1e8e0; margin-top: 16px; padding-top: 16px; }
.technology-filter summary { color: #637168; font-size: 11px; cursor: pointer; min-height: 24px; }
.technology-filter .site-filter-pills { margin: 14px 0 0; }
.topic-siblings { padding: 22px 20px 12px; }
.topic-siblings summary { font-size: 13px; font-weight: 600; cursor: pointer; }
.topic-siblings nav { display: grid; margin-top: 15px; }
.topic-siblings nav a { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; padding: 10px 0; color: #637168; font-size: 12px; line-height: 1.7; border-top: 1px solid #edf1eb; }
.topic-siblings nav a > span:last-child { font-size: 10px; font-variant-numeric: tabular-nums; }
.topic-siblings nav a[aria-current='page'] { color: #234e22; font-weight: 600; }
.topic-siblings nav a:hover { color: #327a2d; }
.topic-siblings svg { width: 14px; height: 14px; }
.topic-keywords { padding: 22px 20px; }
.topic-keywords h2 { font-size: 12px; font-weight: 600; }
.topic-keywords > div { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 14px; }
.topic-keywords a { font-size: 11px; color: #637168; min-height: 28px; display: inline-flex; align-items: center; }
.topic-keywords a:hover { color: #234e22; text-decoration: underline; }
@media (max-width: 767px) {
  .topic-filter-panel { padding: 15px; }
  .topic-filter-panel .site-tabs a { padding-inline: 7px; font-size: 11px; }
  .topic-total strong { font-size: 24px; }
  .topic-mobile-directions { display: block; padding: 16px; margin-bottom: 16px; }
  .topic-mobile-directions summary { color: #637168; font-size: 12px; cursor: pointer; }
  .topic-mobile-directions .site-filter-pills { margin-bottom: 0; }
  .topic-siblings { display: none; }
}
</style>
