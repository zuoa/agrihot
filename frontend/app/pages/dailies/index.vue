<template>
  <div>
    <PageHeading eyebrow="AGRIHOT · 日报归档" title="每天一份，读懂农业新动态" description="汇集政策、报道、学术论文与行业动态，按日回顾值得关注的信息。">
      <button v-if="showAdmin" type="button" class="site-button site-button-secondary" :disabled="generating" @click="generateToday">{{ generating ? '生成中…' : '生成今日日报' }}</button>
    </PageHeading>
    <p v-if="generateMsg" role="status" class="mb-5 text-xs text-stone-500">{{ generateMsg }}</p>
    <PageSkeleton v-if="pending" variant="grid" label="正在加载日报…" />
    <div v-else-if="error" class="site-empty" role="alert"><h2>日报暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
    <div v-else-if="!dailies.length" class="site-empty"><h2>第一期日报正在准备中</h2><p>可以先浏览最新收录的政策、报道与研究。</p><NuxtLink to="/feed" class="site-button site-button-secondary">查看全部动态</NuxtLink></div>
    <template v-else>
      <NuxtLink :to="`/dailies/${dailies[0].date}`" class="latest-edition site-surface">
        <div class="edition-date"><span>{{ monthLabel(dailies[0].date) }}</span><strong>{{ dayNum(dailies[0].date) }}</strong><span>{{ dailies[0].date.slice(0, 4) }}</span></div>
        <div class="latest-edition-copy"><p class="page-eyebrow">最新一期</p><h2>{{ dailies[0].title }}</h2><p class="edition-counts">{{ dailies[0].highlight_count }} 条核心要点<span>·</span>{{ dailies[0].item_count }} 条资讯</p><span class="site-text-link">阅读本期日报<ArticleIcon name="external" /></span></div>
        <ArticleIcon name="document" class="edition-watermark" />
      </NuxtLink>
      <section v-if="dailies.length > 1" class="site-section">
        <div class="site-section-heading"><h2>往期日报</h2><span>按日期回顾</span></div>
        <div class="edition-grid">
          <NuxtLink v-for="d in dailies.slice(1)" :key="d.date" :to="`/dailies/${d.date}`" class="edition-card site-surface"><time :datetime="d.date" class="edition-small-date"><strong>{{ dayNum(d.date) }}</strong><span>{{ d.date.slice(0, 4) }} / {{ monthLabel(d.date) }}</span></time><div><h2>{{ d.title }}</h2><p>{{ d.highlight_count }} 条要点<span>·</span>{{ d.item_count }} 条资讯</p></div><ArticleIcon name="external" /></NuxtLink>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
const api = useApi()
const showAdmin = useClientAdmin()
const generating = ref(false)
const generateMsg = ref('')

const { data, pending, error, refresh } = await useAsyncData(
  'dailies',
  () => api.dailies({ page_size: 60 }),
)

const dailies = computed(() => data.value?.dailies || [])

function dayNum(iso) {
  return Number(shanghaiDateKey(iso).slice(8, 10))
}
function monthLabel(iso) {
  return `${Number(shanghaiDateKey(iso).slice(5, 7))}月`
}

async function generateToday() {
  const today = fmtDateKey(new Date())
  generating.value = true
  generateMsg.value = ''
  try {
    const res = await api.adminGenerateDaily(today)
    generateMsg.value = `已生成：${res.highlight_count} 条要点 · ${res.item_count} 条资讯`
    await refresh()
  } catch (e) {
    generateMsg.value = e.message
  } finally {
    generating.value = false
  }
}

usePageSeo({
  title: '农业日报 · AgriHot',
  description: '每日《农业农村日报》：农业信息化政策、报道、论文与行业动态精选。',
  path: '/dailies',
  keywords: uniqueKeywords(['农业农村日报', DEFAULT_KEYWORDS]),
})
</script>

<style scoped>
.latest-edition { position: relative; display: flex; align-items: center; gap: 34px; overflow: hidden; padding: 34px 38px; }
.latest-edition:hover { border-color: #aec5a8; }
.edition-date { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 106px; padding: 17px 20px; border-radius: 10px; background: #f4f8f2; color: #234e22; }
.edition-date > span { font-size: 11px; }
.edition-date > strong { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 52px; line-height: 1; letter-spacing: -.08em; font-weight: 500; }
.latest-edition-copy { position: relative; z-index: 1; min-width: 0; }
.latest-edition-copy h2 { margin-top: 12px; font-size: 26px; font-weight: 700; line-height: 1.6; letter-spacing: -.025em; }
.latest-edition:hover h2 { color: #327a2d; }
.edition-counts { margin-top: 12px; color: #637168; font-size: 12px; }
.edition-counts > span, .edition-card p > span { margin-inline: 10px; }
.latest-edition-copy .site-text-link { margin-top: 14px; }
.edition-watermark { position: absolute; width: 128px; height: 128px; right: 50px; color: #edf3e9; transform: rotate(10deg); }
.edition-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.edition-card { display: flex; gap: 20px; align-items: center; padding: 24px; min-width: 0; }
.edition-card:hover { border-color: #aec5a8; }
.edition-small-date { display: flex; flex-direction: column; align-items: center; gap: 7px; min-width: 65px; color: #234e22; }
.edition-small-date strong { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 31px; font-weight: 500; line-height: 1; letter-spacing: -.06em; }
.edition-small-date span { color: #637168; font-size: 10px; }
.edition-card > div { flex: 1; min-width: 0; border-left: 1px solid #e1e8e0; padding-left: 20px; }
.edition-card h2 { font-size: 15px; font-weight: 600; line-height: 1.8; overflow-wrap: anywhere; }
.edition-card p { margin-top: 8px; font-size: 11px; color: #637168; }
.edition-card > svg { width: 18px; height: 18px; color: #637168; }
@media (max-width: 767px) { .latest-edition { gap: 20px; padding: 24px 20px; } .edition-date { min-width: 78px; padding: 16px 12px; } .edition-date > strong { font-size: 42px; } .latest-edition-copy h2 { font-size: 20px; } .edition-watermark { display: none; } .edition-grid { grid-template-columns: minmax(0, 1fr); } .edition-card { gap: 15px; padding: 20px 17px; } .edition-card > div { padding-left: 15px; } }
@media (max-width: 379px) { .latest-edition { gap: 14px; padding-inline: 16px; } .edition-date { min-width: 62px; } .edition-counts { font-size: 11px; line-height: 1.9; } .edition-counts > span { margin-inline: 5px; } }
</style>
