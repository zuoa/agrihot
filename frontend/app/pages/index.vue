<template>
  <div>
    <PageHeading eyebrow="AGRIHOT · 农业科技情报" :title="category ? `${category}精选` : '值得关注的农业新进展'" :description="lede">
      <NuxtLink to="/feed" class="site-text-link">查看全部动态<ArticleIcon name="external" /></NuxtLink>
    </PageHeading>
    <div class="site-columns">
      <div class="site-column-main">
        <section v-if="!pending && topItem" class="featured-story">
          <NuxtLink :to="`/items/${topItem.id}`" class="featured-story-link">
            <div class="featured-kicker"><span><ArticleIcon name="insight" />精选焦点</span><span v-if="topItem.score != null" class="featured-score">{{ topItem.score }}<span> / 100</span></span></div>
            <h2>{{ topItem.title }}</h2>
            <p>{{ topItem.paper?.card?.tldr || topItem.summary_zh || topItem.summary }}</p>
            <div class="featured-footer"><span>{{ topItem.source_name }}<span v-if="topItem.sources?.length > 1"> · {{ topItem.sources.length }} 个信源</span></span><span class="featured-read">阅读全文<ArticleIcon name="external" /></span></div>
          </NuxtLink>
        </section>
        <nav aria-label="精选分类" class="site-tabs">
          <NuxtLink v-for="c in categories" :key="c" :to="c === '全部' ? '/' : { path: '/', query: { category: c } }" :aria-current="(category || '全部') === c ? 'page' : undefined">{{ c }}</NuxtLink>
        </nav>
        <PageSkeleton v-if="pending" />
        <div v-else-if="error" class="site-empty" role="alert"><h2>精选暂时加载失败</h2><p>稍后重试，继续查看农业政策与研究进展。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
        <div v-else-if="!groups.length && !topItem" class="site-empty"><h2>暂无精选内容</h2><p>可以先查看已收录的政策、报道和论文。</p><NuxtLink to="/feed" class="site-button site-button-secondary">浏览全部动态</NuxtLink></div>
        <template v-if="!pending && !error">
          <section v-for="g in groups" :key="g.key" class="site-section">
            <div class="site-section-heading"><h2>{{ g.label }}</h2><span>{{ g.items.length }} 条精选</span></div>
            <div class="site-card-list"><ItemCard v-for="it in g.items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
          </section>
          <ContentPagination :page="page" :total="data?.total || 0" :page-size="pageSize" />
        </template>
      </div>
      <BrowseSidebar />
    </div>
  </div>
</template>

<script setup>
const CATEGORIES = ['政策', '报道', '论文', '行业']
const categories = ['全部', ...CATEGORIES]
const route = useRoute()
const api = useApi()
const pageSize = 20

const category = computed(() => (CATEGORIES.includes(route.query.category) ? route.query.category : ''))
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))
const heading = computed(() => (category.value ? `${category.value}精选` : '农业科技情报 · 每日精选'))
const lede = computed(() => (
  category.value
    ? `首页精选中的${category.value}资讯`
    : '追踪农业政策、前沿研究与技术进展，让有价值的信息更早被看见。'
))

const { data, pending, error, refresh } = await useAsyncData(
  () => `home:${category.value || 'all'}:${page.value}`,
  () => api.items({ mode: 'selected', category: category.value, page: page.value, page_size: pageSize }),
  { watch: [category, page] },
)

const items = computed(() => data.value?.items || [])
const topItem = computed(() => {
  if (category.value || page.value > 1 || !items.value.length) return null
  return [...items.value].sort((a, b) => b.hotness - a.hotness)[0]
})
const groups = computed(() => {
  const rest = topItem.value ? items.value.filter((i) => i.id !== topItem.value.id) : items.value
  return groupByDay(rest)
})

const path = computed(() => {
  const query = new URLSearchParams()
  if (category.value) query.set('category', category.value)
  if (page.value > 1) query.set('page', String(page.value))
  return query.size ? `/?${query}` : '/'
})
usePageSeo(() => ({
  title: category.value ? `${heading.value} · AgriHot` : DEFAULT_TITLE,
  description: category.value ? `${lede.value}。${DEFAULT_DESC}` : DEFAULT_DESC,
  path: path.value,
  jsonLd: websiteJsonLd,
  keywords: uniqueKeywords([category.value, DEFAULT_KEYWORDS]),
}))
</script>

<style scoped>
.featured-story { margin-bottom: 24px; overflow: hidden; border: 1px solid #d3dfce; border-radius: 16px; background: white; }
.featured-story-link { display: block; padding: 28px 30px; border-left: 3px solid #234e22; }
.featured-kicker { display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #234e22; }
.featured-kicker > span:first-child { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; }
.featured-kicker svg { width: 16px; height: 16px; }
.featured-score { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 25px; letter-spacing: -.06em; }
.featured-score > span { color: #637168; font-size: 10px; letter-spacing: 0; }
.featured-story h2 { margin-top: 20px; font-size: 26px; font-weight: 700; letter-spacing: -.03em; line-height: 1.6; overflow-wrap: anywhere; }
.featured-story-link:hover h2 { color: #327a2d; }
.featured-story p { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; margin-top: 15px; color: #637168; font-size: 14px; line-height: 1.95; }
.featured-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin-top: 24px; padding-top: 18px; border-top: 1px solid #e1e8e0; color: #637168; font-size: 11px; }
.featured-read { display: inline-flex; align-items: center; gap: 6px; color: #234e22; }
.featured-read svg { width: 16px; height: 16px; }
@media (max-width: 767px) { .featured-story-link { padding: 22px 20px; } .featured-story h2 { font-size: 22px; margin-top: 16px; } .featured-story p { font-size: 13px; } .featured-footer { margin-top: 20px; } }
</style>
