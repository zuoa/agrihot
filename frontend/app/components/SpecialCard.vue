<template>
  <article class="special-card" :class="{ 'special-card-lead': lead }">
    <NuxtLink :to="`/specials/${special.id}`">
      <div class="special-card-kicker"><span>{{ special.kind === 'research' ? '研究前沿' : '事件追踪' }}</span><span>{{ special.status === 'archived' ? '已归档' : '持续追踪' }}</span></div>
      <h2>{{ special.title }}</h2>
      <p class="special-card-summary">{{ special.summary }}</p>
      <ul v-if="lead && special.findings?.length" class="special-card-findings"><li v-for="(finding, index) in special.findings" :key="index">{{ finding.text }}</li></ul>
      <div class="special-card-footer"><span>{{ special.item_count }} 篇文章 · {{ special.source_count }} 组独立证据</span><span v-if="lead">阅读专题 <span aria-hidden="true">↗</span></span></div>
      <p class="special-card-date">内容更新 {{ fmtDate(special.content_updated_at) }}</p>
    </NuxtLink>
  </article>
</template>
<script setup>
defineProps({ special: { type: Object, required: true }, lead: Boolean })
</script>
<style scoped>
.special-card { border: 1px solid var(--site-line); border-radius: 12px; background: white; min-width: 0; }
.special-card > a { display: flex; flex-direction: column; height: 100%; padding: 22px; border-radius: inherit; }
.special-card a:hover h2 { color: #327a2d; }
.special-card a:focus-visible { outline: 2px solid var(--site-green); outline-offset: 4px; }
.special-card-kicker { display: flex; justify-content: space-between; gap: 12px; color: var(--site-muted); font-size: 11px; }
.special-card-kicker > span:first-child { color: var(--site-green); font-weight: 600; }
.special-card h2 { margin: 14px 0 10px; font-size: 19px; font-weight: 650; line-height: 1.65; overflow-wrap: anywhere; }
.special-card-summary { color: var(--site-muted); font-size: 13px; line-height: 1.9; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.special-card-footer { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; margin-top: auto; padding-top: 20px; font-size: 11px; color: var(--site-green); }
.special-card-date { margin-top: 8px; color: var(--site-muted); font-size: 10px; }
.special-card-lead { border-top: 3px solid var(--site-green); }
.special-card-lead > a { padding: 27px 30px; }
.special-card-lead h2 { font-family: 'Songti SC', 'Noto Serif CJK SC', SimSun, serif; font-size: 29px; line-height: 1.65; margin-top: 20px; }
.special-card-lead .special-card-summary { -webkit-line-clamp: 4; font-size: 14px; }
.special-card-findings { display: grid; gap: 10px; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--site-line); }
.special-card-findings li { padding-left: 13px; border-left: 2px solid #9bb793; font-size: 12px; line-height: 1.8; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
@media (max-width: 767px) { .special-card-lead > a { padding: 22px; } .special-card-lead h2 { font-size: 25px; } }
</style>
