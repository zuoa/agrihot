<template>
  <NuxtLink :to="`/items/${item.id}`" :title="item.title" class="article-recommendation">
    <div class="recommendation-copy">
      <h3>{{ item.title }}</h3>
      <div class="recommendation-meta">
        <span v-if="sameTopic" class="recommendation-topic">同主题</span>
        <span class="recommendation-source">{{ item.source_name || '未知来源' }}</span>
        <time :datetime="item.published_at || item.created_at">{{ dateLabel }}</time>
      </div>
    </div>
    <ArticleIcon name="chevron" class="recommendation-arrow" />
  </NuxtLink>
</template>

<script setup>
const props = defineProps({
  item: { type: Object, required: true },
  sameTopic: { type: Boolean, default: false },
})

const dateLabel = computed(() => fmtDay(props.item.published_at || props.item.created_at).split(' · ')[0])
</script>

<style scoped>
.article-recommendation { display: flex; align-items: center; gap: 14px; min-width: 0; padding: 20px 0; border-top: 1px solid var(--article-line, #e1e8e0); }
.article-recommendation:hover { background: var(--article-soft, #f4f8f2); }
.article-recommendation:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; }
.recommendation-copy { flex: 1; min-width: 0; }
.article-recommendation h3 { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; color: #20332a; font-size: 16px; font-weight: 600; line-height: 1.7; overflow-wrap: anywhere; }
.article-recommendation:hover h3 { color: #327a2d; }
.recommendation-meta { display: flex; align-items: center; gap: 8px; min-width: 0; margin-top: 10px; color: #637168; font-size: 11px; line-height: 1.7; }
.recommendation-topic { flex-shrink: 0; color: #234e22; font-weight: 500; }
.recommendation-source { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-meta time { flex-shrink: 0; margin-left: auto; font-size: 10px; font-variant-numeric: tabular-nums; }
.recommendation-arrow { width: 14px; height: 14px; flex-shrink: 0; color: #637168; }
@media (max-width: 767px) {
  .article-recommendation { padding-block: 17px; gap: 10px; }
  .article-recommendation h3 { font-size: 15px; }
  .recommendation-meta { margin-top: 8px; }
}
</style>
