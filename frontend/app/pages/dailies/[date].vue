<template>
  <div v-if="pending" class="text-center text-stone-400 py-16">加载中…</div>
  <div v-else-if="daily">
    <header class="mb-6">
      <div class="text-sm text-leaf-600 font-medium mb-1">{{ dateLabel }}</div>
      <div class="flex items-start justify-between gap-3">
        <h1 class="text-2xl font-bold text-stone-900">{{ daily.title }}</h1>
        <ClientOnly>
          <button @click="openShare"
            class="shrink-0 px-3 py-1.5 rounded-lg bg-leaf-600 text-white text-sm hover:bg-leaf-700 transition-colors">
            分享
          </button>
        </ClientOnly>
      </div>
      <p class="text-sm text-stone-400 mt-2">{{ (daily.content || '').replace(/[*-]/g, '').slice(0, 120) }}</p>
      <div v-if="showAdmin" class="mt-3">
        <button @click="regenerate" :disabled="generating"
          class="text-xs px-2.5 py-1 rounded-md border border-dashed border-leaf-300 text-leaf-600 hover:bg-leaf-50 disabled:opacity-50">
          {{ generating ? '生成中…' : '重新生成本日日报' }}
        </button>
        <span v-if="generateMsg" class="ml-2 text-xs text-stone-400">{{ generateMsg }}</span>
      </div>
    </header>

    <section class="rounded-2xl bg-gradient-to-br from-leaf-50 to-white border border-leaf-200 p-5 sm:p-6 mb-8">
      <h2 class="font-bold text-leaf-800 mb-4 flex items-center gap-2">
        <span class="w-6 h-6 rounded-md bg-leaf-600 text-white grid place-items-center text-xs">要</span>今日要点
      </h2>
      <ol class="space-y-3">
        <li v-for="(h, i) in daily.highlights" :key="i" class="flex gap-3 text-sm leading-6">
          <span class="w-5 h-5 rounded-full bg-leaf-100 text-leaf-700 text-xs font-bold grid place-items-center shrink-0 mt-0.5">{{ i + 1 }}</span>
          <span class="text-stone-700">{{ h }}</span>
        </li>
      </ol>
    </section>

    <section v-for="sec in sections" :key="sec.name" class="mb-8">
      <div class="flex items-baseline gap-3 mb-3">
        <h2 class="text-lg font-bold text-leaf-800">{{ sec.name }}</h2>
        <span class="text-xs text-stone-400">{{ sec.items.length }} 条</span>
        <div class="flex-1 border-t border-leaf-100"></div>
      </div>
      <div class="space-y-3">
        <ItemCard v-for="it in sec.items" :key="it.id" :item="it" @updated="refresh" @deleted="refresh" />
      </div>
    </section>

    <p class="text-xs text-stone-400 border-t border-leaf-100 pt-4 leading-5">
      本日报内容整理自公开来源，学术论文元数据来自 OpenAlex 等开放接口；外文资料已译为中文，翻译与摘要仅供参考；引用与决策请以官方原文与正式出版物为准。
    </p>

    <ClientOnly>
      <div v-if="sharing" class="fixed inset-0 z-40 bg-black/50 grid place-items-center p-4" @click.self="sharing = false">
        <div class="bg-white rounded-2xl p-5 w-full max-w-sm">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-bold text-stone-900">分享本期日报</h3>
            <button @click="sharing = false" class="text-stone-400 hover:text-stone-600 text-lg leading-none">✕</button>
          </div>
          <div v-if="!shareImg" class="text-center text-stone-400 py-16 text-sm">图片生成中…</div>
          <img v-else :src="shareImg" alt="日报分享图" class="w-full rounded-xl border border-leaf-100" />
          <a v-if="shareImg" :href="shareImg" :download="`agrihot-daily-${daily.date}.png`"
            class="mt-4 block text-center px-4 py-2.5 rounded-xl bg-leaf-600 text-white font-medium hover:bg-leaf-700 transition-colors">
            保存图片
          </a>
          <p class="mt-3 text-xs text-stone-400 text-center">手机端可长按图片保存，扫码可进入本期日报</p>
        </div>
      </div>
      <div v-if="sharing" style="position: fixed; left: -9999px; top: 0">
        <DailyShareCard v-if="shareQr" ref="shareCard" :daily="daily" :qr="shareQr" />
      </div>
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
const shareCard = ref(null)
const generating = ref(false)
const generateMsg = ref('')

const { data, pending, error, refresh } = await useAsyncData(
  () => `daily-${route.params.date}`,
  () => api.daily(route.params.date),
  { watch: [() => route.params.date] },
)

if (error.value) {
  throw createError({ statusCode: 404, statusMessage: '该日期暂无日报', fatal: true })
}
watch(error, (e) => {
  if (e) showError({ statusCode: 404, statusMessage: '该日期暂无日报' })
})

const daily = computed(() => data.value)
const dateLabel = computed(() => (daily.value ? fmtDay(daily.value.date) : ''))
const sections = computed(() => {
  if (!daily.value) return []
  const defs = [
    { name: '一、政策', cats: ['政策'] },
    { name: '二、报道', cats: ['报道'] },
    { name: '三、学术论文', cats: ['论文'] },
    { name: '四、行业动态', cats: ['行业'] },
  ]
  return defs
    .map((d) => ({ name: d.name, items: (daily.value.items || []).filter((i) => d.cats.includes(i.category)) }))
    .filter((s) => s.items.length)
})

usePageSeo(() => {
  const d = daily.value
  if (!d) {
    return {
      title: '该日期暂无日报 · AgriHot',
      description: DEFAULT_DESC,
      path: `/dailies/${route.params.date}`,
      noindex: true,
    }
  }
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
  sharing.value = false
  shareQr.value = ''
  shareImg.value = ''
}

async function openShare() {
  closeShare()
  sharing.value = true
  const [{ default: QRCode }, { toPng }] = await Promise.all([
    import('qrcode'),
    import('html-to-image'),
  ])
  const url = `${requestURL.origin}/dailies/${daily.value.date}`
  shareQr.value = await QRCode.toDataURL(url, {
    width: 264, margin: 1,
    color: { dark: '#1e401e', light: '#ffffff' },
  })
  await nextTick()
  shareImg.value = await toPng(shareCard.value.$el, { pixelRatio: 2, cacheBust: true })
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
