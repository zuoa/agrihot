<template>
  <div>
    <PageHeading eyebrow="持续收录 · 政策 / 报道 / 论文 / 行业" title="全部动态" description="从最新政策到前沿研究，查找你关心的农业进展。" />
    <div class="site-columns">
      <div class="site-column-main">
        <form role="search" class="site-search feed-search" @submit.prevent="search">
          <ArticleIcon name="search" /><label for="feed-search" class="sr-only">搜索标题或摘要</label><input id="feed-search" v-model="qInput" type="search" placeholder="搜索标题、摘要或关键词…" /><button type="submit" class="site-button">搜索</button>
        </form>
        <nav aria-label="动态分类" class="site-tabs"><NuxtLink v-for="c in categories" :key="c" :to="categoryLink(c)" :aria-current="(category || '全部') === c ? 'page' : undefined">{{ c }}</NuxtLink></nav>
        <nav v-if="category === '论文' && directions.length" aria-label="论文方向" class="site-filter-pills"><NuxtLink v-for="d in [{ name: '全部方向', count: 0 }, ...directions]" :key="d.name" :to="directionLink(d.name === '全部方向' ? '' : d.name)" :aria-current="(direction || '全部方向') === d.name ? 'page' : undefined">{{ d.name }}<span v-if="d.count" class="tabular-nums opacity-60">{{ d.count }}</span></NuxtLink></nav>
        <div class="site-result-meta" aria-live="polite"><span>{{ q ? `“${q}”的搜索结果` : direction || (category ? `${category}资讯` : '全部已收录内容') }}<template v-if="!pending && !error"> · {{ total.toLocaleString('zh-CN') }} 条</template></span><NuxtLink v-if="q" :to="searchResetLink">清除搜索</NuxtLink></div>
        <PageSkeleton v-if="pending" />
        <div v-else-if="error" class="site-empty" role="alert"><h2>动态暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
        <template v-else>
          <section v-for="g in groups" :key="g.key" class="feed-day">
            <div class="site-section-heading"><h2>{{ g.label }}</h2><span>{{ g.items.length }} 条</span></div>
            <div class="site-card-list"><ItemCard v-for="it in g.items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
          </section>
          <div v-if="!groups.length" class="site-empty"><h2>{{ q ? '没有找到相关内容' : '暂无内容' }}</h2><p>{{ q ? '试试缩短关键词，或选择其他内容类型。' : '可以按主题浏览已收录的农业进展。' }}</p><NuxtLink to="/topic" class="site-button site-button-secondary">浏览主题</NuxtLink></div>
          <ContentPagination :page="page" :total="total" :page-size="pageSize" />
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
const router = useRouter()
const api = useApi()
const pageSize = 20

const category = computed(() => (CATEGORIES.includes(route.query.category) ? route.query.category : ''))
const direction = computed(() => (category.value === '论文' && route.query.direction ? String(route.query.direction) : ''))
const q = computed(() => (route.query.q ? String(route.query.q) : ''))
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))
const qInput = ref(q.value)
watch(q, (v) => { qInput.value = v })

const heading = computed(() => {
  const bits = ['全部动态']
  if (category.value) bits.push(category.value)
  if (category.value === '论文' && direction.value) bits.push(direction.value)
  return bits.join(' · ')
})

const { data, pending, error, refresh } = await useAsyncData(
  () => `feed-${category.value}-${direction.value}-${q.value}-${page.value}`,
  async () => {
    const [list, dirs] = await Promise.all([
      api.items({
        mode: 'all',
        category: category.value,
        direction: direction.value,
        q: q.value,
        page: page.value,
        page_size: pageSize,
      }),
      category.value === '论文' ? api.paperDirections().catch(() => []) : Promise.resolve([]),
    ])
    return { list, dirs }
  },
  { watch: [category, direction, q, page] },
)

const items = computed(() => data.value?.list?.items || [])
const total = computed(() => data.value?.list?.total || 0)
const directions = computed(() => data.value?.dirs || [])
const groups = computed(() => groupByDay(items.value))

const searchResetLink = computed(() => {
  const query = { ...route.query }
  delete query.q
  delete query.page
  return { path: '/feed', query }
})

function categoryLink(c) {
  const query = {}
  if (c !== '全部') query.category = c
  if (q.value.trim()) query.q = q.value.trim()
  return { path: '/feed', query }
}

function directionLink(name) {
  const query = { category: '论文' }
  if (name) query.direction = name
  if (q.value.trim()) query.q = q.value.trim()
  return { path: '/feed', query }
}

function search() {
  const query = { ...route.query }
  const trimmed = qInput.value.trim()
  if (trimmed) query.q = trimmed
  else delete query.q
  delete query.page
  router.replace({ path: '/feed', query })
}

const path = computed(() => {
  const query = new URLSearchParams()
  if (category.value) query.set('category', category.value)
  if (direction.value) query.set('direction', direction.value)
  if (q.value.trim()) query.set('q', q.value.trim())
  if (page.value > 1) query.set('page', String(page.value))
  const qs = query.toString()
  return qs ? `/feed?${qs}` : '/feed'
})

usePageSeo(() => ({
  title: `${heading.value} · AgriHot`,
  description: q.value
    ? `搜索「${q.value}」的农业信息化资讯`
    : `${heading.value}：政策、报道、学术论文与行业动态。`,
  path: path.value,
  noindex: Boolean(q.value),
  keywords: uniqueKeywords([category.value, direction.value, q.value, DEFAULT_KEYWORDS]),
}))
</script>

<style scoped>
.feed-search { margin-bottom: 16px; }
.feed-day + .feed-day { margin-top: 32px; }
</style>
