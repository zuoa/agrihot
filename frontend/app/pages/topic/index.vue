<template>
  <div>
    <PageHeading eyebrow="AGRIHOT · 主题索引" title="从领域出发，发现农业新进展" description="沿着产业、技术与乡村发展的脉络，浏览政策、动态和研究。"><NuxtLink to="/tags" class="site-text-link">查找全部标签<ArticleIcon name="external" /></NuxtLink></PageHeading>
    <div class="topic-directory-toolbar"><label class="site-search"><ArticleIcon name="search" /><span class="sr-only">查找主题</span><input v-model="query" type="search" placeholder="查找主题，如水稻、遥感、种业…" /></label><p v-if="!pending && !error" aria-live="polite">{{ query ? `找到 ${topics.length} 个领域` : `${topics.length} 个领域，从这里开始` }}</p></div>
    <PageSkeleton v-if="pending" variant="grid" label="正在加载主题…" />
    <div v-else-if="error" class="site-empty" role="alert"><h2>主题暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
    <div v-else-if="!topics.length" class="site-empty"><h2>{{ query ? '没有找到这个主题' : '主题目录正在准备中' }}</h2><p>{{ query ? '换一个关键词，或查看全部农业领域。' : '可以先从最新动态开始阅读。' }}</p><button v-if="query" type="button" class="site-button site-button-secondary" @click="query = ''">查看全部主题</button><NuxtLink v-else to="/feed" class="site-button site-button-secondary">查看全部动态</NuxtLink></div>
    <div v-else class="topic-directory-grid">
      <section v-for="topic in topics" :key="topic.code" class="topic-branch site-surface">
        <NuxtLink :to="topic.path" class="topic-branch-heading"><span class="topic-branch-mark"><ArticleIcon :name="topicIcon(topic.slug)" /></span><div><h2>{{ topic.name }}</h2><p>{{ shortDescription(topic) }}</p></div><ArticleIcon name="external" /></NuxtLink>
        <div class="topic-branch-children"><NuxtLink v-for="child in featured(topic)" :key="child.code" :to="child.path"><span>{{ child.name }}</span><span>{{ child.count }}</span></NuxtLink></div>
        <div class="topic-branch-footer"><span>{{ topic.count.toLocaleString('zh-CN') }} 篇内容</span><NuxtLink :to="topic.path">{{ topic.children.length }} 个方向<ArticleIcon name="chevron" /></NuxtLink></div>
      </section>
    </div>
  </div>
</template>

<script setup>
const api = useApi()
const query = ref('')
const { data, pending, error, refresh } = await useAsyncData('taxonomy', () => api.taxonomy())
const topics = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (data.value?.topics || []).filter(t => !q || [t.name, t.description, ...t.children.map(c => c.name)].some(s => s.toLowerCase().includes(q)))
})
function topicIcon(slug) {
  return { 'digital-agriculture': 'grid', policy: 'document', 'rural-services': 'link', environment: 'insight' }[slug] || 'leaf'
}
function featured(topic) {
  const children = [...topic.children].sort((a, b) => b.count - a.count)
  const q = query.value.trim().toLowerCase()
  return (q && children.some(c => c.name.toLowerCase().includes(q)) ? children.filter(c => c.name.toLowerCase().includes(q)) : children).slice(0, 3)
}
function shortDescription(topic) {
  return [...topic.children].sort((a, b) => b.count - a.count).slice(0, 3).map(c => c.name).join(' · ')
}
usePageSeo({ title: '主题索引 · AgriHot', description: '按农业产业、数字技术、资源环境与乡村发展浏览政策、动态和研究。', path: '/topic' })
</script>


<style scoped>
.topic-directory-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 26px; }
.topic-directory-toolbar .site-search { width: 100%; max-width: 520px; padding-right: 16px; }
.topic-directory-toolbar > p { font-size: 11px; color: #637168; }
.topic-directory-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.topic-branch { min-width: 0; padding: 25px 23px 14px; }
.topic-branch-heading { display: flex; align-items: flex-start; gap: 12px; }
.topic-branch-mark { display: grid; place-items: center; width: 36px; height: 38px; border-radius: 8px; background: #f4f8f2; color: #234e22; flex-shrink: 0; }
.topic-branch-mark svg { width: 21px; height: 21px; }
.topic-branch-heading > div { flex: 1; min-width: 0; }
.topic-branch h2 { font-size: 17px; line-height: 1.65; font-weight: 650; letter-spacing: -.02em; }
.topic-branch-heading p { margin-top: 6px; font-size: 10px; color: #637168; line-height: 1.8; }
.topic-branch-heading > svg { width: 16px; height: 16px; color: #637168; margin-top: 5px; }
.topic-branch-heading:hover h2 { color: #327a2d; }
.topic-branch-children { display: grid; margin-top: 20px; padding-top: 10px; border-top: 1px solid #e1e8e0; }
.topic-branch-children a { display: flex; justify-content: space-between; align-items: center; gap: 15px; padding-block: 10px; font-size: 12px; color: #435046; }
.topic-branch-children a > span:last-child { color: #637168; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 10px; }
.topic-branch-children a:hover { color: #234e22; text-decoration: underline; text-underline-offset: 4px; }
.topic-branch-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; padding-top: 12px; margin-top: 8px; border-top: 1px solid #e1e8e0; font-size: 10px; color: #637168; }
.topic-branch-footer a { display: inline-flex; align-items: center; gap: 4px; color: #234e22; min-height: 30px; }
.topic-branch-footer svg { width: 12px; height: 12px; }
@media (max-width: 1023px) { .topic-directory-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 639px) { .topic-directory-grid { grid-template-columns: minmax(0, 1fr); gap: 14px; } .topic-branch { padding: 22px 20px 13px; } .topic-branch-children a, .topic-branch-footer a { min-height: 42px; } .topic-directory-toolbar { gap: 12px; } }
</style>
