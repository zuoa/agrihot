<template>
  <PageSkeleton v-if="pending" variant="article" label="正在加载日报…" />
  <div v-else-if="daily">
    <nav class="site-breadcrumb" aria-label="面包屑"><NuxtLink to="/dailies"><ArticleIcon name="back" />日报归档</NuxtLink><ArticleIcon name="chevron" /><span aria-current="page">{{ daily.date }}</span></nav>
    <PageHeading :eyebrow="`${dateLabel} · 农业农村日报`" :title="daily.title" :description="(daily.content || '').replace(/[*-]/g, '').slice(0, 120)">
      <ClientOnly><button ref="shareTrigger" type="button" class="site-button" @click="openShare">分享本期<ArticleIcon name="external" /></button></ClientOnly>
    </PageHeading>
    <div v-if="showAdmin" class="mb-5 flex flex-wrap items-center gap-3"><button type="button" class="site-button site-button-secondary" :disabled="generating" @click="regenerate">{{ generating ? '生成中…' : '重新生成本日日报' }}</button><span v-if="generateMsg" class="text-xs text-stone-500" role="status">{{ generateMsg }}</span></div>
    <div class="site-columns">
      <div class="site-column-main">
        <section v-if="daily.highlights?.length" class="daily-highlights site-surface" aria-labelledby="daily-highlights-title">
          <div class="daily-highlights-heading"><div><ArticleIcon name="insight" /><h2 id="daily-highlights-title">本期要点</h2></div><span>{{ daily.highlights.length }} 条关注</span></div>
          <ul><li v-for="(highlight, index) in daily.highlights" :key="index">{{ highlight }}</li></ul>
        </section>
        <nav v-if="sections.length" aria-label="本期栏目" class="site-filter-pills daily-mobile-contents"><a v-for="section in sections" :key="section.id" :href="`#daily-${section.id}`">{{ section.name }}<span class="opacity-60">{{ section.items.length }}</span></a></nav>
        <section v-for="section in sections" :id="`daily-${section.id}`" :key="section.id" class="site-section">
          <div class="site-section-heading"><h2>{{ section.name }}</h2><span>{{ section.items.length }} 条资讯</span></div>
          <div class="site-card-list"><ItemCard v-for="it in section.items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" /></div>
        </section>
        <p class="site-disclaimer">本日报内容整理自公开来源，学术论文元数据来自 OpenAlex 等开放接口；外文资料已译为中文，翻译与摘要仅供参考；引用与决策请以官方原文与正式出版物为准。</p>
      </div>
      <aside class="daily-outline browse-sidebar" aria-label="本期索引">
        <section class="site-surface"><p class="page-eyebrow">{{ daily.date }}</p><h2>本期索引</h2><p class="daily-outline-count">{{ daily.highlights?.length || 0 }} 条要点 · {{ daily.items?.length || 0 }} 条资讯</p><nav><a v-for="section in sections" :key="section.id" :href="`#daily-${section.id}`"><span>{{ section.name }}</span><span>{{ section.items.length }}</span></a></nav><NuxtLink to="/dailies" class="site-text-link">浏览往期日报<ArticleIcon name="external" /></NuxtLink></section>
      </aside>
    </div>
    <ClientOnly>
      <div v-if="sharing" class="share-backdrop" @click.self="closeShare" @keydown="shareKeydown">
        <section ref="shareDialog" class="share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-title" tabindex="-1">
          <div class="share-heading"><h2 id="share-title">分享本期日报</h2><button type="button" aria-label="关闭分享" @click="closeShare"><ArticleIcon name="close" /></button></div>
          <div class="share-body" :aria-busy="!shareImg && !shareError">
            <div v-if="shareError" class="site-empty" role="alert"><p>{{ shareError }}</p><button type="button" class="site-button site-button-secondary" @click="openShare">重新生成</button></div>
            <div v-else-if="!shareImg" class="site-empty" role="status"><p>正在生成分享图片…</p></div>
            <img v-else :src="shareImg" :alt="`${daily.date} 农业农村日报分享图`" class="share-preview" />
          </div>
          <div v-if="shareImg" class="share-actions">
            <a :href="shareImg" :download="`agrihot-daily-${daily.date}.png`" class="site-button share-download">保存高清图片<ArticleIcon name="download" /></a>
            <p class="share-hint">手机端可长按图片保存 · 扫码阅读本期日报</p>
          </div>
        </section>
      </div>
      <div v-if="sharing" class="share-render" aria-hidden="true"><DailyShareCard v-if="shareQr" ref="shareCard" :daily="daily" :qr="shareQr" /></div>
    </ClientOnly>
  </div>
</template>

<script setup>
const route = useRoute()
const api = useApi()
const showAdmin = useClientAdmin()
const requestURL = useRequestURL()

const sharing = ref(false)
const shareQr = ref('')
const shareImg = ref('')
const shareError = ref('')
const shareCard = ref(null)
const shareDialog = ref(null)
const shareTrigger = ref(null)
const generating = ref(false)
const generateMsg = ref('')
let shareAttempt = 0

onBeforeUnmount(() => { shareAttempt++ })

const { data, pending, error, refresh } = await useAsyncData(
  () => `daily-${route.params.date}`,
  () => api.daily(route.params.date),
  { watch: [() => route.params.date] },
)

if (error.value) {
  throw createError({ statusCode: 404, message: '该日期暂无日报', fatal: true })
}
watch(error, (e) => {
  if (e) showError({ statusCode: 404, message: '该日期暂无日报' })
})

const daily = computed(() => data.value)
const dateLabel = computed(() => (daily.value ? fmtDay(daily.value.date) : ''))
const sections = computed(() => {
  if (!daily.value) return []
  const defs = [
    { id: 'policy', name: '政策', cats: ['政策'] },
    { id: 'reports', name: '报道', cats: ['报道'] },
    { id: 'research', name: '学术论文', cats: ['论文'] },
    { id: 'industry', name: '行业动态', cats: ['行业'] },
  ]
  return defs
    .map((d) => ({ id: d.id, name: d.name, items: (daily.value.items || []).filter((i) => d.cats.includes(i.category)) }))
    .filter((s) => s.items.length)
})

usePageSeo(() => {
  const d = daily.value
  if (!d) return null
  const desc = (d.highlights || []).join(' ') || d.content || d.title
  return {
    title: `${d.title}（${d.date}）｜农业农村日报`,
    description: desc,
    path: `/dailies/${d.date}`,
    type: 'article',
    jsonLd: (origin) => dailyJsonLd(d, origin),
    keywords: dailyKeywords(d),
    tags: (d.items || []).flatMap((it) => it.tags || []),
    section: '农业农村日报',
    publishedTime: d.date,
  }
})

function closeShare() {
  shareAttempt++
  sharing.value = false
  shareQr.value = ''
  shareImg.value = ''
  shareError.value = ''
  shareTrigger.value?.focus()
}

function shareKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeShare()
    return
  }
  if (event.key !== 'Tab') return
  const controls = shareDialog.value?.querySelectorAll('button, a[href]')
  if (!controls?.length) return
  const first = controls[0]
  const last = controls[controls.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === shareDialog.value)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

async function openShare() {
  closeShare()
  const attempt = shareAttempt
  sharing.value = true
  await nextTick()
  shareDialog.value?.focus()
  try {
    const [{ default: QRCode }, { toPng }] = await Promise.all([
      import('qrcode'),
      import('html-to-image'),
    ])
    const url = `${requestURL.origin}/dailies/${daily.value.date}`
    const qr = await QRCode.toDataURL(url, {
      width: 528, margin: 4,
      color: { dark: '#234e22', light: '#ffffff' },
    })
    if (attempt !== shareAttempt) return
    shareQr.value = qr
    await nextTick()
    const card = shareCard.value.$el
    await Promise.all([
      document.fonts.ready,
      ...Array.from(card.querySelectorAll('img'), (img) => img.decode()),
    ])
    if (attempt !== shareAttempt) return
    const png = await toPng(card, { pixelRatio: 2, cacheBust: true })
    if (attempt === shareAttempt) shareImg.value = png
  } catch {
    if (attempt === shareAttempt) shareError.value = '图片生成失败，请重新生成。'
  }
}

async function regenerate() {
  if (!confirm(`重新生成 ${route.params.date} 的日报？现有内容会被覆盖。`)) return
  generating.value = true
  generateMsg.value = ''
  try {
    const res = await api.adminGenerateDaily(route.params.date)
    generateMsg.value = `已生成：${res.highlight_count} 条要点 · ${res.item_count} 条资讯`
    await refresh()
  } catch (e) {
    generateMsg.value = e.message
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.daily-highlights { padding: 26px 30px; border-top: 3px solid #234e22; }
.daily-highlights-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
.daily-highlights-heading > div { display: flex; gap: 8px; align-items: center; color: #234e22; }
.daily-highlights-heading svg { width: 18px; height: 18px; }
.daily-highlights-heading h2 { font-size: 18px; font-weight: 650; }
.daily-highlights-heading > span { font-size: 11px; color: #637168; }
.daily-highlights ul { margin-top: 6px; }
.daily-highlights li { position: relative; padding: 18px 0 18px 20px; color: #435046; font-size: 14px; line-height: 1.95; }
.daily-highlights li + li { border-top: 1px solid #e1e8e0; }
.daily-highlights li::before { content: ''; position: absolute; left: 0; top: 28px; width: 5px; height: 5px; border: 1px solid #82a678; border-radius: 1px; }
.daily-highlights li:last-child { padding-bottom: 3px; }
.daily-mobile-contents { display: none; }
.daily-outline > section { padding: 24px 22px 16px; }
.daily-outline h2 { margin-top: 10px; font-size: 19px; font-weight: 650; }
.daily-outline-count { color: #637168; font-size: 11px; margin-top: 10px; }
.daily-outline nav { display: grid; margin-top: 20px; padding-block: 7px; border-block: 1px solid #e1e8e0; }
.daily-outline nav a { display: flex; justify-content: space-between; gap: 12px; padding-block: 12px; color: #234e22; font-size: 12px; }
.daily-outline nav a:hover { text-decoration: underline; text-underline-offset: 4px; }
.daily-outline nav a > span:last-child { color: #637168; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px; }
.daily-outline .site-text-link { margin-top: 12px; font-size: 11px; }
.share-backdrop { position: fixed; inset: 0; z-index: 40; display: grid; place-items: center; padding: 20px; background: #14211bc2; backdrop-filter: blur(4px); }
.share-dialog { display: flex; flex-direction: column; width: 100%; max-width: 460px; max-height: calc(100dvh - 40px); overflow: hidden; border: 1px solid #e1e8e0; border-radius: 18px; background: white; box-shadow: 0 24px 80px #14211b33; }
.share-heading { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 22px; border-bottom: 1px solid #e1e8e0; }
.share-heading h2 { font-size: 17px; font-weight: 650; }
.share-heading button { display: grid; place-items: center; width: 44px; height: 44px; color: #637168; border-radius: 8px; }
.share-heading button:hover { background: #f4f8f2; }
.share-heading svg { width: 20px; height: 20px; }
.share-body { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 20px; background: #f4f8f2; }
.share-preview { display: block; width: 100%; border: 1px solid #dce6d8; border-radius: 10px; }
.share-actions { flex-shrink: 0; padding: 16px 22px; border-top: 1px solid #e1e8e0; }
.share-download { width: 100%; min-height: 44px; }
.share-hint { margin-top: 10px; color: #637168; font-size: 11px; text-align: center; line-height: 1.9; }
.share-render { position: fixed; left: -9999px; top: 0; width: 750px; pointer-events: none; }
@media (max-width: 767px) { .daily-highlights { padding: 22px 20px; } .daily-highlights li { font-size: 13px; } .daily-outline { display: none; } .daily-mobile-contents { display: flex; } }
</style>
