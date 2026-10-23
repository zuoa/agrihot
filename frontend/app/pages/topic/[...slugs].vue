<template>
  <div>
    <PageSkeleton v-if="!node" label="正在加载主题…" />
    <template v-else>
    <nav aria-label="主题路径" class="flex flex-wrap gap-2 text-xs text-stone-500 mb-5">
      <NuxtLink to="/topic" class="hover:text-leaf-700">主题索引</NuxtLink>
      <template v-if="parent"><span aria-hidden="true">/</span><NuxtLink :to="parent.path" class="hover:text-leaf-700">{{ parent.name }}</NuxtLink></template>
      <span aria-hidden="true">/</span><span class="text-leaf-800" aria-current="page">{{ node.name }}</span>
    </nav>
    <header class="border-l-4 border-leaf-600 pl-4 mb-6">
      <h1 class="text-2xl font-bold text-leaf-900">{{ node.name }}</h1>
      <p class="text-sm text-stone-500 leading-7 mt-2">{{ node.description }}</p>
    </header>

    <details v-if="siblings.length" class="mb-5 border-y border-leaf-200 py-3" open>
      <summary class="text-xs text-stone-500 cursor-pointer select-none">{{ parent ? '同领域方向' : '细分方向' }}</summary>
      <div class="flex flex-wrap gap-2 mt-3">
        <NuxtLink v-if="parent" :to="parent.path" class="topic-chip">全部</NuxtLink>
        <NuxtLink v-for="child in siblings" :key="child.code" :to="child.path" class="topic-chip"
          :class="child.code === node.code ? 'topic-chip-active' : ''" :aria-current="child.code === node.code ? 'page' : undefined">
          {{ child.name }} <span class="opacity-60 text-xs tabular-nums">{{ child.count }}</span>
        </NuxtLink>
      </div>
    </details>

    <form class="mb-4 flex flex-wrap gap-2" @submit.prevent="search">
      <label class="sr-only" for="topic-search">在主题内搜索</label>
      <input id="topic-search" v-model="searchInput" type="search" placeholder="在这个主题内搜索…"
        class="min-w-0 flex-1 rounded-lg bg-white border border-leaf-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-leaf-500" />
      <button class="rounded-lg bg-leaf-700 text-white text-sm px-4 py-2 hover:bg-leaf-800">搜索</button>
    </form>
    <nav aria-label="内容类型" class="flex flex-wrap gap-2 mb-4">
      <NuxtLink v-for="c in ['', '政策', '报道', '论文', '行业']" :key="c" :to="filterLink({ category: c })"
        class="topic-chip" :class="category === c ? 'topic-chip-active' : ''" :aria-current="category === c ? 'true' : undefined">{{ c || '全部类型' }}</NuxtLink>
    </nav>
    <details v-if="technologies.length || selectedTech.length" class="mb-5 rounded-lg bg-white border border-leaf-100 px-3 py-2" :open="selectedTech.length > 0">
      <summary class="text-xs text-stone-500 cursor-pointer">技术筛选<span v-if="selectedTech.length"> · 已选 {{ selectedTech.length }} 项</span></summary>
      <div class="flex flex-wrap gap-2 pt-3 pb-1">
        <NuxtLink v-for="t in technologies" :key="t.name" :to="technologyLink(t.name)" class="topic-chip"
          :class="selectedTech.includes(t.name) ? 'topic-chip-active' : ''">{{ t.name }} <span class="opacity-60 text-xs">{{ t.count }}</span></NuxtLink>
        <NuxtLink v-if="selectedTech.length" :to="filterLink({ technology: [] })" class="text-xs text-leaf-700 self-center underline">清除技术筛选</NuxtLink>
      </div>
    </details>
    <div v-if="facets?.keywords?.length && !hasFilters" class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-stone-500 mb-5">
      <span>相关热词</span><NuxtLink v-for="tag in facets.keywords.slice(0, 6)" :key="tag.name" :to="tagPath(tag.name)" class="text-leaf-700 hover:underline">#{{ tag.name }}</NuxtLink>
    </div>
    <div class="flex justify-between gap-3 items-center mb-3 text-xs text-stone-500" aria-live="polite">
      <span>{{ total }} 篇内容</span><NuxtLink v-if="hasFilters" :to="node.path" class="text-leaf-700 hover:underline">清除全部筛选</NuxtLink>
    </div>
    <PageSkeleton v-if="pending" />
    <div v-else-if="error" class="text-center text-stone-500 py-12" role="alert">
      <p>内容加载失败，请重试。</p><button class="mt-3 text-leaf-700 underline" @click="refresh">重新加载</button>
    </div>
    <div v-else-if="!items.length" class="text-center text-stone-500 rounded-xl border border-dashed border-leaf-200 py-14 px-4">
      <p>{{ hasFilters ? '当前筛选下暂无内容。' : '这个方向还没有内容，先看看同领域的其他方向。' }}</p>
      <NuxtLink :to="hasFilters ? node.path : (parent?.path || '/topic')" class="inline-block mt-4 text-sm text-leaf-700 underline">{{ hasFilters ? '清除筛选' : '浏览更多主题' }}</NuxtLink>
    </div>
    <div v-else class="space-y-3"><ItemCard v-for="it in items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
    <nav v-if="totalPages > 1" aria-label="内容分页" class="flex justify-center items-center gap-4 mt-7 text-sm">
      <NuxtLink v-if="page > 1" :to="filterLink({ page: page - 1 }, false)" class="topic-chip">上一页</NuxtLink>
      <span class="text-stone-500 tabular-nums">{{ page }} / {{ totalPages }}</span>
      <NuxtLink v-if="page < totalPages" :to="filterLink({ page: page + 1 }, false)" class="topic-chip">下一页</NuxtLink>
    </nav>
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
const totalPages = computed(() => Math.ceil(total.value / 20))
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
