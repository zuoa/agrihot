<template>
  <div>
    <PageHeading eyebrow="AGRIHOT · 关键词索引" title="从一个关键词，找到更多线索" description="按作物、技术、地区或机构，探索彼此关联的农业资讯与研究。"><NuxtLink to="/topic" class="site-text-link">按主题浏览<ArticleIcon name="external" /></NuxtLink></PageHeading>
    <section class="tag-directory site-surface">
      <div class="tag-directory-toolbar"><label class="site-search"><ArticleIcon name="search" /><span class="sr-only">查找标签</span><input v-model="query" type="search" placeholder="输入关键词查找标签…" /></label><span v-if="!pending && !error" aria-live="polite">{{ tags.length }} 个标签</span></div>
      <PageSkeleton v-if="pending" variant="tags" label="正在加载标签…" />
      <div v-else-if="error" class="site-empty" role="alert"><h2>标签暂时加载失败</h2><p>请稍后重试。</p><button type="button" class="site-button site-button-secondary" @click="refresh()">重新加载</button></div>
      <div v-else-if="!tags.length" class="site-empty"><h2>{{ query ? '没有找到相关标签' : '暂无标签' }}</h2><p>{{ query ? '换一个关键词，或从主题目录开始。' : '可以先浏览最新动态。' }}</p><button v-if="query" type="button" class="site-button site-button-secondary" @click="query = ''">查看全部标签</button><NuxtLink v-else to="/feed" class="site-button site-button-secondary">查看全部动态</NuxtLink></div>
      <div v-else class="tag-directory-links"><NuxtLink v-for="tag in tags" :key="tag.name" :to="`/tags/${encodeURIComponent(tag.name)}`"><span class="tag-hash" aria-hidden="true">#</span><span>{{ tag.name }}</span><span class="tag-count">{{ tag.count }}</span></NuxtLink></div>
    </section>
  </div>
</template>

<script setup>
const api = useApi()
const query = ref('')
const { data, pending, error, refresh } = await useAsyncData('tags', () => api.tags())
const tags = computed(() => {
  const term = query.value.trim().toLowerCase()
  return (data.value || []).filter(tag => !term || tag.name.toLowerCase().includes(term))
})

usePageSeo({
  title: '全部标签 · AgriHot',
  description: '按主题浏览农业信息化资讯：智慧农业、数字乡村、遥感、政策等。',
  path: '/tags',
  keywords: uniqueKeywords(['主题', DEFAULT_KEYWORDS]),
})
</script>

<style scoped>
.tag-directory { padding: 28px; }
.tag-directory-toolbar { display: flex; align-items: center; flex-wrap: wrap; justify-content: space-between; gap: 16px; border-bottom: 1px solid #e1e8e0; padding-bottom: 24px; margin-bottom: 24px; }
.tag-directory-toolbar .site-search { width: 100%; max-width: 440px; background: #f8faf7; padding-right: 15px; }
.tag-directory-toolbar > span { color: #637168; font-size: 11px; }
.tag-directory-links { display: flex; flex-wrap: wrap; gap: 10px; }
.tag-directory-links a { display: inline-flex; align-items: center; gap: 7px; max-width: 100%; min-height: 40px; border: 1px solid #e1e8e0; border-radius: 7px; padding: 9px 12px; color: #435046; font-size: 12px; overflow-wrap: anywhere; }
.tag-directory-links a:hover { color: #234e22; background: #f4f8f2; border-color: #aec5a8; }
.tag-hash { color: #9bab94; }
.tag-count { font-family: 'SFMono-Regular', Consolas, monospace; color: #637168; margin-left: 4px; font-size: 10px; }
@media (max-width: 767px) { .tag-directory { padding: 20px; } .tag-directory-links { gap: 8px; } .tag-directory-links a { min-height: 44px; padding-inline: 10px; } }
</style>
