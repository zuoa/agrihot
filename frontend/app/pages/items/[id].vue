<template>
  <div v-if="pending" class="text-center text-stone-400 py-16">加载中…</div>
  <div v-else-if="item">
  <article class="bg-white rounded-2xl border border-leaf-100 p-6 sm:p-8">
    <div class="flex items-center gap-2 text-xs text-stone-400 flex-wrap mb-3">
      <span class="text-leaf-700 font-medium">{{ item.source_name || '未知来源' }}</span>
      <span>·</span>
      <span>{{ dateLabel }}</span>
      <span class="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">{{ item.category }}</span>
      <span v-if="item.paper?.direction"
        class="px-1.5 py-0.5 rounded bg-leaf-50 text-leaf-700 border border-leaf-100">
        {{ item.paper.direction }}
      </span>
      <span v-if="item.is_selected" class="px-1.5 py-0.5 rounded bg-leaf-100 text-leaf-700 font-medium">精选</span>
      <span class="text-amber-600" v-if="item.hotness >= 60">🔥 {{ item.hotness }}</span>
      <span>阅读 {{ item.view_count ?? 0 }}</span>
    </div>

    <h1 class="text-xl sm:text-2xl font-bold text-stone-900 leading-snug">{{ item.title }}</h1>

    <p v-if="authorLine" class="mt-3 text-sm text-stone-500 leading-6">{{ authorLine }}</p>
    <div v-if="item.paper || item.doi" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
      <span v-if="item.paper?.venue">{{ item.paper.venue }}</span>
      <span v-if="item.paper?.cited_by_count">被引 {{ item.paper.cited_by_count }}</span>
      <a v-if="item.doi" :href="`https://doi.org/${item.doi}`" target="_blank" rel="noopener"
        class="text-leaf-700 hover:underline break-all">DOI {{ item.doi }}</a>
      <a v-if="item.paper?.oa_url" :href="item.paper.oa_url" target="_blank" rel="noopener"
        class="text-leaf-700 hover:underline">开放获取 PDF ↗</a>
    </div>

    <InsightCard v-if="item.paper?.card || item.score != null" class="mt-5"
      :card="item.paper?.card" :score="item.score" :detail="item.score_detail" />

    <div class="mt-5 rounded-xl border border-stone-200 bg-white p-4">
      <div class="flex items-center justify-between gap-3 mb-2">
        <div class="text-xs font-bold text-stone-600">{{ item.paper?.card ? '原文摘要' : '摘要' }}</div>
        <div v-if="item.summary_zh"
          class="flex rounded-full border border-leaf-200 overflow-hidden text-[11px] font-medium leading-none">
          <button type="button" class="px-2.5 py-1"
            :class="absLang === 'zh' ? 'bg-leaf-700 text-white' : 'text-leaf-700 hover:bg-white'"
            @click="absLang = 'zh'">中</button>
          <button type="button" class="px-2.5 py-1"
            :class="absLang === 'en' ? 'bg-leaf-700 text-white' : 'text-leaf-700 hover:bg-white'"
            @click="absLang = 'en'">EN</button>
        </div>
      </div>
      <p class="text-sm text-stone-700 leading-7 whitespace-pre-line">{{ displayedSummary }}</p>
    </div>

    <section v-if="item.content" class="mt-5 rounded-xl border border-stone-200 bg-stone-50/70">
      <div class="flex items-center gap-2 px-5 pt-4 pb-3 border-b border-stone-200/80">
        <span class="w-5 h-5 rounded bg-stone-700 text-white grid place-items-center text-[10px] font-bold">文</span>
        <span class="text-xs font-bold text-stone-600">全文</span>
      </div>
      <!-- eslint-disable-next-line vue/no-v-html -- markdown-it html:false -->
      <div class="prose-body text-sm text-stone-700 px-5 py-4" v-html="contentHtml"></div>
    </section>

    <div class="mt-5 flex flex-wrap gap-1.5" v-if="item.tags?.length">
      <NuxtLink v-for="t in item.tags" :key="t" :to="tagPath(t)"
        class="px-2.5 py-1 text-xs rounded-full bg-leaf-50 text-leaf-700 border border-leaf-100 hover:bg-leaf-100 transition-colors">
        #{{ t }}
      </NuxtLink>
    </div>

    <div v-if="item.search_phrases?.length" class="mt-5">
      <div class="text-xs font-bold text-stone-500 mb-2">相关检索</div>
      <div class="flex flex-wrap gap-2">
        <NuxtLink v-for="p in item.search_phrases" :key="p" :to="tagPath(p)"
          class="px-2.5 py-1 text-xs rounded-full bg-white text-stone-700 border border-leaf-200 hover:border-leaf-500 hover:text-leaf-700 transition-colors">
          {{ p }}
        </NuxtLink>
      </div>
    </div>

    <div class="mt-6 border-t border-leaf-100 pt-5">
      <div class="text-xs font-bold text-stone-500 mb-3">
        信源（{{ item.sources?.length || 1 }} 个）<span v-if="item.sources?.length > 1">· 多信源合并去重</span>
      </div>
      <ul class="space-y-2">
        <li v-for="(s, i) in item.sources?.length ? item.sources : [{ name: item.source_name, url: item.url }]" :key="i">
          <a :href="s.url || item.url" target="_blank" rel="noopener"
            class="text-sm text-leaf-700 hover:underline break-all">
            {{ s.name || '原文链接' }} ↗
          </a>
        </li>
      </ul>
    </div>

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

    <ItemEditModal v-if="showEdit" :item="item"
      @close="showEdit = false" @saved="onSaved" />
  </article>

  <section v-if="related.length" class="mt-8">
    <h2 class="text-lg font-bold text-leaf-800 mb-3">{{ relatedHeading }}</h2>
    <div class="space-y-3">
      <ItemCard v-for="it in related" :key="it.id" :item="it" />
    </div>
  </section>
  </div>
</template>

<script setup>
const VIEW_DWELL_MS = 3000
const route = useRoute()
const router = useRouter()
const api = useApi()
const showAdmin = useClientAdmin()

const absLang = ref('zh')
const showEdit = ref(false)
const deleting = ref(false)
const fetching = ref(false)

const { data, pending, error, refresh } = await useAsyncData(
  () => `item-${route.params.id}`,
  () => api.item(route.params.id),
  { watch: [() => route.params.id] },
)

const { data: relatedData } = await useAsyncData(
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
  throw createError({ statusCode: 404, statusMessage: '条目不存在', fatal: true })
}

watch(error, (e) => {
  if (e) showError({ statusCode: 404, statusMessage: '条目不存在' })
})

const item = computed(() => data.value)
const related = computed(() => (relatedData.value?.items || []).filter((it) => it.id !== item.value?.id))
const relatedHeading = computed(() => {
  const phrase = item.value?.search_phrases?.[0]
  return phrase ? `${phrase}相关资讯` : '相关报道'
})

watch(() => route.params.id, () => { absLang.value = 'zh' })

const dateLabel = computed(() => (item.value ? fmtDay(item.value.published_at || item.value.created_at) : ''))
const displayedSummary = computed(() => {
  if (!item.value) return ''
  if (absLang.value === 'zh' && item.value.summary_zh) return item.value.summary_zh
  return item.value.summary
})
const contentHtml = computed(() => renderMarkdown(item.value?.content))
const authorLine = computed(() => {
  const authors = item.value?.paper?.authors
  if (!authors?.length) return ''
  const names = authors.map((a) => a.name).filter(Boolean)
  if (names.length <= 3) return names.join(' · ')
  return `${names.slice(0, 3).join(' · ')} 等 ${names.length} 人`
})

usePageSeo(() => {
  const it = item.value
  if (!it) {
    return { title: '条目不存在 · AgriHot', description: DEFAULT_DESC, path: route.path, noindex: true }
  }
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
