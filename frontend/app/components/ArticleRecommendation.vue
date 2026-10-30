<template>
  <NuxtLink :to="`/items/${item.id}`" class="article-recommendation" :class="{ 'is-compact': compact }">
    <div class="recommendation-meta">
      <span>{{ item.category || '资讯' }}</span>
      <time :datetime="item.published_at || item.created_at">{{ dateLabel }}</time>
    </div>
    <h3>{{ item.title }}</h3>
    <p v-if="!compact && summary" class="recommendation-summary">{{ summary }}</p>
    <div class="recommendation-footer"><span>{{ item.source_name || '未知来源' }}</span><ArticleIcon name="chevron" /></div>
  </NuxtLink>
</template>

<script setup>
const props = defineProps({
  item: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})

const dateLabel = computed(() => fmtDay(props.item.published_at || props.item.created_at))
const summary = computed(() => props.item.paper?.card?.tldr || props.item.summary_zh || props.item.summary)
</script>

<style scoped>
.article-recommendation { display: flex; flex-direction: column; min-width: 0; padding: 21px 22px 17px; border: 1px solid var(--article-line, #e1e8e0); border-radius: 12px; background: #fff; transition: border-color .15s, background .15s; }
.article-recommendation:hover { border-color: #aec5a8; background: #fbfdf9; }
.article-recommendation:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; }
.recommendation-meta { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 5px 12px; color: #637168; font-size: 11px; line-height: 1.7; }
.recommendation-meta > span { color: #234e22; font-weight: 500; }
.recommendation-meta time { font-size: 10px; font-variant-numeric: tabular-nums; }
.article-recommendation h3 { margin-top: 10px; color: #20332a; font-size: 16px; font-weight: 600; line-height: 1.75; overflow-wrap: anywhere; }
.article-recommendation:hover h3 { color: #327a2d; }
.recommendation-summary { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; margin-top: 8px; color: #637168; font-size: 12px; line-height: 1.9; overflow-wrap: anywhere; }
.recommendation-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: auto; padding-top: 16px; color: #637168; font-size: 11px; line-height: 1.7; }
.recommendation-footer > span { min-width: 0; overflow-wrap: anywhere; }
.recommendation-footer svg { width: 14px; height: 14px; flex-shrink: 0; color: #234e22; }
.is-compact { padding: 17px 0; border: 0; border-radius: 0; background: transparent; }
.is-compact:hover { background: transparent; }
.is-compact h3 { margin-top: 7px; font-size: 14px; line-height: 1.8; }
.is-compact .recommendation-footer { padding-top: 8px; font-size: 10px; }
@media (max-width: 767px) {
  .article-recommendation { padding: 18px 19px 15px; }
  .is-compact { padding: 17px 0; }
  .is-compact h3 { font-size: 15px; }
}
@media (prefers-reduced-motion: reduce) {
  .article-recommendation { transition: none; }
}
</style>
