<template>
  <PageSkeleton v-if="pending" variant="article" label="正在加载文章…" />
  <div v-else-if="item">
    <nav aria-label="面包屑" class="mb-4 text-xs text-stone-500 leading-6">
      <ol class="flex flex-wrap items-center gap-x-2">
        <li><NuxtLink to="/" class="hover:text-leaf-700">首页</NuxtLink></li>
        <li aria-hidden="true">/</li>
        <li>
          <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path" class="hover:text-leaf-700">{{ item.primary_topic.name }}</NuxtLink>
          <NuxtLink v-else :to="item.category ? { path: '/feed', query: { category: item.category } } : '/feed'" class="hover:text-leaf-700">{{ item.category || '资讯' }}</NuxtLink>
        </li>
      </ol>
    </nav>

    <article>
      <header>
        <div class="flex flex-wrap items-center gap-2">
          <span class="px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 text-xs font-medium">{{ item.category || '资讯' }}</span>
          <span v-if="item.is_selected" class="px-2 py-0.5 rounded-full bg-leaf-100 text-leaf-700 text-xs font-medium">精选</span>
          <span v-if="item.paper?.direction" class="px-2 py-0.5 rounded-full bg-leaf-50 text-leaf-700 border border-leaf-100 text-xs">{{ item.paper.direction }}</span>
        </div>

        <h1 class="mt-3 text-2xl sm:text-[28px] font-bold text-stone-900 leading-snug">{{ item.title }}</h1>
        <p v-if="lede" class="mt-3 text-base text-stone-600 leading-7">{{ lede }}</p>

        <div class="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500">
          <span class="text-leaf-800 font-medium">{{ item.source_name || '未知来源' }}</span>
          <span>{{ dateLabel }}</span>
          <span>阅读 {{ item.view_count ?? 0 }}</span>
          <span v-if="item.hotness >= 60" class="text-amber-600">热度 {{ item.hotness }}</span>
          <span v-if="sourceCount > 1">{{ sourceCount }} 个信源同时报道</span>
          <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path" class="text-leaf-700 hover:underline">{{ item.primary_topic.name }}</NuxtLink>
        </div>
      </header>

      <aside class="my-6 space-y-4">
        <ScorePanel v-if="item.score != null" :score="item.score" :detail="item.score_detail" />
        <ContextPanel :item="item" />
      </aside>

      <div class="min-w-0 mt-5">
        <section v-if="isPaper" class="rounded-xl border border-stone-200 bg-stone-50/80 px-4 py-3">
          <p v-if="authorItems.length" class="text-sm text-stone-700 leading-6">
            <template v-for="(author, index) in authorItems" :key="author.name">
              <span v-if="index"> · </span>
              <a v-if="author.orcid" :href="author.orcid" target="_blank" rel="noopener" class="text-leaf-800 hover:underline">{{ author.name }}</a>
              <span v-else>{{ author.name }}</span>
            </template>
            <span v-if="authorRest"> 等 {{ authorTotal }} 人</span>
          </p>
          <div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
            <span v-if="item.paper?.venue">{{ item.paper.venue }}</span>
            <span v-if="item.paper?.cited_by_count">被引 {{ item.paper.cited_by_count }}</span>
            <a v-if="item.doi" :href="`https://doi.org/${item.doi}`" target="_blank" rel="noopener" class="text-leaf-700 hover:underline break-all">DOI {{ item.doi }}</a>
            <a v-if="item.paper?.oa_url" :href="item.paper.oa_url" target="_blank" rel="noopener" class="text-leaf-700 hover:underline">开放获取 PDF</a>
            <a v-if="item.paper?.openalex_id" :href="`https://openalex.org/${item.paper.openalex_id}`" target="_blank" rel="noopener" class="text-leaf-700 hover:underline">OpenAlex 档案</a>
          </div>
        </section>

        <section v-if="readingRows.length" class="mt-5 grid sm:grid-cols-2 gap-3" aria-label="论文解读">
          <div v-for="row in readingRows" :key="row.key"
            class="rounded-xl border px-4 py-3"
            :class="row.key === 'opportunity' ? 'sm:col-span-2 border-leaf-200 bg-leaf-50/70' : 'border-stone-200 bg-white'">
            <div class="text-[11px] font-bold tracking-wide" :class="row.key === 'opportunity' ? 'text-leaf-800' : 'text-stone-500'">{{ row.label }}</div>
            <p class="mt-1 text-sm text-stone-800 leading-6">{{ row.value }}</p>
          </div>
        </section>

        <figure v-if="showCover" class="mt-5">
          <img :src="item.cover_url" :alt="item.title" class="w-full max-h-80 object-cover rounded-xl border border-stone-200" @error="coverFailed = true">
        </figure>

        <section class="mt-5">
          <div class="flex items-center justify-between gap-3 mb-2">
            <h2 class="text-xs font-bold text-stone-500">{{ item.paper?.card ? '原文摘要' : '摘要' }}</h2>
            <div v-if="item.summary_zh" class="flex rounded-full border border-leaf-200 overflow-hidden text-[11px] font-medium leading-none">
              <button type="button" class="px-2.5 py-1" :class="absLang === 'zh' ? 'bg-leaf-700 text-white' : 'text-leaf-700 hover:bg-leaf-50'" @click="absLang = 'zh'">中</button>
              <button type="button" class="px-2.5 py-1" :class="absLang === 'en' ? 'bg-leaf-700 text-white' : 'text-leaf-700 hover:bg-leaf-50'" @click="absLang = 'en'">EN</button>
            </div>
          </div>
          <p class="text-sm text-stone-700 leading-7 whitespace-pre-line">{{ displayedSummary }}</p>
        </section>

        <section v-if="item.content" class="mt-6 border-t border-stone-200 pt-5">
          <h2 class="text-xs font-bold text-stone-500 mb-3">全文</h2>
          <!-- eslint-disable-next-line vue/no-v-html -- markdown-it html:false -->
          <div class="prose-body text-sm text-stone-700" v-html="contentHtml"></div>
        </section>
        <a v-else :href="primaryUrl" target="_blank" rel="noopener"
          class="mt-6 inline-flex items-center px-4 py-2 rounded-full bg-leaf-700 text-white text-sm font-medium hover:bg-leaf-800">
          阅读原文
        </a>

        <section v-if="tagGroups.length || item.search_phrases?.length" class="mt-6 border-t border-stone-200 pt-5 space-y-4">
          <div v-for="group in tagGroups" :key="group.kind">
            <h2 class="text-xs font-bold text-stone-500 mb-2">{{ group.label }}</h2>
            <div class="flex flex-wrap gap-1.5">
              <NuxtLink v-for="name in group.names" :key="name" :to="tagPath(name)"
                class="px-2.5 py-1 text-xs rounded-full bg-leaf-50 text-leaf-700 border border-leaf-100 hover:bg-leaf-100">
                #{{ name }}
              </NuxtLink>
            </div>
          </div>
          <div v-if="item.search_phrases?.length">
            <h2 class="text-xs font-bold text-stone-500 mb-2">相关检索</h2>
            <div class="flex flex-wrap gap-2">
              <NuxtLink v-for="phrase in item.search_phrases" :key="phrase" :to="tagPath(phrase)"
                class="px-2.5 py-1 text-xs rounded-full bg-white text-stone-700 border border-leaf-200 hover:border-leaf-500 hover:text-leaf-700">
                {{ phrase }}
              </NuxtLink>
            </div>
          </div>
        </section>

        <div v-if="showAdmin" class="mt-6 pt-5 border-t border-dashed border-stone-200 flex gap-2 justify-end">
          <button @click="fetchContent" :disabled="fetching"
            class="px-4 py-1.5 text-xs rounded-full border border-sky-200 text-sky-700 hover:bg-sky-50 disabled:opacity-50">
            {{ fetching ? '抓取中…' : (item.content ? '重新获取全文' : '获取全文') }}
          </button>
          <button @click="showEdit = true"
            class="px-4 py-1.5 text-xs rounded-full border border-leaf-300 text-leaf-700 hover:bg-leaf-50">编辑</button>
          <button @click="remove" :disabled="deleting"
            class="px-4 py-1.5 text-xs rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50">
            {{ deleting ? '删除中…' : '删除' }}
          </button>
        </div>

        <ItemEditModal v-if="showEdit" :item="item" @close="showEdit = false" @saved="onSaved" />
    </div>
    </article>

    <section v-if="sameTopic.length" class="mt-10">
      <h2 class="text-lg font-bold text-leaf-800 mb-3">同一主题</h2>
      <div class="space-y-3">
        <ItemCard v-for="it in sameTopic" :key="it.id" :item="it" />
      </div>
    </section>
    <section v-if="otherRelated.length" class="mt-8">
      <h2 class="text-lg font-bold text-leaf-800 mb-3">{{ otherHeading }}</h2>
      <div class="space-y-3">
        <ItemCard v-for="it in otherRelated" :key="it.id" :item="it" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { tagPath } from '~/utils/seo.js'

const VIEW_DWELL_MS = 3000
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
    try {
      return await api.related(route.params.id)
    } catch {
      return { items: [] }
    }
  },
  { watch: [() => route.params.id] },
)

if (error.value) {
  throw createError({ statusCode: 404, message: '条目不存在', fatal: true })
}

watch(error, (e) => {
  if (e) showError({ statusCode: 404, message: '条目不存在' })
})

const item = computed(() => data.value)
const related = computed(() => (relatedData.value?.items || []).filter((it) => it.id !== item.value?.id))
const sameTopic = computed(() => {
  const code = item.value?.primary_topic?.code
  if (!code) return []
  return related.value.filter((it) => it.primary_topic?.code === code)
})
const otherRelated = computed(() => related.value.filter((it) => !sameTopic.value.includes(it)))
const otherHeading = computed(() => {
  const phrase = item.value?.search_phrases?.[0]
  return phrase ? `${phrase}相关资讯` : '相关报道'
})

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
const sourceCount = computed(() => item.value?.sources?.length || 1)
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
    { key: 'tldr', label: '速览', value: card.tldr },
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
