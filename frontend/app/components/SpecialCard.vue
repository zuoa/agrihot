<template>
  <article class="special-card" :class="{ 'special-card-lead': lead }">
    <NuxtLink :to="`/specials/${special.id}`">
      <div class="special-card-kicker">
        <span class="special-kind-badge" :class="special.kind === 'research' ? 'kind-research' : 'kind-event'">{{ special.kind === 'research' ? '研究前沿' : '事件追踪' }}</span>
        <span class="special-status" :class="{ 'is-live': special.status !== 'archived' }">{{ special.status === 'archived' ? '已归档' : '持续追踪' }}</span>
      </div>
      <h2>{{ special.title }}</h2>
      <p v-if="summary && !progress" class="special-card-summary">{{ summary }}</p>
      <div v-if="progress" class="special-card-progress"><span>最新进展 <time :datetime="progress.date">{{ progress.date }}</time></span><p>{{ progressText }}</p></div>
      <div class="special-card-footer"><span>{{ special.item_count }} 篇文章 · {{ special.source_count }} 组独立证据</span><span class="special-card-arrow" aria-hidden="true">↗</span></div>
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
.special-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--site-line, #e0e8de);
  border-radius: 16px;
  background: white;
  min-width: 0;
  box-shadow: var(--site-shadow-xs, 0 1px 2px rgba(20, 42, 28, 0.04));
  transition: border-color .22s var(--site-ease, ease), box-shadow .24s var(--site-ease, ease), transform .24s var(--site-ease, ease);
}
.special-card:hover {
  border-color: #afc9aa;
  box-shadow: var(--site-shadow-hover, 0 14px 30px -16px rgba(24, 58, 32, 0.18));
  transform: translateY(-2px);
}
.special-card-lead {
  border-color: #bdd3b7;
  background: linear-gradient(155deg, #f3faf0 0%, #ffffff 58%);
  box-shadow: var(--site-shadow-sm, 0 4px 14px -6px rgba(24, 52, 32, 0.08));
}
.special-card-lead::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: linear-gradient(90deg, #234e22 0%, #48973f 65%, #95ca87 100%);
}
.special-card > a { display: flex; flex-direction: column; height: 100%; padding: 22px; border-radius: inherit; }
.special-card a:hover h2 { color: #2f752a; }
.special-card a:focus-visible { outline: 2px solid var(--site-green); outline-offset: 4px; }
.special-card-kicker { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 11px; }
.special-kind-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 11px;
  line-height: 1.5;
}
.kind-research { background: #e8f3e5; color: #1f4f22; }
.kind-event { background: #fbf1df; color: #865416; }
.special-status { display: inline-flex; align-items: center; gap: 5px; color: var(--site-muted); font-size: 11px; }
.special-status.is-live { color: #2b6529; font-weight: 500; }
.special-status.is-live::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: #44963c;
  box-shadow: 0 0 0 3px rgba(68, 150, 60, 0.2);
}
.special-card h2 {
  min-height: 3.1em;
  margin: 14px 0 10px;
  color: var(--site-ink, #1a2d24);
  font-size: 19px;
  font-weight: 650;
  line-height: 1.55;
  letter-spacing: -.018em;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color .18s ease;
}
.special-card-summary { color: var(--site-muted); font-size: 13px; line-height: 1.85; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.special-card-progress {
  padding: 11px 13px;
  border-radius: 10px;
  border: 1px solid #e2ece0;
  background: #f5faf3;
  margin-top: 12px;
}
.special-card-progress > span { display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 10.5px; color: var(--site-muted); font-variant-numeric: tabular-nums; }
.special-card-progress p { margin-top: 5px; font-size: 12.5px; line-height: 1.75; color: #234e22; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.special-card-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid #edf2eb;
  font-size: 11px;
  color: var(--site-muted);
  font-variant-numeric: tabular-nums;
}
.special-card-summary, .special-card-progress { margin-bottom: 16px; }
.special-card-arrow {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #f1f6ef;
  color: var(--site-green);
  font-size: 12px;
  transition: background-color .18s ease, color .18s ease, transform .22s var(--site-ease, ease);
}
.special-card:hover .special-card-arrow {
  background: var(--site-green);
  color: white;
  transform: translate(1.5px, -1.5px);
}
.special-card-date { margin-top: 6px; color: #78887d; font-size: 10.5px; }
@media (max-width: 767px) { .special-card > a { padding: 18px 19px; } .special-card h2 { min-height: 0; font-size: 18px; } .special-card-progress p { -webkit-line-clamp: 2; } }
</style>
