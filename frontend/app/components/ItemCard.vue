<template>
  <article class="item-card">
    <div class="item-card-meta">
      <div class="item-card-source"><span class="item-card-category" :class="categoryClass">{{ item.category || '资讯' }}</span><span>{{ item.source_name || '未知来源' }}</span><SourceProvenance :provenance="item.source_provenance" /><EmbeddingBadge v-if="item.embedding_ready" /></div>
      <time :datetime="item.published_at || item.created_at">{{ timeText }}</time>
    </div>
    <NuxtLink :to="`/items/${item.id}`" class="item-card-title"><h2>{{ item.title }}</h2></NuxtLink>
    <p v-if="blurb" class="item-card-blurb" :class="{ 'line-clamp-3': clamp }">{{ blurb }}</p>
    <AttentionPoint :text="item.attention_point" compact />
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
const CATEGORY_TONE = { 政策: 'cat-policy', 论文: 'cat-paper', 报道: 'cat-report', 行业: 'cat-industry' }
const categoryClass = computed(() => CATEGORY_TONE[props.item.category] || 'cat-default')

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
.item-card {
  min-width: 0;
  padding: 22px 24px 17px;
  background: white;
  border: 1px solid var(--site-line, #e0e8de);
  border-radius: 15px;
  box-shadow: var(--site-shadow-xs, 0 1px 2px rgba(20, 42, 28, 0.04));
  transition: border-color .2s var(--site-ease, ease), box-shadow .24s var(--site-ease, ease), transform .24s var(--site-ease, ease);
}
.item-card:hover {
  border-color: #b7ceb2;
  box-shadow: var(--site-shadow-hover, 0 14px 30px -16px rgba(24, 58, 32, 0.18));
  transform: translateY(-1.5px);
}
.item-card a:focus-visible, .item-card button:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; border-radius: 3px; }
.item-card-meta { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 7px 14px; font-size: 11.5px; color: #5d6c62; }
.item-card-source { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 9px; min-width: 0; flex: 1; }
.item-card-source > span { overflow-wrap: anywhere; }
.item-card-category {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: .02em;
}
.item-card-category.cat-policy { background: #e8f3e5; color: #1f4f22; }
.item-card-category.cat-paper { background: #eaf0f8; color: #294c76; }
.item-card-category.cat-report { background: #e6f4f1; color: #1b5a52; }
.item-card-category.cat-industry { background: #faf1e0; color: #875516; }
.item-card-category.cat-default { background: #eef3ec; color: #36503b; }
.item-card-meta time { flex-shrink: 0; font-size: 11px; color: #758479; font-variant-numeric: tabular-nums; }
.item-card-title { display: block; margin-top: 12px; }
.item-card-title h2 { color: #1a2d24; font-size: 18px; font-weight: 650; line-height: 1.58; letter-spacing: -.018em; overflow-wrap: anywhere; transition: color .18s ease; }
.item-card-title:hover h2 { color: #2f752a; }
.item-card-blurb { margin-top: 9px; color: #536358; font-size: 13.5px; line-height: 1.88; overflow-wrap: anywhere; }
.item-card-topics { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-top: 14px; font-size: 11px; }
.item-card-topic, .item-card-direction {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 6px;
  background: #f0f6ee;
  border: 1px solid #dce8d8;
  color: #234e22;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.7;
  transition: background-color .15s, border-color .15s;
}
.item-card-topic:hover { background: #e5f1e1; border-color: #b5ceb0; text-decoration: none !important; }
.item-card-tag {
  display: inline-flex;
  gap: 2px;
  padding: 2px 7px;
  border-radius: 6px;
  color: #5d6c62;
  min-height: 26px;
  align-items: center;
  overflow-wrap: anywhere;
  transition: background-color .15s, color .15s;
}
.item-card-tag > span { color: #95a791; }
.item-card-tag:hover { background: #f2f7f0; color: #234e22; text-decoration: none !important; }
.item-card-more { padding: 2px 6px; border-radius: 6px; background: #f3f6f2; color: #5d6c62; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 10px; }
.item-card-more:hover { background: #e6efe3; color: #234e22; text-decoration: none !important; }
.item-card-foot { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; margin-top: 15px; padding-top: 12px; border-top: 1px solid #edf2eb; font-size: 11px; color: #67776c; }
.item-card-signals, .item-card-counts { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; font-variant-numeric: tabular-nums; }
.item-card-selected {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eaf4e7;
  color: #234e22;
  font-weight: 500;
}
.item-card-selected svg { width: 12px; height: 12px; }
.item-card-score {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f4f7f2;
  color: #4d5f52;
  transition: background-color .15s, color .15s;
}
.item-card-score:hover { background: #e8f2e5; color: #234e22; }
.item-card-score strong { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px; font-weight: 600; color: #234e22; }
.item-card-hotness {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: #fbf2e4;
  color: #915c1a;
  font-weight: 500;
}
.item-card-admin { display: flex; gap: 16px; justify-content: flex-end; margin-top: 12px; padding-top: 10px; border-top: 1px dashed #e1e8e0; font-size: 11px; color: #234e22; }
.item-card-admin button { min-height: 32px; }
.item-card-admin button:disabled { opacity: .5; }
.item-card-delete { color: #b64d43; }
@media (max-width: 767px) {
  .item-card { padding: 19px 18px 15px; }
  .item-card-title h2 { font-size: 17px; }
  .item-card-meta { gap: 5px 10px; }
  .item-card-source { gap: 6px; }
  .item-card-tag, .item-card-topic, .item-card-more { min-height: 30px; }
  .item-card-admin button { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) { .item-card { transition: none; } }
</style>
