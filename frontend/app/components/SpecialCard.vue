<template>
  <article class="special-card" :class="{ 'special-card-lead': lead }">
    <NuxtLink :to="`/specials/${special.id}`">
      <div class="special-card-kicker"><span>{{ special.kind === 'research' ? '研究前沿' : '事件追踪' }}</span><span>{{ special.status === 'archived' ? '已归档' : '持续追踪' }}</span></div>
      <h2>{{ special.title }}</h2>
      <p v-if="summary && !progress" class="special-card-summary">{{ summary }}</p>
      <div v-if="progress" class="special-card-progress"><span>最新进展 <time :datetime="progress.date">{{ progress.date }}</time></span><p>{{ progressText }}</p></div>
      <div class="special-card-footer"><span>{{ special.item_count }} 篇文章 · {{ special.source_count }} 组独立证据</span><span aria-hidden="true">↗</span></div>
      <p v-if="!progress" class="special-card-date">内容更新 {{ fmtDate(special.content_updated_at) }}</p>
    </NuxtLink>
  </article>
</template>
<script setup>
const props = defineProps({ special: { type: Object, required: true }, lead: Boolean })
const normalize = value => String(value || '').replace(/\s+/g, ' ').trim()
const summary = computed(() => normalize(props.special.summary))
const progress = computed(() => props.special.kind === 'event' ? props.special.latest_progress : null)
const progressText = computed(() => normalize(progress.value?.text) || normalize(progress.value?.title))
</script>
<style scoped>
.special-card-progress { padding-top: 14px; border-top: 1px solid var(--site-line); margin-top: 16px; }
.special-card-progress > span { display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 10px; color: var(--site-muted); }
.special-card-progress p { margin-top: 7px; font-size: 13px; line-height: 1.8; color: var(--site-green); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.special-card { border: 1px solid var(--site-line); border-radius: 12px; background: white; min-width: 0; }
.special-card > a { display: flex; flex-direction: column; height: 100%; padding: 22px; border-radius: inherit; }
.special-card a:hover h2 { color: #327a2d; }
.special-card a:focus-visible { outline: 2px solid var(--site-green); outline-offset: 4px; }
.special-card-kicker { display: flex; justify-content: space-between; gap: 12px; color: var(--site-muted); font-size: 11px; }
.special-card-kicker > span:first-child { color: var(--site-green); font-weight: 600; }
.special-card h2 { min-height: 3.2em; margin: 14px 0 10px; font-size: 20px; font-weight: 650; line-height: 1.6; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.special-card-summary { color: var(--site-muted); font-size: 13px; line-height: 1.9; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.special-card-footer { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; margin-top: auto; padding-top: 20px; font-size: 11px; color: var(--site-muted); }
.special-card-date { margin-top: 8px; color: var(--site-muted); font-size: 10px; }
.special-card-lead { border-color: #b8ccb1; }
@media (max-width: 767px) { .special-card > a { padding: 17px 20px; } .special-card h2 { min-height: 0; font-size: 19px; } .special-card-progress p { -webkit-line-clamp: 2; } }
</style>
