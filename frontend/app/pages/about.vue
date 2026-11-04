<template>
  <div class="site-reading-page about-page">
    <PageHeading eyebrow="关于 AGRIHOT" title="关于 AgriHot：农业科技情报平台" description="让有价值的农业信息，更早被看见。" />

    <section class="about-intro site-surface" aria-labelledby="about-intro-title">
      <div class="about-intro-mark"><BrandMark class="w-12 h-12" /><span>AgriHot<span class="text-leaf-500">.</span></span></div>
      <div class="about-intro-copy">
        <h2 id="about-intro-title">AgriHot 是什么？</h2>
        <p>{{ platformDescription }}</p>
        <p>面向农业科研人员、学生与产业从业者，AgriHot 帮助读者跟踪智慧农业、农业信息化、数字乡村等主题的进展，为课题调研、技术选型和日常信息跟踪提供有出处的参考。</p>
        <NuxtLink to="/feed" class="site-text-link">开始查找农业资讯<ArticleIcon name="external" /></NuxtLink>
      </div>
    </section>

    <section aria-labelledby="about-content-title">
      <h2 id="about-content-title" class="about-section-title">在 AgriHot 可以查到什么？</h2>
      <div class="about-features">
        <section v-for="feature in features" :key="feature.title" class="site-surface">
          <ArticleIcon :name="feature.icon" />
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.description }}</p>
          <NuxtLink :to="feature.to" class="site-text-link">{{ feature.action }}<ArticleIcon name="external" /></NuxtLink>
        </section>
      </div>
    </section>

    <section class="about-data site-surface" aria-labelledby="about-data-title">
      <div class="about-section-heading"><h2 id="about-data-title">正在汇聚的信息</h2><span v-if="sinceLabel">自 {{ sinceLabel }} 起</span></div>
      <div class="about-stat-grid">
        <component v-for="card in cards" :key="card.label" :is="card.to ? NuxtLink : 'div'" :to="card.to" :aria-label="card.to ? `查看${card.aria}` : undefined" class="about-stat">
          <strong>{{ fmtNum(card.value) }}</strong><span>{{ card.label }}<ArticleIcon v-if="card.to" name="external" /></span>
        </component>
      </div>
    </section>

    <section class="about-method site-surface" aria-labelledby="about-method-title">
      <h2 id="about-method-title">内容来源与整理方式</h2>
      <dl class="about-method-list">
        <div><dt>政策与报道</dt><dd>整理自公开发布的农业农村政策、新闻报道与行业信息。详情页保留来源名称与原文链接，方便回到发布机构或媒体核对。</dd></div>
        <div><dt>学术论文</dt><dd>论文元数据来自 <a href="https://openalex.org/" target="_blank" rel="noopener">OpenAlex</a> 等开放接口，汇集作者、期刊、DOI 等信息。中文摘要与论文卡片帮助读者初步了解研究内容，完整结论请查阅正式出版物。</dd></div>
        <div><dt>自动整理与 AI 辅助</dt><dd>收录内容自动去重，多信源报道合并呈现。摘要与翻译由 AI 生成，可能存在遗漏或偏差；站内整理内容供阅读参考，引用与决策请以官方原文和正式出版物为准。</dd></div>
      </dl>
    </section>

    <section class="about-faq site-surface" aria-labelledby="about-faq-title">
      <h2 id="about-faq-title">常见问题</h2>
      <div v-for="faq in faqs" :key="faq.question" class="about-faq-item">
        <h3>{{ faq.question }}</h3>
        <p>{{ faq.answer }}</p>
        <NuxtLink :to="faq.to" class="site-text-link">{{ faq.action }}<ArticleIcon name="external" /></NuxtLink>
      </div>
    </section>

    <section class="about-contact site-surface" aria-labelledby="about-contact-title">
      <div class="about-contact-copy">
        <p class="page-eyebrow">纠错 · 合作 · 建议</p>
        <h2 id="about-contact-title">联系 AgriHot</h2>
        <p>发现摘要错误、来源链接失效，或希望更正、下线内容，请附上站内页面链接与问题说明，通过邮件或微信联系。也欢迎交流内容合作与使用建议。</p>
        <dl>
          <div><dt>邮箱</dt><dd><a href="mailto:ijedyu@gmail.com">ijedyu@gmail.com<ArticleIcon name="external" /></a></dd></div>
          <div><dt>微信</dt><dd>扫码添加 ZUOAJ，备注来意即可。</dd></div>
        </dl>
      </div>
      <figure><a :href="wechatQr" target="_blank" rel="noopener" aria-label="查看微信二维码大图"><img :src="wechatQr" alt="AgriHot 联系微信二维码，扫码添加 ZUOAJ" width="958" height="1415" loading="lazy" /></a></figure>
    </section>
    <p class="site-disclaimer">原文与论文的相关权利归各自权利人所有。如涉及来源方权益问题，请邮件联系 <a href="mailto:ijedyu@gmail.com">ijedyu@gmail.com</a> 更正或下线。</p>
  </div>
</template>

<script setup>
import wechatQr from '~/assets/wechat-qr.png'
import { NuxtLink } from '#components'

const pageTitle = '关于 AgriHot｜农业科技情报、政策与论文聚合'
const pageDescription = 'AgriHot 是面向农业科研与产业从业者的农业科技情报平台，汇集农业农村政策、行业报道与学术论文，整理《农业农村日报》，支持 Agent Skill 与 MCP 检索。了解内容来源、AI 摘要与联系纠错方式。'
const platformDescription = 'AgriHot 是一个农业科技情报平台，汇集农业农村政策、行业报道与农业科技学术论文，按日整理《农业农村日报》，并支持通过 Agent Skill 与 MCP 检索资讯、论文和日报。'
const features = [
  { title: '农业政策与行业动态', description: '跟踪农业农村政策、地方实践与行业报道，通过分类和关键词查找资料，沿原文链接继续阅读。', icon: 'document', to: '/feed', action: '浏览农业资讯' },
  { title: '农业科技学术论文', description: '按研究方向浏览已收录论文，通过中文摘要与论文卡片了解研究要点，再查阅论文原文。', icon: 'leaf', to: '/feed?category=论文', action: '查找农业论文' },
  { title: '《农业农村日报》', description: '把政策、报道、论文与行业动态按日汇总，提炼核心要点，也可按日期回顾往期内容。', icon: 'calendar', to: '/dailies', action: '阅读农业农村日报' },
  { title: 'Agent Skill 与 MCP', description: '将 AgriHot 接入 AI 助手，按关键词和语义检索已收录内容，获取站内阅读页与原文链接。', icon: 'link', to: '/agent', action: '了解 Agent 接入' },
]
const faqs = [
  { question: '如何查找某个农业主题的资料？', answer: '在“全部动态”中输入标题、摘要中的词语或关键词，可按政策、报道、论文、行业分类筛选。也可以通过主题目录与标签继续浏览相关内容。', to: '/topic', action: '浏览农业主题' },
  { question: '《农业农村日报》是什么？', answer: '《农业农村日报》是 AgriHot 按日整理的农业信息汇总，包含核心要点和当期收录资讯。日报归档页提供最新一期与往期内容，适合快速回顾每天的农业进展。', to: '/dailies', action: '查看日报归档' },
  { question: '如何在 AI 助手中使用 AgriHot？', answer: '先在 Agent 接入页面申请读取 Key，经管理员审核后，安装 AgriHot Skill 或配置支持认证头的远程 MCP 客户端，即可检索资讯、获取单篇详情和阅读日报。', to: '/agent', action: '查看接入说明与申请' },
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
  title: pageTitle,
  description: pageDescription,
  path: '/about',
  keywords: ['AgriHot', '农业科技情报', '农业政策', '农业论文', '农业农村日报', '智慧农业', '农业信息化'],
  jsonLd: (origin) => {
    const root = absUrl('/', origin)
    const url = absUrl('/about', origin)
    const graph = websiteJsonLd(origin)['@graph']
    return {
      '@context': 'https://schema.org',
      '@graph': [
        { ...graph[0], description: platformDescription, email: 'ijedyu@gmail.com' },
        graph[1],
        {
          '@type': 'AboutPage',
          '@id': `${url}#webpage`,
          url,
          name: pageTitle,
          description: pageDescription,
          inLanguage: 'zh-CN',
          isPartOf: { '@id': `${root}#website` },
          mainEntity: { '@id': `${root}#org` },
        },
      ],
    }
  },
})
</script>

<style scoped>
.about-page { display: grid; gap: 24px; }
.about-page .page-heading { margin-bottom: 6px; }
.about-intro { padding: 32px; display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 34px; align-items: start; }
.about-intro-mark { display: flex; flex-direction: column; gap: 12px; }
.about-intro-mark > span { font-size: 24px; font-weight: 650; letter-spacing: -.04em; color: #234e22; }
.about-intro-copy h2, .about-section-title, .about-method h2, .about-faq h2 { font-size: 19px; font-weight: 650; line-height: 1.6; }
.about-intro-copy p { margin-top: 12px; font-size: 14px; color: #637168; line-height: 2.1; }
.about-intro-copy .site-text-link { margin-top: 12px; }
.about-method a, .about-page .site-disclaimer a { color: #234e22; text-decoration: underline; text-underline-offset: 4px; }
.about-section-title { margin-bottom: 16px; }
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
.about-features { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.about-features > section { padding: 25px; }
.about-features > section > svg { width: 24px; height: 24px; color: #234e22; }
.about-features h3 { font-size: 17px; font-weight: 600; margin-top: 18px; }
.about-features p { margin-top: 10px; font-size: 13px; line-height: 1.9; color: #637168; }
.about-features .site-text-link { margin-top: 16px; }
.about-method, .about-faq { padding: 28px 32px; }
.about-method-list { margin-top: 22px; display: grid; gap: 20px; }
.about-method-list > div { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 24px; }
.about-method-list dt { font-size: 13px; line-height: 1.9; font-weight: 600; color: #435046; }
.about-method-list dd, .about-faq-item p { color: #637168; font-size: 13px; line-height: 2; overflow-wrap: anywhere; }
.about-faq-item { margin-top: 20px; padding-top: 20px; border-top: 1px solid #e1e8e0; }
.about-faq-item h3 { font-size: 15px; font-weight: 600; line-height: 1.8; }
.about-faq-item p { margin-top: 8px; }
.about-faq-item .site-text-link { margin-top: 6px; }
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
@media (max-width: 767px) { .about-method, .about-faq { padding: 24px; } .about-method-list > div { grid-template-columns: minmax(0, 1fr); gap: 6px; } }
</style>
