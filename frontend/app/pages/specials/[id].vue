<template>
  <div v-if="special?.document" class="special-detail">
    <nav class="site-breadcrumb" aria-label="面包屑"><NuxtLink to="/">首页</NuxtLink><span>/</span><NuxtLink to="/specials">热点专题</NuxtLink><span>/</span><span>{{ special.kind === 'research' ? '研究前沿' : '事件追踪' }}</span></nav>
    <header class="special-header"><p class="page-eyebrow">{{ special.kind === 'research' ? '研究前沿 · RESEARCH' : '事件追踪 · DEVELOPMENTS' }}<span v-if="special.status === 'archived'"> · 已归档</span></p><h1>{{ special.title }}</h1><p class="special-scope">{{ special.scope }}</p><div class="special-meta"><span>{{ special.item_count }} 篇文章</span><span>{{ special.source_count }} 组独立证据</span><span v-if="special.coverage_start">{{ fmtDate(special.coverage_start) }} — {{ fmtDate(special.coverage_end) }}</span><span>内容更新 {{ fmtDate(special.content_updated_at) }}</span></div></header>
    <div class="special-body">
      <div class="special-main">
        <section id="overview" class="special-section special-overview"><div class="special-section-title"><h2>专题速览</h2><span>先了解整体进展</span></div><SpecialClaim :claim="special.document.overview" :source-numbers="sourceNumbers" /><p class="special-change"><strong>本次更新</strong>{{ special.changes }}</p></section>
        <section id="findings" class="special-section"><div class="special-section-title"><h2>关键发现</h2><span>共同之处与差异都保留</span></div><div class="special-findings"><article v-for="(claim, index) in special.document.findings" :key="index"><SpecialClaim :claim="claim" :source-numbers="sourceNumbers" show-label /></article></div></section>
        <section v-if="special.document.timeline.length" id="timeline" class="special-section"><div class="special-section-title"><h2>事件脉络</h2></div><ol class="special-timeline"><li v-for="(entry, index) in special.document.timeline" :key="index"><time :datetime="entry.date">{{ entry.date }}</time><SpecialClaim :claim="entry.claim" :source-numbers="sourceNumbers" /></li></ol></section>
        <section v-if="special.document.comparisons.length" id="comparison" class="special-section"><div class="special-section-title"><h2>研究比较</h2></div><p class="special-section-note">对照研究条件与局限，具体指标请结合原文阅读。</p><div class="special-table-wrap" role="region" aria-label="研究比较表，可横向滚动" tabindex="0"><table class="special-table"><caption class="sr-only">研究对象、方法、数据条件、结果及局限</caption><thead><tr><th scope="col">研究</th><th v-for="field in comparisonFields" :key="field.key" scope="col">{{ field.label }}</th></tr></thead><tbody><tr v-for="row in special.document.comparisons" :key="row.item_id"><th scope="row"><NuxtLink :to="`/items/${row.item_id}`">{{ sourceById[`i${row.item_id}`]?.title }}</NuxtLink><p><a v-for="citation in row.citations" :key="citation.source_id" :href="`#source-${citation.source_id}`">[{{ sourceNumbers[citation.source_id] }}]</a></p></th><td v-for="field in comparisonFields" :key="field.key">{{ row[field.key] }}</td></tr></tbody></table></div></section>
        <section id="articles" class="special-section"><div class="special-section-title"><h2>关联文章</h2><span>{{ special.total }} 篇</span></div><nav class="site-filter-pills mb-5" aria-label="文章类型"><NuxtLink :to="articleFilter('')" :aria-current="!category ? 'page' : undefined" :class="{ 'is-active': !category }">全部</NuxtLink><NuxtLink v-for="value in special.categories" :key="value" :to="articleFilter(value)" :aria-current="category === value ? 'page' : undefined" :class="{ 'is-active': category === value }">{{ value }}</NuxtLink></nav><template v-for="group in articleGroups" :key="group.role"><h3 v-if="group.entries.length" class="special-article-group">{{ group.label }}</h3><article v-for="entry in group.entries" :key="entry.item.id" class="special-article"><p class="special-relevance">{{ entry.reason }}</p><ItemCard :item="entry.item" @updated="refresh" @deleted="refresh" /></article></template><p v-if="!special.articles.length" class="special-section-note">该类型暂无文章。</p><ContentPagination :page="page" :total="special.total" :page-size="12" /></section>
        <section v-if="special.document.extensions.length" id="explore" class="special-section"><div class="special-section-title"><h2>深入理解</h2><span>主体、方法与延伸问题</span></div><details v-for="(extension, index) in special.document.extensions" :key="index" class="special-extension"><summary><span class="extension-kind">{{ extensionKinds[extension.kind] }}</span><h3>{{ extension.title }}</h3><span class="extension-plus" aria-hidden="true">＋</span></summary><div class="special-extension-content"><SpecialClaim :claim="extension.body" :source-numbers="sourceNumbers" :show-label="extension.body.kind === 'inference'" /></div></details></section>
        <section id="sources" class="special-section"><div class="special-section-title"><h2>参考资料</h2><span>每条发现都可以回到来源</span></div><ol class="special-sources"><li v-for="source in special.sources" :id="`source-${source.id}`" :key="source.id"><span class="source-number">{{ sourceNumbers[source.id] }}</span><div><NuxtLink v-if="source.item_id" :to="`/items/${source.item_id}`">{{ source.title }}</NuxtLink><a v-else :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }} ↗</a><p>{{ source.publisher }} · {{ source.kind === 'internal' ? '站内文章' : '外部补充' }} · {{ source.basis === 'abstract' ? '依据摘要' : '依据已获取正文片段' }}<span v-if="source.retrieved_at"> · 获取于 {{ fmtDate(source.retrieved_at) }}</span></p><details v-if="quotesFor(source.id).length"><summary>查看引用摘录</summary><blockquote v-for="quote in quotesFor(source.id)" :key="quote">{{ quote }}</blockquote></details></div></li></ol></section>
        <section class="special-section"><h2 class="special-updates-title">更新记录</h2><ul class="special-updates"><li v-for="(update, index) in special.updates" :key="index"><time>{{ fmtDate(update.date) }}</time><span>{{ update.changes }}</span></li></ul></section>
        <div v-if="special.topics.length" class="special-topics"><span>继续浏览相关方向</span><NuxtLink v-for="topic in special.topics" :key="topic.slug" :to="`/topic/${topic.slug}`" class="topic-chip">{{ topic.name }}</NuxtLink></div>
        <p class="site-disclaimer">本专题由 AI 基于引用资料综合整理；“延伸思考”为分析性推论。研究结果的适用范围与引用请以原文为准。</p>
      </div>
      <aside class="special-directory-nav"><p>本页内容</p><nav aria-label="专题目录"><a href="#overview">专题速览</a><a href="#findings">关键发现</a><a v-if="special.document.timeline.length" href="#timeline">事件脉络</a><a v-if="special.document.comparisons.length" href="#comparison">研究比较</a><a href="#articles">关联文章</a><a v-if="special.document.extensions.length" href="#explore">深入理解</a><a href="#sources">参考资料</a></nav><NuxtLink to="/specials">浏览其他专题 ↗</NuxtLink></aside>
    </div>
  </div>
</template>
<script setup>
const route = useRoute()
const api = useApi()
const category = computed(() => String(route.query.category || ''))
const page = computed(() => Math.max(1, parseInt(route.query.page, 10) || 1))
const { data: special, error, refresh } = await useAsyncData(() => `special:${route.params.id}:${category.value}:${page.value}`, () => api.special(route.params.id, { page: page.value, category: category.value }), { watch: [() => route.params.id, category, page] })
if (error.value) throw createError({ statusCode: error.value.statusCode || 500, message: error.value.statusCode === 404 ? '专题不存在或正在重新核验' : '专题暂时无法加载', fatal: true })
if (special.value?.redirect_to) await navigateTo(`/specials/${special.value.redirect_to}`, { redirectCode: 301, replace: true })
watch(error, value => { if (value) showError({ statusCode: value.statusCode || 500, message: '专题暂时无法加载' }) })
const sourceById = computed(() => Object.fromEntries((special.value?.sources || []).map(s => [s.id, s])))
const sourceNumbers = computed(() => Object.fromEntries((special.value?.sources || []).map((s, index) => [s.id, index + 1])))
const comparisonFields = [{ key: 'object', label: '对象' }, { key: 'method', label: '方法' }, { key: 'data', label: '数据条件' }, { key: 'result', label: '结果' }, { key: 'limitation', label: '局限' }]
const extensionKinds = { entity: '相关主体', method: '理论方法', question: '延伸问题' }
const articleGroups = computed(() => [{ role: 'core', label: '核心材料', entries: (special.value?.articles || []).filter(e => e.role === 'core') }, { role: 'background', label: '背景阅读', entries: (special.value?.articles || []).filter(e => e.role === 'background') }])
function articleFilter(value) { return { path: route.path, query: value ? { category: value } : {}, hash: '#articles' } }
function quotesFor(id) {
  const doc = special.value?.document
  if (!doc) return []
  const blocks = [doc.overview, ...doc.findings, ...doc.comparisons, ...doc.timeline.map(e => e.claim), ...doc.extensions.map(e => e.body)]
  return [...new Set(blocks.flatMap(b => b.citations).filter(c => c.source_id === id).map(c => c.quote))]
}
usePageSeo(() => ({ title: `${special.value?.title || '热点专题'} · AgriHot`, description: special.value?.summary || '', path: `/specials/${route.params.id}`, keywords: special.value?.topics?.map(t => t.name).join(',') }))
</script>
<style scoped>
.special-header { max-width: 900px; margin-bottom: 38px; }
.special-header h1 { font-family: 'Songti SC', 'Noto Serif CJK SC', SimSun, serif; font-size: 38px; font-weight: 700; line-height: 1.6; margin-top: 14px; letter-spacing: -.025em; overflow-wrap: anywhere; }
.special-scope { margin-top: 15px; font-size: 15px; line-height: 1.9; color: var(--site-muted); }
.special-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; font-size: 11px; color: var(--site-muted); margin-top: 20px; }
.special-body { display: grid; grid-template-columns: minmax(0, 1fr) 160px; gap: 64px; align-items: start; }
.special-main { min-width: 0; }
.special-section { margin-bottom: 38px; }
.special-section-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 20px; justify-content: space-between; padding-bottom: 13px; border-bottom: 1px solid var(--site-line); margin-bottom: 20px; }
.special-section-title h2, .special-updates-title { font-size: 20px; font-weight: 650; }
.special-section-title > span, .special-section-note { font-size: 12px; color: var(--site-muted); line-height: 1.8; }
.special-overview { background: white; border: 1px solid var(--site-line); border-left: 3px solid var(--site-green); border-radius: 0 12px 12px 0; padding: 25px 28px; }
.special-change { display: flex; flex-wrap: wrap; gap: 6px 13px; padding-top: 16px; margin-top: 20px; border-top: 1px solid var(--site-line); font-size: 11px; color: var(--site-muted); line-height: 1.8; }
.special-change strong { color: var(--site-green); font-weight: 500; }
.special-findings { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
.special-findings > article { padding: 22px; border: 1px solid var(--site-line); border-radius: 10px; background: white; }
.special-findings > article:last-child:nth-child(odd) { grid-column: 1 / -1; }
.special-timeline { border-left: 1px solid #b8ccb1; margin-left: 8px; padding-left: 26px; }
.special-timeline li { position: relative; padding-bottom: 26px; }
.special-timeline li::before { position: absolute; content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--site-green); left: -30px; top: 8px; }
.special-timeline time { display: block; font-size: 11px; color: var(--site-muted); margin-bottom: 8px; }
.special-table-wrap { overflow-x: auto; margin-top: 16px; border: 1px solid var(--site-line); border-radius: 8px; background: white; }
.special-table { border-collapse: collapse; min-width: 850px; width: 100%; text-align: left; font-size: 12px; line-height: 1.9; }
.special-table th, .special-table td { padding: 15px; vertical-align: top; border-bottom: 1px solid var(--site-line); min-width: 130px; overflow-wrap: anywhere; }
.special-table thead { background: var(--site-soft); color: var(--site-muted); }
.special-table tbody th { font-weight: 500; max-width: 180px; color: var(--site-green); }
.special-table a:hover { text-decoration: underline; }
.special-article-group { color: var(--site-muted); margin: 22px 0 13px; font-size: 12px; }
.special-article { margin-bottom: 18px; }
.special-relevance { font-size: 12px; line-height: 1.9; border-left: 2px solid #9bb793; padding-left: 12px; margin-bottom: 10px; color: var(--site-green); }
.special-extension { border-bottom: 1px solid var(--site-line); }
.special-extension summary { display: flex; align-items: baseline; gap: 13px; padding: 22px 0; cursor: pointer; list-style: none; }
.special-extension summary::-webkit-details-marker { display: none; }
.extension-kind { font-size: 10px; color: var(--site-muted); flex-shrink: 0; }
.special-extension h3 { font-size: 16px; font-weight: 550; }
.extension-plus { margin-left: auto; color: var(--site-green); }
.special-extension[open] .extension-plus { transform: rotate(45deg); }
.special-extension-content { padding: 0 0 24px; }
.special-sources { display: grid; gap: 23px; }
.special-sources > li { display: flex; gap: 13px; padding: 6px 0; }
.source-number { color: var(--site-muted); min-width: 22px; font: 12px/1.8 monospace; }
.special-sources > li > div { min-width: 0; }
.special-sources a { font-size: 13px; color: var(--site-green); line-height: 1.8; overflow-wrap: anywhere; }
.special-sources p, .special-sources summary { font-size: 11px; color: var(--site-muted); line-height: 1.9; margin-top: 6px; }
.special-sources summary { cursor: pointer; }
.special-sources blockquote { border-left: 2px solid var(--site-line); margin: 10px 0; padding-left: 12px; font-size: 12px; line-height: 1.9; color: var(--site-muted); overflow-wrap: anywhere; }
.special-sources > li:target { background: #edf4e9; outline: 6px solid #edf4e9; border-radius: 4px; }
.special-updates { display: grid; gap: 12px; margin-top: 18px; color: var(--site-muted); font-size: 11px; line-height: 1.8; }
.special-updates li { display: flex; gap: 18px; }
.special-updates time { flex-shrink: 0; }
.special-topics { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.special-topics > span { font-size: 11px; color: var(--site-muted); margin-right: 6px; }
.special-directory-nav { position: sticky; top: 100px; font-size: 12px; }
.special-directory-nav > p { color: var(--site-muted); font-size: 10px; margin-bottom: 15px; }
.special-directory-nav nav { border-left: 1px solid var(--site-line); display: grid; }
.special-directory-nav nav a { padding: 12px 18px; }
.special-directory-nav a:hover { color: var(--site-green); text-decoration: underline; }
.special-directory-nav > a { display: block; margin-top: 25px; color: var(--site-green); }
@media (max-width: 1023px) { .special-body { grid-template-columns: minmax(0, 1fr) 130px; gap: 25px; } .special-header h1 { font-size: 32px; } }
@media (max-width: 767px) { .special-header h1 { font-size: 28px; } .special-header { margin-bottom: 26px; } .special-body { display: flex; flex-direction: column; gap: 24px; } .special-directory-nav { position: static; order: -1; width: 100%; } .special-directory-nav > p, .special-directory-nav > a { display: none; } .special-directory-nav nav { display: flex; overflow-x: auto; border-left: 0; border-bottom: 1px solid var(--site-line); } .special-directory-nav nav a { white-space: nowrap; padding: 12px; } .special-main { width: 100%; } .special-findings { grid-template-columns: 1fr; } .special-overview { padding: 22px 20px; } .special-section { margin-bottom: 28px; } }
</style>
