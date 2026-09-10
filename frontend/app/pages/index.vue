<template>
  <div>
    <header class="mb-5">
      <h1 class="text-xl font-bold text-leaf-800">{{ heading }}</h1>
      <p class="text-sm text-stone-500 mt-1">{{ lede }}</p>
    </header>

    <section v-if="topItem" class="mb-6">
      <NuxtLink :to="`/items/${topItem.id}`"
        class="block rounded-2xl bg-gradient-to-br from-leaf-700 to-leaf-900 text-white p-6 sm:p-8 shadow-lg shadow-leaf-200 hover:from-leaf-600 hover:to-leaf-800 transition-all">
        <div class="flex items-center gap-2 text-xs text-leaf-200 mb-3">
          <span class="px-2 py-0.5 rounded-full bg-white/15 font-medium">今日热点 TOP 1</span>
          <span>{{ topItem.source_name }}</span>
          <span v-if="topItem.sources?.length > 1">· {{ topItem.sources.length }} 个信源同时报道</span>
        </div>
        <h2 class="text-xl sm:text-2xl font-bold leading-snug">{{ topItem.title }}</h2>
        <p class="mt-3 text-sm text-leaf-100 leading-6 line-clamp-2">{{ topItem.summary_zh || topItem.summary }}</p>
      </NuxtLink>
    </section>

    <div class="flex gap-2 mb-5 overflow-x-auto pb-1">
      <NuxtLink v-for="c in categories" :key="c"
        :to="c === '全部' ? '/' : { path: '/', query: { category: c } }"
        class="px-3.5 py-1.5 text-sm rounded-full border whitespace-nowrap transition-colors"
        :class="(category || '全部') === c
          ? 'bg-leaf-600 text-white border-leaf-600'
          : 'bg-white text-stone-600 border-leaf-200 hover:border-leaf-400'">
        {{ c }}
      </NuxtLink>
    </div>

    <div v-if="pending" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else-if="!groups.length" class="text-center text-stone-400 py-16">暂无内容</div>

    <section v-for="g in groups" :key="g.key" class="mb-8">
      <div class="flex items-baseline gap-3 mb-3">
        <h2 class="text-lg font-bold text-leaf-800">{{ g.label }}</h2>
        <span class="text-xs text-stone-400">{{ g.items.length }} 条</span>
        <div class="flex-1 border-t border-leaf-100"></div>
      </div>
      <div class="space-y-3">
        <ItemCard v-for="it in g.items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" />
      </div>
    </section>
  </div>
</template>

<script setup>
const CATEGORIES = ['政策', '报道', '论文', '行业']
const categories = ['全部', ...CATEGORIES]
const route = useRoute()
const api = useApi()

const category = computed(() => (CATEGORIES.includes(route.query.category) ? route.query.category : ''))
const heading = computed(() => (category.value ? `${category.value}精选` : '农业信息化每日精选'))
const lede = computed(() => (
  category.value
    ? `首页精选中的${category.value}资讯`
    : '政策、报道与学术论文聚合，每日更新'
))

const { data, pending, refresh } = await useAsyncData(
  () => `home-${category.value || 'all'}`,
  () => api.items({ mode: 'selected', category: category.value, page_size: 100 }),
  { watch: [category] },
)

const items = computed(() => data.value?.items || [])
const topItem = computed(() => {
  if (category.value || !items.value.length) return null
  return [...items.value].sort((a, b) => b.hotness - a.hotness)[0]
})
const groups = computed(() => {
  const rest = topItem.value ? items.value.filter((i) => i.id !== topItem.value.id) : items.value
  return groupByDay(rest)
})

const path = computed(() => (category.value ? `/?category=${encodeURIComponent(category.value)}` : '/'))
usePageSeo(() => ({
  title: category.value ? `${heading.value} · AgriHot` : DEFAULT_TITLE,
  description: category.value ? `${lede.value}。${DEFAULT_DESC}` : DEFAULT_DESC,
  path: path.value,
  jsonLd: websiteJsonLd,
  keywords: uniqueKeywords([category.value, DEFAULT_KEYWORDS]),
}))
</script>
