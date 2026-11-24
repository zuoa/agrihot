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
.content-pagination { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 14px; margin-top: 32px; }
.pagination-button {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  min-height: 40px;
  border: 1px solid #dce6d9;
  border-radius: 999px;
  background: white;
  color: #234e22;
  font-size: 12.5px;
  font-weight: 500;
  box-shadow: var(--site-shadow-xs, 0 1px 2px rgba(20, 42, 28, 0.04));
  transition: border-color .18s ease, background-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.pagination-button svg { width: 15px; height: 15px; }
.pagination-button:hover { border-color: #a9c5a3; background: #f3f8f1; transform: translateY(-1px); box-shadow: var(--site-shadow-sm); }
.pagination-button[aria-disabled='true'] { color: #a0aca1; background: rgba(255, 255, 255, 0.5); box-shadow: none; transform: none; }
.pagination-button[aria-disabled='true']:hover { border-color: #dce6d9; background: rgba(255, 255, 255, 0.5); box-shadow: none; transform: none; }
.pagination-next { transform: rotate(180deg); }
.pagination-current {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 6px 14px;
  border-radius: 999px;
  background: #edf3eb;
  color: #5d6c62;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.pagination-current strong { color: #1a2d24; font-weight: 600; }
@media (max-width: 479px) { .content-pagination { gap: 10px; } .pagination-button { padding-inline: 13px; min-height: 44px; } }
</style>
