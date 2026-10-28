<template>
  <article class="item-card">
    <div class="item-card-meta">
      <div class="item-card-source"><span class="item-card-category">{{ item.category || '资讯' }}</span><span>{{ item.source_name || '未知来源' }}</span><EmbeddingBadge v-if="item.embedding_ready" /></div>
      <time :datetime="item.published_at || item.created_at">{{ timeText }}</time>
    </div>
    <NuxtLink :to="`/items/${item.id}`" class="item-card-title"><h2>{{ item.title }}</h2></NuxtLink>
    <p v-if="blurb" class="item-card-blurb" :class="{ 'line-clamp-3': clamp }">{{ blurb }}</p>
    <div v-if="item.primary_topic || item.paper?.direction || item.tags?.length" class="item-card-topics">
      <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path" class="item-card-topic">{{ item.primary_topic.name }}</NuxtLink>
      <span v-else-if="item.paper?.direction" class="item-card-direction">{{ item.paper.direction }}</span>
      <NuxtLink v-for="tag in (item.tags || []).slice(0, 3)" :key="tag" :to="`/tags/${encodeURIComponent(tag)}`" class="item-card-tag"><span aria-hidden="true">#</span>{{ tag }}</NuxtLink>
      <NuxtLink v-if="item.tags?.length > 3" :to="`/items/${item.id}#article-topics`" class="item-card-more" :aria-label="`查看其余 ${item.tags.length - 3} 个标签`">+{{ item.tags.length - 3 }}</NuxtLink>
    </div>
    <div class="item-card-foot">
      <div class="item-card-signals"><span v-if="item.is_selected" class="item-card-selected"><ArticleIcon name="insight" />精选</span><NuxtLink v-if="item.score != null" :to="`/items/${item.id}`" class="item-card-score" :aria-label="`AI 评分 ${item.score} 分`"><strong>{{ item.score }}</strong> 分</NuxtLink><span v-if="item.hotness >= 60" class="item-card-hotness">热度 {{ item.hotness }}</span></div>
      <div class="item-card-counts"><span v-if="item.sources?.length > 1">{{ item.sources.length }} 个信源</span><span>阅读 {{ item.view_count ?? 0 }}</span></div>
    </div>
    <div v-if="showAdmin" class="item-card-admin">
      <button type="button" @click="openEditor" :disabled="editing">{{ editing ? '加载中…' : '编辑' }}</button>
      <button type="button" @click="remove" :disabled="deleting" class="item-card-delete">{{ deleting ? '删除中…' : '删除' }}</button>
    </div>
    <p v-if="editError" role="alert" class="mt-2 text-xs text-red-600">{{ editError }}</p>
    <LazyItemEditModal v-if="editItem" :item="editItem" @close="editItem = null" @saved="(it) => $emit('updated', it)" />
  </article>
</template>

<script setup>
const props = defineProps({
  item: { type: Object, required: true },
  clamp: { type: Boolean, default: true },
})
const emit = defineEmits(['updated', 'deleted'])
const api = useApi()
const showAdmin = useClientAdmin()

const editItem = ref(null)
const editing = ref(false)
const editError = ref('')
const deleting = ref(false)
const blurb = computed(() => props.item.paper?.card?.tldr || props.item.summary_zh || props.item.summary)

async function openEditor() {
  editing.value = true
  editError.value = ''
  try {
    editItem.value = await api.item(props.item.id)
  } catch {
    editError.value = '条目加载失败，请重试。'
  } finally {
    editing.value = false
  }
}

async function remove() {
  if (!confirm(`确定删除「${props.item.title.slice(0, 30)}」？此操作不可恢复。`)) return
  deleting.value = true
  try {
    await api.adminDeleteItem(props.item.id)
    emit('deleted', props.item.id)
  } catch (e) {
    alert(e.message)
  } finally {
    deleting.value = false
  }
}

const timeText = computed(() => {
  const iso = props.item.published_at || props.item.created_at
  const today = shanghaiDateKey(iso) === shanghaiDateKey(new Date())
  return today ? fmtTime(iso) : fmtDay(iso)
})
</script>

<style scoped>
.item-card { min-width: 0; padding: 23px 25px 18px; background: white; border: 1px solid var(--site-line, #e1e8e0); border-radius: 14px; transition: border-color .15s; }
.item-card:hover { border-color: #aec5a8; }
.item-card a:focus-visible, .item-card button:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; border-radius: 3px; }
.item-card-meta { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 7px 16px; font-size: 11px; color: #637168; }
.item-card-source { display: flex; flex-wrap: wrap; align-items: center; gap: 7px 10px; min-width: 0; flex: 1; }
.item-card-source > span { overflow-wrap: anywhere; }
.item-card-category { color: #234e22; font-weight: 600; padding-right: 10px; border-right: 1px solid #e1e8e0; }
.item-card-meta time { flex-shrink: 0; font-size: 10px; font-variant-numeric: tabular-nums; }
.item-card-title { display: block; margin-top: 13px; }
.item-card-title h2 { color: #20332a; font-size: 18px; font-weight: 650; line-height: 1.65; letter-spacing: -.015em; overflow-wrap: anywhere; }
.item-card-title:hover h2 { color: #327a2d; }
.item-card-blurb { margin-top: 10px; color: #637168; font-size: 13px; line-height: 1.9; overflow-wrap: anywhere; }
.item-card-topics { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 10px; margin-top: 15px; font-size: 11px; }
.item-card-topic, .item-card-direction { color: #234e22; font-size: 11px; line-height: 1.8; }
.item-card-topic { font-weight: 500; }
.item-card-tag { display: inline-flex; gap: 3px; color: #637168; min-height: 28px; align-items: center; overflow-wrap: anywhere; }
.item-card-tag > span { color: #9bab96; }
.item-card-topics a:hover { color: #234e22; text-decoration: underline; text-underline-offset: 4px; }
.item-card-more { color: #637168; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 10px; }
.item-card-foot { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; margin-top: 16px; padding-top: 13px; border-top: 1px solid #edf1eb; font-size: 10px; color: #637168; }
.item-card-signals, .item-card-counts { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.item-card-selected { display: inline-flex; align-items: center; gap: 4px; color: #234e22; }
.item-card-selected svg { width: 12px; height: 12px; }
.item-card-score strong { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; font-weight: 500; color: #234e22; }
.item-card-hotness { color: #946324; }
.item-card-admin { display: flex; gap: 16px; justify-content: flex-end; margin-top: 12px; padding-top: 10px; border-top: 1px dashed #e1e8e0; font-size: 11px; color: #234e22; }
.item-card-admin button { min-height: 32px; }
.item-card-admin button:disabled { opacity: .5; }
.item-card-delete { color: #b64d43; }
@media (max-width: 767px) {
  .item-card { padding: 20px 19px 16px; }
  .item-card-title h2 { font-size: 17px; }
  .item-card-meta { gap: 5px 10px; }
  .item-card-source { gap: 6px; }
  .item-card-category { padding-right: 6px; }
  .item-card-tag, .item-card-topic, .item-card-more { min-height: 32px; }
  .item-card-admin button { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) { .item-card { transition: none; } }
</style>
