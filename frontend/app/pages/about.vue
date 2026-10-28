<template>
  <div class="site-reading-page about-page">
    <PageHeading eyebrow="关于 AGRIHOT" title="让有价值的农业信息，更早被看见" description="追踪农业政策、前沿研究与技术进展，为阅读、研究与日常工作提供有出处的参考。" />
    <section class="about-intro site-surface"><div class="about-intro-mark"><BrandMark class="w-12 h-12" /><span>AgriHot<span class="text-leaf-500">.</span></span></div><p>AgriHot 汇集农业农村政策、行业报道与农业科技学术论文，每日整理《农业农村日报》。内容自动收录与去重，多信源报道合并呈现。通过 <NuxtLink to="/agent">Agent Skill 或 MCP</NuxtLink> 接入，也可以在自己的工具中查找资讯、论文和日报。</p></section>
    <section class="about-data site-surface"><div class="about-section-heading"><h2>正在汇聚的信息</h2><span v-if="sinceLabel">自 {{ sinceLabel }} 起</span></div><div class="about-stat-grid"><component v-for="card in cards" :key="card.label" :is="card.to ? NuxtLink : 'div'" :to="card.to" :aria-label="card.to ? `查看${card.aria}` : undefined" class="about-stat"><strong>{{ fmtNum(card.value) }}</strong><span>{{ card.label }}<ArticleIcon v-if="card.to" name="external" /></span></component></div></section>
    <div class="about-features"><section v-for="feature in features" :key="feature.title" class="site-surface"><ArticleIcon :name="feature.icon" /><h2>{{ feature.title }}</h2><p>{{ feature.description }}</p><NuxtLink :to="feature.to" class="site-text-link">{{ feature.action }}<ArticleIcon name="external" /></NuxtLink></section></div>
    <section class="about-contact site-surface"><div class="about-contact-copy"><p class="page-eyebrow">纠错 · 合作 · 建议</p><h2>保持联系</h2><p>内容纠错、来源下线、合作或使用建议，欢迎通过邮件或微信联系。</p><dl><div><dt>邮箱</dt><dd><a href="mailto:ijedyu@gmail.com">ijedyu@gmail.com<ArticleIcon name="external" /></a></dd></div><div><dt>微信</dt><dd>扫码添加 ZUOAJ，备注来意即可。</dd></div></dl></div><figure><a :href="wechatQr" target="_blank" rel="noopener" aria-label="查看微信二维码大图"><img :src="wechatQr" alt="微信二维码，扫码添加 ZUOAJ" width="958" height="1415" loading="lazy" /></a></figure></section>
    <p class="site-disclaimer">本站内容整理自公开来源，学术论文元数据来自 <a href="https://openalex.org/" target="_blank" rel="noopener">OpenAlex</a> 等开放接口，摘要与翻译由 AI 生成，仅供参考；引用与决策请以官方原文与正式出版物为准。如涉及来源方权益问题，请邮件联系 <a href="mailto:ijedyu@gmail.com">ijedyu@gmail.com</a> 更正或下线。</p>
  </div>
</template>

<script setup>
import wechatQr from '~/assets/wechat-qr.png'
import { NuxtLink } from '#components'

const features = [
  { title: '政策与报道', description: '部委文件、地方实践与行业动态，保留来源，串联进展。', icon: 'document', to: '/feed', action: '浏览全部动态' },
  { title: '前沿研究', description: '订阅核心期刊与研究方向，用中文摘要和论文卡片了解成果。', icon: 'leaf', to: '/feed?category=论文', action: '发现学术论文' },
  { title: '接入你的工具', description: '通过 Skill 与 MCP，让 Agent 按关键词和语义查找资料。', icon: 'link', to: '/agent', action: '了解接入方式' },
]
const api = useApi()
const { data: stats } = await useLazyAsyncData('stats', () => api.stats().catch(() => null))

function cat(name) {
  return stats.value?.by_category?.[name] ?? 0
}

function fmtNum(n) {
  if (n == null || !stats.value) return '—'
  return Number(n).toLocaleString('zh-CN')
}

const sinceLabel = computed(() => {
  if (!stats.value?.since) return ''
  const key = shanghaiDateKey(stats.value.since)
  if (!key) return ''
  const [y, m] = key.split('-')
  return `${y}年${Number(m)}月`
})

const cards = computed(() => {
  const s = stats.value
  return [
    { label: '条资讯', aria: '全部资讯', value: s?.items, to: '/feed' },
    { label: '份政策', aria: '政策', value: cat('政策'), to: { path: '/feed', query: { category: '政策' } } },
    { label: '条报道', aria: '报道', value: cat('报道'), to: { path: '/feed', query: { category: '报道' } } },
    { label: '篇论文', aria: '论文', value: cat('论文'), to: { path: '/feed', query: { category: '论文' } } },
    { label: '条行业', aria: '行业动态', value: cat('行业'), to: { path: '/feed', query: { category: '行业' } } },
    { label: '期日报', aria: '农业日报', value: s?.dailies, to: '/dailies' },
    { label: '家信源', aria: '信源', value: s?.sources, to: null },
    { label: '个标签', aria: '标签', value: s?.tags, to: '/tags' },
  ]
})

usePageSeo({
  title: '关于 · AgriHot',
  description: `关于 AgriHot：${DEFAULT_DESC}`,
  path: '/about',
})
</script>

<style scoped>
.about-page { display: grid; gap: 24px; }
.about-page .page-heading { margin-bottom: 6px; }
.about-intro { padding: 32px; display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 34px; align-items: start; }
.about-intro-mark { display: flex; flex-direction: column; gap: 12px; }
.about-intro-mark > span { font-size: 24px; font-weight: 650; letter-spacing: -.04em; color: #234e22; }
.about-intro > p { font-size: 14px; color: #637168; line-height: 2.1; }
.about-intro > p a, .about-page .site-disclaimer a { color: #234e22; text-decoration: underline; text-underline-offset: 4px; }
.about-data { padding: 28px 32px 12px; }
.about-section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding-bottom: 22px; border-bottom: 1px solid #e1e8e0; }
.about-section-heading h2 { font-size: 17px; font-weight: 650; }
.about-section-heading > span { color: #637168; font-size: 11px; }
.about-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.about-stat { padding: 24px 0; }
.about-stat:nth-child(n+5) { border-top: 1px solid #edf1eb; }
.about-stat > strong { display: block; font-family: 'SFMono-Regular', Consolas, monospace; color: #234e22; font-size: 30px; font-weight: 500; letter-spacing: -.06em; }
.about-stat > span { display: flex; align-items: center; gap: 12px; margin-top: 8px; color: #637168; font-size: 11px; }
.about-stat svg { width: 13px; height: 13px; opacity: 0; }
a.about-stat:hover svg { opacity: 1; }
.about-features { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.about-features > section { padding: 25px; }
.about-features > section > svg { width: 24px; height: 24px; color: #234e22; }
.about-features h2 { font-size: 17px; font-weight: 600; margin-top: 18px; }
.about-features p { margin-top: 10px; font-size: 12px; line-height: 1.9; color: #637168; }
.about-features .site-text-link { font-size: 11px; margin-top: 16px; }
.about-contact { display: grid; grid-template-columns: minmax(0, 1fr) 200px; gap: 40px; align-items: start; padding: 32px; }
.about-contact h2 { font-size: 24px; font-weight: 650; margin-top: 12px; }
.about-contact-copy > p:not(.page-eyebrow) { color: #637168; font-size: 13px; line-height: 1.9; margin-top: 14px; }
.about-contact dl { display: grid; gap: 20px; margin-top: 28px; }
.about-contact dt { font-size: 11px; color: #637168; }
.about-contact dd { font-size: 13px; color: #435046; margin-top: 8px; }
.about-contact dd a { display: inline-flex; gap: 8px; align-items: center; color: #234e22; min-height: 30px; }
.about-contact dd svg { width: 15px; height: 15px; }
.about-contact img { width: 200px; height: auto; border: 1px solid #e1e8e0; border-radius: 10px; }
.about-page .site-disclaimer { margin: 4px 0 0; }
@media (max-width: 767px) { .about-intro { padding: 24px; grid-template-columns: minmax(0, 1fr); gap: 20px; } .about-intro-mark { flex-direction: row; align-items: center; gap: 12px; } .about-data { padding: 24px 22px 8px; } .about-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .about-stat:nth-child(n+3) { border-top: 1px solid #edf1eb; } .about-stat > strong { font-size: 28px; } .about-features { grid-template-columns: minmax(0, 1fr); } .about-features > section { padding: 24px; } .about-contact { grid-template-columns: minmax(0, 1fr); padding: 24px; gap: 24px; } .about-contact figure { justify-self: center; } }
</style>
