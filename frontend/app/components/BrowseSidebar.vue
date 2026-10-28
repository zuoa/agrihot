<template>
  <aside class="browse-sidebar" aria-label="发现更多">
    <section class="site-surface browse-panel">
      <p class="page-eyebrow">换个角度，继续阅读</p>
      <h2>发现更多</h2>
      <nav>
        <NuxtLink v-for="link in links" :key="link.to" :to="link.to">
          <span class="browse-icon"><ArticleIcon :name="link.icon" /></span>
          <span class="browse-link-copy"><strong>{{ link.label }}</strong><span>{{ link.description }}</span></span>
          <ArticleIcon name="external" class="browse-arrow" />
        </NuxtLink>
      </nav>
    </section>
    <section class="browse-note">
      <BrandMark class="w-6 h-6" />
      <p>追踪农业政策、前沿研究与技术进展，让有价值的信息更早被看见。</p>
      <NuxtLink to="/about">了解 AgriHot<ArticleIcon name="external" /></NuxtLink>
    </section>
  </aside>
</template>

<script setup>
const links = [
  { to: '/topic', label: '主题索引', description: '沿着产业与技术查找进展', icon: 'grid' },
  { to: '/dailies', label: '农业日报', description: '按日回顾政策、动态与研究', icon: 'calendar' },
  { to: '/agent', label: 'Agent 接入', description: '在你的工具中检索与引用', icon: 'link' },
]
</script>
