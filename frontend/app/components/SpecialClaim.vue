<template>
  <div class="special-claim">
    <span v-if="label" class="claim-label" :class="`claim-label-${claim.kind}`">{{ label }}</span>
    <p>{{ claim.text }} <span class="claim-citations"><a v-for="citation in uniqueCitations" :key="citation.source_id" :href="`#source-${citation.source_id}`" :title="citation.quote" :aria-label="`查看来源 ${sourceNumbers[citation.source_id] || citation.source_id}`">[{{ sourceNumbers[citation.source_id] || citation.source_id }}]</a></span></p>
  </div>
</template>
<script setup>
const props = defineProps({ claim: { type: Object, required: true }, sourceNumbers: { type: Object, default: () => ({}) }, showLabel: Boolean })
const labels = { finding: '单项发现', shared: '共同发现', difference: '研究差异', question: '尚待解答', inference: '延伸思考' }
const label = computed(() => props.showLabel ? labels[props.claim.kind] : '')
const uniqueCitations = computed(() => [...new Map((props.claim.citations || []).map(c => [c.source_id, c])).values()])
</script>
<style scoped>
.special-claim p { font-size: 15px; line-height: 2; color: #435046; overflow-wrap: anywhere; white-space: pre-line; }
.claim-label { display: inline-block; margin-bottom: 9px; font-size: 11px; font-weight: 600; color: var(--site-green); }
.claim-label-difference, .claim-label-question { color: #796231; }
.claim-label-inference { color: #486a83; }
.claim-citations { display: inline-flex; gap: 5px; vertical-align: super; font-size: 10px; line-height: 1.4; }
.claim-citations a { color: var(--site-green); padding: 4px 2px; text-decoration: underline; text-underline-offset: 3px; }
</style>
