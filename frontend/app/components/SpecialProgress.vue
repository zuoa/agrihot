<template>
  <template v-if="rows.length">
    <section id="latest-progress" class="progress-section latest-progress" aria-labelledby="latest-progress-title">
      <div class="progress-heading"><h2 id="latest-progress-title">最新进展</h2><span>{{ dateLabel(latest) }} · <time :datetime="latest.date">{{ latest.date }}</time></span></div>
      <h3 v-if="latest.title">{{ latest.title }}</h3>
      <SpecialClaim v-if="!repeatsOverview" :claim="latest.claim" :source-numbers="sourceNumbers" />
      <a class="latest-progress-link" href="#timeline">查看时间线 <span aria-hidden="true">↓</span></a>
    </section>
    <section id="timeline" class="progress-section" aria-labelledby="timeline-title">
      <div class="progress-heading"><h2 id="timeline-title">进展时间线</h2><button type="button" :aria-pressed="oldestFirst" @click="oldestFirst = !oldestFirst">{{ oldestFirst ? '最早在前' : '最新在前' }} <span aria-hidden="true">↕</span></button></div>
      <ol id="progress-nodes" class="progress-timeline">
        <li v-for="(entry, index) in visibleRows" :key="entry.id || `${entry.date}-${index}`">
          <div class="progress-meta"><time :datetime="entry.date">{{ entry.date }}</time><span>{{ dateLabel(entry) }}</span><strong v-if="newIds.includes(entry.id)">本次新增</strong></div>
          <h3 v-if="entry.title">{{ entry.title }}</h3>
          <SpecialClaim :claim="entry.claim" :source-numbers="sourceNumbers" />
          <div class="progress-sources"><template v-for="source in nodeSources(entry)" :key="source.id"><NuxtLink v-if="source.item_id" :to="`/items/${source.item_id}`">{{ source.publisher || source.title }} ↗</NuxtLink><a v-else :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.publisher || source.title }} ↗</a></template></div>
        </li>
      </ol>
      <button v-if="rows.length > 5" type="button" class="progress-expand" :aria-expanded="expanded" aria-controls="progress-nodes" @click="expanded = !expanded">{{ expanded ? '收起较早进展' : `展开全部 ${rows.length} 条进展` }}</button>
    </section>
  </template>
</template>
<script setup>
const props = defineProps({ entries: { type: Array, default: () => [] }, sources: { type: Array, default: () => [] }, sourceNumbers: { type: Object, default: () => ({}) }, newIds: { type: Array, default: () => [] }, overviewText: { type: String, default: '' } })
const expanded = ref(false)
const oldestFirst = ref(false)
const rows = computed(() => [...props.entries].sort((a, b) => b.date.localeCompare(a.date)))
const latest = computed(() => rows.value[0])
const repeatsOverview = computed(() => latest.value?.claim.text.trim() === props.overviewText.trim())
const visibleRows = computed(() => {
  const sorted = oldestFirst.value ? [...rows.value].reverse() : rows.value
  return expanded.value ? sorted : sorted.slice(0, 5)
})
function dateLabel(entry) { return entry.date_basis === 'event' ? '事件发生日' : entry.date_basis === 'published' ? '报道日期' : '日期' }
function nodeSources(entry) {
  const ids = new Set(entry.claim.citations.map(c => c.source_id))
  return props.sources.filter(source => ids.has(source.id))
}
watch(() => props.entries, () => { expanded.value = false; oldestFirst.value = false })
</script>
<style scoped>
.progress-section { margin-bottom: 38px; }
.progress-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 10px 20px; padding-bottom: 13px; border-bottom: 1px solid var(--site-line); margin-bottom: 20px; }
.progress-heading h2 { font-size: 20px; font-weight: 650; }
.progress-heading > span, .progress-heading button { font-size: 11px; color: var(--site-muted); line-height: 1.8; }
.progress-heading button { min-height: 36px; color: var(--site-green); }
.latest-progress { padding: 17px 20px; border-left: 2px solid #9bb793; border-radius: 0 8px 8px 0; background: var(--site-soft); }
.latest-progress .progress-heading { padding: 0; border: 0; margin-bottom: 10px; }
.latest-progress .progress-heading h2 { font-size: 16px; }
.latest-progress-link { display: inline-flex; align-items: center; gap: 7px; margin-top: 9px; min-height: 28px; font-size: 11px; color: var(--site-green); }
.latest-progress h3, .progress-timeline h3 { font-size: 16px; font-weight: 600; line-height: 1.8; color: var(--site-green); margin-bottom: 8px; }
.progress-timeline { border-left: 1px solid #b8ccb1; margin-left: 8px; padding-left: 26px; }
.progress-timeline li { position: relative; padding-bottom: 28px; }
.progress-timeline li::before { position: absolute; content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--site-green); left: -30px; top: 8px; }
.progress-meta { display: flex; flex-wrap: wrap; gap: 7px 12px; font-size: 11px; color: var(--site-muted); margin-bottom: 8px; line-height: 1.8; }
.progress-meta strong { font-weight: 500; color: var(--site-green); }
.progress-sources { display: flex; flex-wrap: wrap; gap: 5px 14px; margin-top: 9px; font-size: 11px; color: var(--site-green); line-height: 1.8; }
.progress-expand { min-height: 44px; padding: 10px 18px; border: 1px solid var(--site-line); border-radius: 6px; font-size: 12px; color: var(--site-green); }
button:focus-visible, a:focus-visible { outline: 2px solid var(--site-green); outline-offset: 3px; }
@media (max-width: 767px) { .latest-progress { padding: 15px 16px; } }
</style>
