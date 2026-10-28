<template>
  <section class="context-panel" aria-label="主题与信源">
    <div v-if="item.primary_topic || item.secondary_topics?.length" class="context-topics">
      <h2>所属主题</h2>
      <div class="context-topic-links">
        <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path" class="primary-topic">{{ item.primary_topic.name }}<ArticleIcon name="external" /></NuxtLink>
        <NuxtLink v-for="topic in item.secondary_topics || []" :key="topic.code" :to="topic.path">{{ topic.name }}</NuxtLink>
      </div>
    </div>
    <div class="context-sources">
      <div class="sources-heading"><h2>参考信源</h2><span>{{ sources.length }} 个来源</span></div>
      <ul>
        <li v-for="(source, index) in sources" :key="index">
          <a :href="source.url || item.url" target="_blank" rel="noopener"><span class="source-indicator" aria-hidden="true"></span><span>{{ source.name || '原文链接' }}</span><ArticleIcon name="external" /></a>
        </li>
      </ul>
    </div>
    <div class="context-share">
      <button type="button" @click="copyLink"><ArticleIcon :name="copied ? 'check' : 'link'" /><span>{{ copied ? '链接已复制' : '复制本页链接' }}</span></button>
      <EmbeddingBadge v-if="showAdmin && item.embedding_ready" />
      <p class="sr-only" role="status">{{ copied ? '链接已复制' : copyError }}</p>
      <p v-if="copyError" class="copy-error">{{ copyError }}</p>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({ item: { type: Object, required: true } })
const showAdmin = useClientAdmin()
const copied = ref(false)
const copyError = ref('')
const sources = computed(() => (
  props.item.sources?.length
    ? props.item.sources
    : [{ name: props.item.source_name, url: props.item.url }]
))
watch(() => props.item?.id, () => { copied.value = false; copyError.value = '' })

async function copyLink() {
  copied.value = false
  copyError.value = ''
  const url = window.location.href
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
  } catch {
    const input = document.createElement('textarea')
    const previousFocus = document.activeElement
    input.value = url
    input.setAttribute('readonly', '')
    input.style.cssText = 'position:fixed;opacity:0;pointer-events:none'
    document.body.appendChild(input)
    try {
      input.select()
      copied.value = document.execCommand('copy')
    } catch {
      copied.value = false
    } finally {
      input.remove()
      previousFocus?.focus()
    }
    if (!copied.value) copyError.value = '复制失败，请从地址栏复制链接。'
  }
}
</script>

<style scoped>
.context-panel { padding: 22px; border: 1px solid #e1e8e0; border-radius: 14px; background: #fff; }
.context-panel h2 { font-size: 12px; font-weight: 600; color: #20332a; }
.context-panel a:focus-visible, .context-panel button:focus-visible { outline: 2px solid #234e22; outline-offset: 4px; border-radius: 3px; }
.context-topics { padding-bottom: 20px; margin-bottom: 20px; border-bottom: 1px solid #e1e8e0; }
.context-topic-links { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 10px; }
.context-topic-links a { display: inline-flex; align-items: center; gap: 8px; color: #234e22; font-size: 12px; line-height: 1.8; min-height: 30px; }
.context-topic-links .primary-topic { flex-basis: 100%; font-size: 14px; font-weight: 600; }
.context-topic-links svg { width: 15px; height: 15px; }
.context-panel a:hover { text-decoration: underline; text-underline-offset: 4px; }
.sources-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.sources-heading > span { font-size: 10px; color: #637168; }
.context-sources ul { margin-top: 12px; display: grid; gap: 7px; }
.context-sources a { display: flex; align-items: center; gap: 9px; min-height: 32px; color: #435046; font-size: 12px; }
.context-sources a > span:nth-child(2) { flex: 1; min-width: 0; overflow-wrap: anywhere; line-height: 1.8; }
.source-indicator { width: 6px; height: 6px; border: 1px solid #82a678; border-radius: 50%; flex-shrink: 0; }
.context-sources svg { width: 15px; height: 15px; flex-shrink: 0; color: #637168; }
.context-share { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; margin-top: 18px; padding-top: 16px; border-top: 1px solid #e1e8e0; }
.context-share button { display: inline-flex; align-items: center; gap: 7px; min-height: 32px; color: #234e22; font-size: 11px; }
.context-share button:hover { text-decoration: underline; text-underline-offset: 4px; }
.context-share svg { width: 15px; height: 15px; }
.copy-error { width: 100%; margin-top: 8px; font-size: 11px; color: #b64d43; }
@media (min-width: 768px) and (max-width: 1023px) { .context-panel { padding: 18px; } }
@media (max-width: 767px) { .context-share button, .context-topic-links a, .context-sources a { min-height: 44px; } }
</style>
