<template>
  <div class="public-site min-h-screen flex flex-col">
    <header class="site-header"><div class="max-w-6xl mx-auto px-4 py-4"><NuxtLink to="/" class="inline-flex items-center gap-2.5 font-bold text-leaf-800"><BrandMark class="w-8 h-8" />AgriHot<span class="text-leaf-500">.</span></NuxtLink></div></header>
    <main class="error-main"><div class="error-panel site-surface"><p class="page-eyebrow">{{ error?.statusCode || 500 }} · AGRIHOT</p><h1>{{ heading }}</h1><p class="error-description">{{ error?.message || '这条内容可能已下线，请稍后重试。' }}</p><div class="error-actions"><NuxtLink to="/" class="site-button">返回首页</NuxtLink><NuxtLink to="/feed" class="site-button site-button-secondary">浏览最新动态<ArticleIcon name="external" /></NuxtLink></div></div></main>
  </div>
</template>

<script setup>
const props = defineProps({ error: { type: Object, default: null } })
const heading = computed(() => (props.error?.statusCode === 404 ? '页面不存在' : '出错了'))

usePageSeo(() => ({
  title: `${heading.value} · AgriHot`,
  description: DEFAULT_DESC,
  path: '/',
  noindex: true,
}))
</script>

<style scoped>
.error-main { display: grid; place-items: center; flex: 1; padding: 48px 16px; }
.error-panel { width: 100%; max-width: 620px; padding: 48px; text-align: center; }
.error-panel h1 { margin-top: 18px; font-size: 30px; font-weight: 650; letter-spacing: -.03em; }
.error-description { margin-top: 16px; color: #637168; font-size: 14px; line-height: 1.9; }
.error-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; margin-top: 30px; }
@media (max-width: 767px) { .error-panel { padding: 32px 24px; } .error-panel h1 { font-size: 26px; } }
</style>
