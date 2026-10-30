<template>
  <PageSkeleton v-if="pending" variant="article" label="正在加载文章…" />
  <div v-else-if="item" class="item-detail">
    <nav aria-label="面包屑" class="detail-breadcrumb">
      <NuxtLink to="/feed" class="back-link"><ArticleIcon name="back" />全部动态</NuxtLink>
      <ol>
        <li><NuxtLink to="/">首页</NuxtLink></li>
        <li aria-hidden="true"><ArticleIcon name="chevron" /></li>
        <li>
          <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path">{{ item.primary_topic.name }}</NuxtLink>
          <NuxtLink v-else :to="item.category ? { path: '/feed', query: { category: item.category } } : '/feed'">{{ item.category || '资讯' }}</NuxtLink>
        </li>
        <li aria-hidden="true"><ArticleIcon name="chevron" /></li>
        <li aria-current="page">正文</li>
      </ol>
    </nav>

    <div class="detail-layout">
      <article class="article-sheet">
        <header class="article-header">
          <div class="article-kicker">
            <span class="category-label">{{ item.category || '资讯' }}</span>
            <span v-if="item.is_selected" class="selected-label"><ArticleIcon name="insight" />精选推荐</span>
            <span v-if="item.paper?.direction" class="direction-label">{{ item.paper.direction }}</span>
          </div>
          <h1>{{ item.title }}</h1>
          <div class="article-meta">
            <span class="article-source">{{ item.source_name || '未知来源' }}</span>
            <span class="meta-dot" aria-hidden="true">·</span>
            <time :datetime="item.published_at || item.created_at">{{ dateLabel }}</time>
            <span>阅读 {{ item.view_count ?? 0 }}</span>
            <span v-if="item.hotness >= 60" class="hotness-label">热度 {{ item.hotness }}</span>
          </div>
          <div class="article-actions">
            <a :href="primaryUrl" target="_blank" rel="noopener" class="original-link">阅读原文<ArticleIcon name="external" /></a>
            <span class="reading-time"><ArticleIcon name="clock" />{{ readingTimeLabel }}</span>
          </div>
          <div v-if="lede" class="article-takeaway">
            <p class="takeaway-label"><ArticleIcon name="insight" />核心看点</p>
            <p class="takeaway-text">{{ lede }}</p>
          </div>
        </header>

        <nav v-if="articleSections.length > 1" aria-label="文章目录" class="article-contents">
          <span>本文内容</span>
          <a v-for="section in articleSections" :key="section.id" :href="`#${section.id}`">{{ section.label }}</a>
        </nav>

        <div class="article-body">
          <section v-if="hasPaperMeta" class="paper-record" aria-label="论文信息">
            <div class="record-heading"><ArticleIcon name="document" /><h2>论文信息</h2></div>
            <p v-if="authorItems.length" class="paper-authors">
              <template v-for="(author, index) in authorItems" :key="author.name">
                <span v-if="index" class="author-separator"> / </span>
                <a v-if="author.orcid" :href="author.orcid" target="_blank" rel="noopener">{{ author.name }}</a>
                <span v-else>{{ author.name }}</span>
              </template>
              <span v-if="authorRest"> 等 {{ authorTotal }} 人</span>
            </p>
            <div class="paper-publication">
              <span v-if="item.paper?.venue">{{ item.paper.venue }}</span>
              <span v-if="item.paper?.cited_by_count">被引 {{ item.paper.cited_by_count }} 次</span>
            </div>
            <div v-if="item.doi || item.paper?.oa_url || item.paper?.openalex_id" class="paper-links">
              <a v-if="item.doi" :href="`https://doi.org/${item.doi}`" target="_blank" rel="noopener" class="doi-link">DOI: {{ item.doi }}<ArticleIcon name="external" /></a>
              <a v-if="item.paper?.oa_url" :href="item.paper.oa_url" target="_blank" rel="noopener">开放获取 PDF<ArticleIcon name="external" /></a>
              <a v-if="item.paper?.openalex_id" :href="`https://openalex.org/${item.paper.openalex_id}`" target="_blank" rel="noopener">OpenAlex 档案<ArticleIcon name="external" /></a>
            </div>
          </section>

          <section v-if="readingRows.length" id="paper-reading" class="reading-section" aria-labelledby="paper-reading-title">
            <div class="section-heading"><h2 id="paper-reading-title">论文解读</h2><span class="section-caption">AI 辅助整理</span></div>
            <dl class="paper-insights">
              <div v-for="row in readingRows" :key="row.key" class="insight-row" :class="{ 'insight-opportunity': row.key === 'opportunity' }">
                <dt>{{ row.label }}</dt><dd>{{ row.value }}</dd>
              </div>
            </dl>
          </section>

          <figure v-if="showCover" class="article-cover">
            <img :src="item.cover_url" :alt="item.title" decoding="async" @error="coverFailed = true">
          </figure>

          <section v-if="displayedSummary" id="article-abstract" class="reading-section" aria-labelledby="abstract-title">
            <div class="section-heading">
              <h2 id="abstract-title">{{ isPaper ? '论文摘要' : '内容摘要' }}</h2>
              <div v-if="item.summary_zh" class="language-switch" role="group" aria-label="摘要语言">
                <button type="button" :aria-pressed="absLang === 'zh'" @click="absLang = 'zh'">中文</button>
                <button type="button" :aria-pressed="absLang === 'en'" @click="absLang = 'en'">原文</button>
              </div>
            </div>
            <p class="abstract-text" :lang="absLang === 'zh' && item.summary_zh ? 'zh-CN' : undefined">{{ displayedSummary }}</p>
          </section>

          <section v-if="item.content" id="article-fulltext" class="reading-section fulltext-section" aria-labelledby="fulltext-title">
            <div class="section-heading"><h2 id="fulltext-title">全文</h2><span class="section-caption">{{ item.source_name }}</span></div>
            <!-- eslint-disable-next-line vue/no-v-html -- markdown-it html:false -->
            <div class="prose-body article-prose" v-html="contentHtml"></div>
          </section>

          <div class="article-end-source">
            <div><p>{{ isPaper ? '论文原文与出版信息' : '了解完整信息' }}</p><span>{{ item.source_name || '原始来源' }}</span></div>
            <a :href="primaryUrl" target="_blank" rel="noopener">{{ isPaper ? '查看论文原文' : '前往原文' }}<ArticleIcon name="external" /></a>
          </div>

          <section v-if="tagGroups.length || item.search_phrases?.length" id="article-topics" class="article-topics" aria-labelledby="topics-title">
            <div class="section-heading"><h2 id="topics-title">继续探索</h2></div>
            <div v-for="group in tagGroups" :key="group.kind" class="topic-group">
              <h3>{{ group.label }}</h3>
              <div class="topic-links"><NuxtLink v-for="name in group.names" :key="name" :to="tagPath(name)"><span aria-hidden="true">#</span>{{ name }}</NuxtLink></div>
            </div>
            <div v-if="item.search_phrases?.length" class="topic-group">
              <h3>相关检索</h3>
              <div class="topic-links search-links"><NuxtLink v-for="phrase in item.search_phrases" :key="phrase" :to="tagPath(phrase)">{{ phrase }}<ArticleIcon name="external" /></NuxtLink></div>
            </div>
          </section>

          <div v-if="showAdmin" class="article-admin">
            <span>内容管理</span>
            <EmbeddingBadge v-if="item.embedding_ready" />
            <button type="button" @click="fetchContent" :disabled="fetching">{{ fetching ? '抓取中…' : (item.content ? '重新获取全文' : '获取全文') }}</button>
            <button type="button" @click="showEdit = true">编辑</button>
            <button type="button" @click="remove" :disabled="deleting" class="delete-action">{{ deleting ? '删除中…' : '删除' }}</button>
          </div>
        </div>
        <ItemEditModal v-if="showEdit" :item="item" @close="showEdit = false" @saved="onSaved" />
      </article>

      <aside class="detail-sidebar" :class="{ 'sidebar-with-score': item.score != null }" aria-label="文章参考信息">
        <ContextPanel :item="item" />
        <ScorePanel v-if="item.score != null" :key="item.id" :score="item.score" :detail="item.score_detail" />
        <p class="sidebar-note">摘要与解读由 AI 辅助整理，引用请以原始来源为准。</p>
      </aside>
    </div>

    <section v-if="itemSpecials?.specials?.length" class="related-reading" aria-label="所属专题">
      <div class="related-heading"><h2>在专题中理解这篇文章</h2><NuxtLink to="/specials">全部专题</NuxtLink></div>
      <div class="related-grid"><SpecialCard v-for="special in itemSpecials.specials" :key="special.id" :special="special" /></div>
    </section>
    <section v-if="recommendations.length" class="related-reading" aria-labelledby="related-reading-title">
      <div class="related-heading">
        <h2 id="related-reading-title">相关阅读</h2>
        <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path">查看同主题<ArticleIcon name="chevron" /></NuxtLink>
      </div>
      <div class="related-grid">
        <ArticleRecommendation v-for="entry in recommendationPreview" :key="entry.article.id" :item="entry.article" :same-topic="entry.sameTopic" />
      </div>
      <details v-if="moreRecommendations.length" :key="item.id" class="related-more">
        <summary><span class="show-more">展开其余 {{ moreRecommendations.length }} 篇</span><span class="show-less">收起更多</span><ArticleIcon name="chevron" /></summary>
        <div class="related-grid">
          <ArticleRecommendation v-for="entry in moreRecommendations" :key="entry.article.id" :item="entry.article" :same-topic="entry.sameTopic" />
        </div>
      </details>
    </section>
  </div>
</template>

<script setup>
import { tagPath } from '~/utils/seo.js'

const VIEW_DWELL_MS = 3000
const RECOMMENDATION_PREVIEW_COUNT = 4
const TAG_GROUPS = [
  { kind: 'technology', label: '技术' },
  { kind: 'region', label: '地区' },
  { kind: 'organization', label: '机构' },
  { kind: 'keyword', label: '其他' },
]

const route = useRoute()
const router = useRouter()
const api = useApi()
const showAdmin = useClientAdmin()

const absLang = ref('zh')
const showEdit = ref(false)
const deleting = ref(false)
const fetching = ref(false)
const coverFailed = ref(false)

const { data, pending, error, refresh } = await useAsyncData(
  () => `item-${route.params.id}`,
  () => api.item(route.params.id),
  { watch: [() => route.params.id] },
)

const { data: relatedData } = await useLazyAsyncData(
  () => `related-${route.params.id}`,
  async () => {
    const id = String(route.params.id)
    try {
      return { ...await api.related(id), forItemId: id }
    } catch {
      return { items: [], similar: [], forItemId: id }
    }
  },
  { watch: [() => route.params.id] },
)

const { data: itemSpecials } = await useLazyAsyncData(
  () => `item-specials:${route.params.id}`,
  () => api.specials({ item_id: route.params.id }).catch(() => ({ specials: [] })),
  { watch: [() => route.params.id] },
)

if (error.value) {
  throw createError({ statusCode: 404, message: '条目不存在', fatal: true })
}

watch(error, (e) => {
  if (e) showError({ statusCode: 404, message: '条目不存在' })
})

const item = computed(() => data.value)
const recommendations = computed(() => {
  if (relatedData.value?.forItemId !== String(item.value?.id)) return []
  const code = item.value?.primary_topic?.code
  const seen = new Set([String(item.value?.id)])
  return [...(relatedData.value?.items || []), ...(relatedData.value?.similar || [])]
    .filter((article) => {
      const id = String(article.id)
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    .map((article) => ({ article, sameTopic: Boolean(code && article.primary_topic?.code === code) }))
    .sort((a, b) => Number(b.sameTopic) - Number(a.sameTopic))
})
const recommendationPreview = computed(() => recommendations.value.slice(0, RECOMMENDATION_PREVIEW_COUNT))
const moreRecommendations = computed(() => recommendations.value.slice(RECOMMENDATION_PREVIEW_COUNT))

watch(() => route.params.id, () => {
  absLang.value = 'zh'
  coverFailed.value = false
})

const dateLabel = computed(() => (item.value ? fmtDay(item.value.published_at || item.value.created_at) : ''))
const displayedSummary = computed(() => {
  if (!item.value) return ''
  if (absLang.value === 'zh' && item.value.summary_zh) return item.value.summary_zh
  return item.value.summary
})
const contentHtml = computed(() => renderMarkdown(item.value?.content))
const isPaper = computed(() => Boolean(item.value?.paper || item.value?.doi))
const hasPaperMeta = computed(() => Boolean(
  authorTotal.value || item.value?.paper?.venue || item.value?.paper?.cited_by_count
  || item.value?.doi || item.value?.paper?.oa_url || item.value?.paper?.openalex_id,
))
const readingTimeLabel = computed(() => {
  const text = [lede.value, displayedSummary.value, item.value?.content, ...readingRows.value.map(row => row.value)].filter(Boolean).join(' ')
  const chineseCharacters = (text.match(/[\u3400-\u9fff]/g) || []).length
  const words = text.replace(/[\u3400-\u9fff]/g, ' ').trim().split(/\s+/).filter(Boolean).length
  const minutes = Math.max(1, Math.ceil(chineseCharacters / 400 + words / 220))
  return `约 ${minutes} 分钟阅读`
})
const articleSections = computed(() => [
  readingRows.value.length && { id: 'paper-reading', label: '论文解读' },
  displayedSummary.value && { id: 'article-abstract', label: '摘要' },
  item.value?.content && { id: 'article-fulltext', label: '全文' },
  (tagGroups.value.length || item.value?.search_phrases?.length) && { id: 'article-topics', label: '相关主题' },
].filter(Boolean))
const lede = computed(() => {
  const card = item.value?.paper?.card
  if (card?.tldr) return card.tldr
  return item.value?.score_detail?.comment || ''
})
const showCover = computed(() => Boolean(item.value?.cover_url) && !coverFailed.value)
const sourceList = computed(() => {
  const sources = item.value?.sources
  if (sources?.length) return sources
  return [{ name: item.value?.source_name, url: item.value?.url }]
})
const primaryUrl = computed(() => sourceList.value[0]?.url || item.value?.url || '#')

const authorItems = computed(() => {
  const authors = (item.value?.paper?.authors || []).filter((author) => author?.name)
  return authors.slice(0, 3)
})
const authorTotal = computed(() => (item.value?.paper?.authors || []).filter((author) => author?.name).length)
const authorRest = computed(() => authorTotal.value > 3)

const readingRows = computed(() => {
  const card = item.value?.paper?.card
  if (!card) return []
  return [
    { key: 'method', label: '方法', value: card.method },
    { key: 'finding', label: '发现', value: card.finding },
    { key: 'opportunity', label: '机会点', value: card.opportunity },
  ].filter((row) => row.value)
})

const tagGroups = computed(() => {
  const meta = item.value?.tag_meta
  const names = item.value?.tags || []
  const kindOf = Object.fromEntries((meta || []).map((row) => [row.name, row.kind]))
  return TAG_GROUPS.map((group) => ({
    ...group,
    names: names.filter((name) => (kindOf[name] || 'keyword') === group.kind),
  })).filter((group) => group.names.length)
})

usePageSeo(() => {
  const it = item.value
  if (!it) return null
  return {
    title: `${it.title} · AgriHot`,
    description: it.summary_zh || it.summary,
    path: `/items/${it.id}`,
    type: 'article',
    image: it.cover_url || undefined,
    jsonLd: (origin) => itemJsonLd(it, origin),
    keywords: itemKeywords(it),
    tags: it.tags,
    section: it.category,
    publishedTime: it.published_at || it.created_at,
  }
})

let dwellTimer = null
let viewRecorded = false

function stopDwell() {
  if (dwellTimer != null) {
    clearTimeout(dwellTimer)
    dwellTimer = null
  }
}

function startDwell() {
  stopDwell()
  if (viewRecorded || !item.value || !import.meta.client) return
  if (String(item.value.id) !== String(route.params.id)) return
  if (document.visibilityState !== 'visible') return
  dwellTimer = setTimeout(recordView, VIEW_DWELL_MS)
}

async function recordView() {
  if (viewRecorded || !item.value) return
  viewRecorded = true
  stopDwell()
  const id = item.value.id
  try {
    const res = await api.recordView(id)
    if (item.value?.id === id && res.view_count != null) {
      item.value.view_count = res.view_count
    }
  } catch {
    // 计数失败不影响阅读
  }
}

function onVisibility() {
  if (document.visibilityState === 'visible') startDwell()
  else stopDwell()
}

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibility)
  startDwell()
})
onUnmounted(() => {
  stopDwell()
  document.removeEventListener('visibilitychange', onVisibility)
})
watch(() => route.params.id, () => {
  viewRecorded = false
  startDwell()
})
watch(() => item.value?.id, startDwell)

function onSaved(it) {
  data.value = it
}

async function fetchContent() {
  if (item.value.content && !confirm('已有全文，重新抓取将覆盖现有内容，确定继续？')) return
  fetching.value = true
  try {
    data.value = await api.adminFetchContent(item.value.id)
  } catch (e) {
    alert(e.message)
  } finally {
    fetching.value = false
  }
}

async function remove() {
  if (!confirm(`确定删除「${item.value.title.slice(0, 30)}」？此操作不可恢复。`)) return
  deleting.value = true
  try {
    await api.adminDeleteItem(item.value.id)
    router.back()
  } catch (e) {
    alert(e.message)
  } finally {
    deleting.value = false
  }
}

</script>

<style scoped>
.item-detail {
  --article-ink: #20332a;
  --article-muted: #637168;
  --article-green: #234e22;
  --article-line: #e1e8e0;
  --article-soft: #f4f8f2;
  --article-paper: #fff;
  color: var(--article-ink);
  padding-bottom: 20px;
}
.item-detail :is(a, button, summary):focus-visible { outline: 2px solid var(--article-green); outline-offset: 4px; border-radius: 4px; }
.item-detail svg { width: 18px; height: 18px; flex-shrink: 0; }
.detail-breadcrumb { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 0 22px; font-size: 12px; color: var(--article-muted); }
.back-link { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; color: var(--article-green); }
.detail-breadcrumb ol { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
.detail-breadcrumb ol svg { width: 12px; height: 12px; }
.detail-breadcrumb a:hover { color: var(--article-green); text-decoration: underline; text-underline-offset: 4px; }
.detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) 252px; gap: 26px; align-items: start; }
.article-sheet { min-width: 0; overflow: clip; border: 1px solid var(--article-line); border-radius: 20px; background: var(--article-paper); }
.article-header { padding: 34px 38px 28px; }
.article-kicker { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 12px; }
.category-label { font-weight: 700; color: var(--article-green); padding-right: 12px; border-right: 1px solid var(--article-line); letter-spacing: .12em; }
.category-label:only-child { padding-right: 0; border-right: 0; }
.selected-label { display: inline-flex; gap: 4px; align-items: center; color: var(--article-green); }
.selected-label svg { width: 13px; height: 13px; }
.direction-label { color: var(--article-muted); }
.article-header h1 { margin-top: 18px; font-size: clamp(26px, 2.5vw, 34px); font-weight: 700; line-height: 1.5; letter-spacing: -.035em; overflow-wrap: anywhere; text-wrap: pretty; }
.article-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-top: 20px; font-size: 12px; line-height: 1.6; color: var(--article-muted); }
.article-source { font-weight: 600; color: var(--article-green); overflow-wrap: anywhere; }
.article-meta time { font-variant-numeric: tabular-nums; }
.article-meta .meta-dot { margin: 0 -7px; }
.hotness-label { color: #946324; }
.article-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; margin-top: 22px; }
.original-link { display: inline-flex; min-height: 40px; align-items: center; gap: 18px; border-radius: 8px; padding: 8px 15px; background: var(--article-green); color: white; font-size: 13px; font-weight: 500; transition: background .15s; }
.original-link:hover { background: #327a2d; }
.reading-time { display: inline-flex; align-items: center; gap: 6px; color: var(--article-muted); font-size: 12px; }
.reading-time svg { width: 15px; height: 15px; }
.article-takeaway { margin-top: 28px; padding: 18px 20px; background: var(--article-soft); border-left: 3px solid var(--article-green); border-radius: 0 10px 10px 0; }
.takeaway-label { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700; letter-spacing: .06em; color: var(--article-green); }
.takeaway-label svg { width: 14px; height: 14px; }
.takeaway-text { margin-top: 9px; font-family: 'Songti SC', 'STSong', 'Noto Serif CJK SC', serif; font-size: 16px; font-weight: 500; line-height: 1.9; overflow-wrap: anywhere; }
.article-contents { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 20px; margin: 0 38px; padding: 10px 0; border-block: 1px solid var(--article-line); font-size: 12px; }
.article-contents > span { color: var(--article-muted); font-size: 11px; }
.article-contents a { display: inline-flex; min-height: 30px; align-items: center; color: var(--article-green); }
.article-contents a:hover { text-decoration: underline; text-underline-offset: 5px; }
.article-body { padding: 0 38px 32px; }
.paper-record { margin-top: 28px; padding: 18px 20px; background: var(--article-soft); border: 1px solid var(--article-line); border-radius: 10px; overflow-wrap: anywhere; }
.record-heading { display: flex; align-items: center; gap: 7px; color: var(--article-muted); font-size: 11px; font-weight: 600; }
.record-heading svg { width: 15px; height: 15px; }
.paper-authors { margin-top: 12px; font-size: 13px; line-height: 1.9; }
.paper-record a { color: var(--article-green); }
.paper-record a:hover { text-decoration: underline; text-underline-offset: 3px; }
.author-separator { color: #b3beb2; }
.paper-publication { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 5px; color: var(--article-muted); font-size: 12px; line-height: 1.7; }
.paper-links { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; font-size: 11px; }
.paper-links a { display: inline-flex; align-items: center; gap: 3px; min-height: 28px; max-width: 100%; }
.paper-links svg { width: 13px; height: 13px; }
.doi-link { word-break: break-all; }
.reading-section { margin-top: 32px; scroll-margin-top: 100px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 17px; }
.section-heading h2 { font-size: 17px; font-weight: 700; letter-spacing: -.02em; }
.section-caption { color: var(--article-muted); font-size: 11px; text-align: right; }
.paper-insights { border: 1px solid var(--article-line); border-radius: 12px; overflow: hidden; }
.insight-row { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 16px; padding: 19px 20px; }
.insight-row + .insight-row { border-top: 1px solid var(--article-line); }
.insight-row dt { padding-top: 3px; font-size: 12px; font-weight: 600; color: var(--article-muted); }
.insight-row dd { font-size: 14px; line-height: 1.9; overflow-wrap: anywhere; }
.insight-opportunity { background: var(--article-soft); }
.insight-opportunity dt { color: var(--article-green); }
.article-cover { margin-top: 28px; }
.article-cover img { width: 100%; max-height: 420px; object-fit: contain; border-radius: 10px; background: var(--article-soft); }
.language-switch { display: inline-flex; gap: 2px; border: 1px solid var(--article-line); background: var(--article-soft); padding: 3px; border-radius: 7px; }
.language-switch button { min-height: 30px; padding: 4px 11px; border-radius: 5px; color: var(--article-muted); font-size: 11px; }
.language-switch button[aria-pressed='true'] { background: white; color: var(--article-green); font-weight: 600; box-shadow: 0 1px 3px #20332a14; }
.language-switch button:hover { color: var(--article-green); }
.abstract-text { color: #435046; font-size: 15px; line-height: 2.05; white-space: pre-line; overflow-wrap: anywhere; }
.fulltext-section { border-top: 1px solid var(--article-line); padding-top: 28px; }
.article-prose { font-size: 15px; line-height: 2; overflow-wrap: anywhere; }
.article-prose :deep(p) { line-height: 2; margin-bottom: 20px; }
.article-prose :deep(:is(h1, h2, h3, h4)) { color: var(--article-ink); line-height: 1.65; margin-top: 28px; margin-bottom: 14px; }
.article-prose :deep(h1) { font-size: 23px; }
.article-prose :deep(h2) { font-size: 20px; }
.article-prose :deep(h3) { font-size: 17px; }
.article-prose :deep(:is(ul, ol)) { margin-block: 16px; }
.article-prose :deep(li) { padding-left: 3px; line-height: 1.9; }
.article-prose :deep(blockquote) { background: var(--article-soft); border-left-width: 3px; padding: 14px 20px; border-radius: 0 8px 8px 0; }
.article-prose :deep(blockquote p:last-child) { margin-bottom: 0; }
.article-prose :deep(table) { display: block; max-width: 100%; overflow-x: auto; font-size: 13px; }
.article-prose :deep(pre) { max-width: 100%; font-size: 13px; }
.article-end-source { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; margin-top: 32px; padding: 20px 0; border-block: 1px solid var(--article-line); }
.article-end-source p { font-size: 13px; font-weight: 500; }
.article-end-source span { display: block; margin-top: 5px; color: var(--article-muted); font-size: 11px; overflow-wrap: anywhere; }
.article-end-source a { display: inline-flex; align-items: center; gap: 6px; color: var(--article-green); font-size: 12px; min-height: 36px; }
.article-end-source a:hover { text-decoration: underline; text-underline-offset: 4px; }
.article-topics { padding-top: 28px; scroll-margin-top: 100px; }
.topic-group { display: grid; grid-template-columns: 54px minmax(0, 1fr); align-items: start; gap: 8px 12px; margin-top: 14px; }
.topic-group h3 { font-size: 11px; color: var(--article-muted); padding-top: 9px; }
.topic-links { display: flex; flex-wrap: wrap; gap: 7px; }
.topic-links a { display: inline-flex; align-items: center; gap: 4px; min-height: 34px; max-width: 100%; padding: 6px 10px; border-radius: 6px; background: var(--article-soft); border: 1px solid transparent; color: var(--article-green); font-size: 12px; overflow-wrap: anywhere; }
.topic-links a > span { opacity: .45; }
.topic-links a:hover { border-color: #b5ccb0; background: #eaf2e6; }
.search-links a { background: white; border-color: var(--article-line); color: var(--article-muted); }
.search-links svg { width: 13px; height: 13px; }
.article-admin { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px 14px; margin-top: 28px; border-top: 1px dashed var(--article-line); padding-top: 18px; font-size: 11px; }
.article-admin > span { color: var(--article-muted); margin-right: auto; }
.article-admin button { min-height: 32px; color: var(--article-green); }
.article-admin button:hover { text-decoration: underline; }
.article-admin button:disabled { opacity: .5; }
.article-admin .delete-action { color: #b64d43; }
.detail-sidebar { display: grid; gap: 16px; min-width: 0; }
.sidebar-note { font-size: 11px; color: var(--article-muted); line-height: 1.9; padding-inline: 8px; }
.related-reading { margin-top: 32px; padding: 24px 28px 8px; border: 1px solid var(--article-line); border-radius: 16px; background: var(--article-paper); }
.related-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.related-heading h2 { font-size: 20px; font-weight: 700; }
.related-heading > a { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; font-size: 12px; color: var(--article-green); }
.related-heading > a:hover { text-decoration: underline; text-underline-offset: 4px; }
.related-heading > a svg { width: 14px; height: 14px; }
.related-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 32px; }
.related-more { border-top: 1px solid var(--article-line); }
.related-more summary { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px; list-style: none; color: var(--article-green); font-size: 12px; cursor: pointer; scroll-margin-top: 100px; }
.related-more summary::-webkit-details-marker { display: none; }
.related-more summary:hover { background: var(--article-soft); }
.related-more summary svg { width: 14px; height: 14px; transform: rotate(90deg); }
.related-more[open] summary svg { transform: rotate(-90deg); }
.related-more .show-less, .related-more[open] .show-more { display: none; }
.related-more[open] .show-less { display: inline; }

@media (max-width: 1023px) {
  .detail-layout { grid-template-columns: minmax(0, 1fr); gap: 24px; }
  .detail-sidebar { grid-template-columns: minmax(0, 1fr); align-items: start; }
  .sidebar-with-score { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .sidebar-note { grid-column: 1 / -1; }
  .article-header { padding: 28px; }
  .article-contents { margin-inline: 28px; gap: 4px 14px; }
  .article-body { padding-inline: 28px; }
  .article-header h1 { font-size: 28px; }
}
@media (max-width: 767px) {
  .detail-breadcrumb { margin-bottom: 14px; gap: 10px; font-size: 11px; }
  .detail-breadcrumb ol { gap: 4px; }
  .detail-breadcrumb ol li:nth-last-child(-n+2) { display: none; }
  .detail-layout { gap: 24px; }
  .article-sheet { border-radius: 14px; }
  .article-header { padding: 24px 22px; }
  .article-header h1 { font-size: 26px; line-height: 1.55; margin-top: 16px; }
  .article-meta { margin-top: 16px; gap: 7px 12px; font-size: 11px; }
  .article-actions { margin-top: 20px; }
  .article-takeaway { margin-top: 24px; padding: 16px; }
  .takeaway-text { font-size: 15px; }
  .article-contents { margin-inline: 22px; gap: 4px 14px; }
  .article-contents > span { display: none; }
  .article-body { padding: 0 22px 24px; }
  .paper-record { padding: 16px; }
  .reading-section, .article-topics { scroll-margin-top: 148px; }
  .insight-row { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 16px; }
  .insight-row dt { padding: 0; }
  .related-reading { margin-top: 24px; padding: 16px 20px 4px; }
  .related-heading { gap: 12px; margin-bottom: 8px; }
  .related-heading h2 { font-size: 18px; }
  .related-heading > a { min-height: 44px; }
  .related-more summary { scroll-margin-top: 148px; }
  .original-link, .language-switch button, .topic-links a, .article-end-source a, .article-admin button { min-height: 44px; }
  .paper-links a { min-height: 36px; }
}
@media (max-width: 639px) {
  .detail-sidebar, .related-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 479px) {
  .article-header { padding-inline: 19px; }
  .article-body { padding-inline: 19px; }
  .article-contents { margin-inline: 19px; }
  .article-header h1 { font-size: 24px; }
  .article-kicker { gap: 8px; font-size: 11px; }
  .abstract-text, .article-prose { font-size: 14px; }
  .topic-group { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .topic-group h3 { padding: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .original-link { transition: none; }
}
</style>
