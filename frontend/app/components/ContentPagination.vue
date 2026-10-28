<template>
  <nav v-if="totalPages > 1" aria-label="分页" class="content-pagination">
    <NuxtLink v-if="page > 1" :to="pageLink(page - 1)" class="pagination-button"><ArticleIcon name="back" />上一页</NuxtLink>
    <span v-else class="pagination-button" aria-disabled="true"><ArticleIcon name="back" />上一页</span>
    <span class="pagination-current"><strong>{{ page }}</strong><span>/</span>{{ totalPages }}</span>
    <NuxtLink v-if="page < totalPages" :to="pageLink(page + 1)" class="pagination-button">下一页<ArticleIcon name="back" class="pagination-next" /></NuxtLink>
    <span v-else class="pagination-button" aria-disabled="true">下一页<ArticleIcon name="back" class="pagination-next" /></span>
  </nav>
</template>

<script setup>
const props = defineProps({
  page: { type: Number, required: true },
  total: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
})
const route = useRoute()
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

function pageLink(page) {
  const query = { ...route.query }
  if (page <= 1) delete query.page
  else query.page = String(page)
  return { path: route.path, query }
}
</script>

<style scoped>
.content-pagination { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 16px; margin-top: 30px; }
.pagination-button { display: inline-flex; justify-content: center; align-items: center; gap: 8px; padding: 10px 15px; min-height: 42px; border: 1px solid #e1e8e0; border-radius: 7px; background: white; color: #234e22; font-size: 12px; }
.pagination-button svg { width: 15px; height: 15px; }
.pagination-button:hover { border-color: #aec5a8; }
.pagination-button[aria-disabled='true'] { color: #a0aaa0; background: transparent; }
.pagination-button[aria-disabled='true']:hover { border-color: #e1e8e0; }
.pagination-next { transform: rotate(180deg); }
.pagination-current { display: flex; gap: 10px; align-items: center; color: #637168; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11px; }
.pagination-current strong { color: #20332a; font-weight: 500; }
@media (max-width: 479px) { .content-pagination { gap: 12px; } .pagination-button { padding-inline: 12px; min-height: 44px; } }
</style>
