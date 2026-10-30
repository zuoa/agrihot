<template>
  <div>
    <PageHeading eyebrow="AGRIHOT · 热点专题" title="把进展连起来看" description="围绕同一事件与研究问题，汇集文章、梳理发现，继续追踪。" />
    <form class="special-directory-search site-search" role="search" @submit.prevent="search"><label class="sr-only" for="special-search">搜索专题</label><input id="special-search" v-model="query" type="search" placeholder="搜索研究问题、事件或机构" maxlength="100"><button class="site-button" type="submit">搜索</button></form>
    <nav aria-label="专题类型" class="site-filter-pills my-5"><NuxtLink v-for="type in types" :key="type.value" :to="filterPath(type.value)" :aria-current="kind === type.value ? 'page' : undefined" :class="{ 'is-active': kind === type.value }">{{ type.label }}</NuxtLink></nav>
    <PageSkeleton v-if="pending" />
    <div v-else-if="error" class="site-empty" role="alert"><h2>专题暂时加载失败</h2><button class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
    <div v-else-if="!data?.specials?.length" class="site-empty"><h2>{{ route.query.q ? '没有找到相关专题' : '专题正在积累中' }}</h2><p>从最新文章开始，关注农业科技的新进展。</p><NuxtLink to="/feed" class="site-button site-button-secondary">浏览全部动态</NuxtLink></div>
    <template v-else><p class="site-result-meta">{{ data.total }} 个专题 · 包含历史归档</p><div class="special-directory"><SpecialCard v-for="special in data.specials" :key="special.id" :special="special" /></div><ContentPagination :page="page" :total="data.total" :page-size="12" /></template>
  </div>
</template>
<script setup>
const api = useApi()
const route = useRoute()
const router = useRouter()
const query = ref(String(route.query.q || ''))
const kind = computed(() => ['event', 'research'].includes(route.query.kind) ? route.query.kind : '')
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))
const types = [{ value: '', label: '全部专题' }, { value: 'research', label: '研究前沿' }, { value: 'event', label: '事件追踪' }]
const { data, pending, error, refresh } = await useAsyncData(() => `specials:${kind.value}:${route.query.q || ''}:${page.value}`, () => api.specials({ kind: kind.value, q: route.query.q, page: page.value }), { watch: [kind, page, () => route.query.q] })
watch(() => route.query.q, value => { query.value = String(value || '') })
function filterPath(value) { return { path: '/specials', query: { ...(route.query.q ? { q: route.query.q } : {}), ...(value ? { kind: value } : {}) } } }
function search() { router.push({ path: '/specials', query: { ...(kind.value ? { kind: kind.value } : {}), ...(query.value.trim() ? { q: query.value.trim() } : {}) } }) }
usePageSeo({ title: '热点专题 · AgriHot', description: '聚合农业科技事件与研究前沿，对照关联文章与原始证据，理解共同发现、研究差异与理论方法。', path: '/specials' })
</script>
<style scoped>
.special-directory-search { max-width: 600px; }
.special-directory { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
@media (max-width: 1023px) { .special-directory { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) { .special-directory { grid-template-columns: 1fr; gap: 16px; } }
</style>
