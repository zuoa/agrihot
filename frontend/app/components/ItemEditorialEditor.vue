<template>
  <fieldset class="editorial-editor" :disabled="!ready">
    <legend>关注点与一手来源</legend>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!ready">正在读取编辑状态…</p>
    <template v-else>
      <p v-if="stale" class="editorial-stale">原文已变更，旧关注点与来源标识已隐藏。请核对后重新确认。</p>
      <label>关注点<textarea v-model="point" maxlength="120" rows="3" @input="attentionLocked = true" /></label>
      <label class="editorial-check"><input v-model="attentionLocked" type="checkbox">锁定关注点，重新评分时保留</label>
      <label>当前文章原文的来源<select v-model="sourceType" @change="provenanceLocked = true"><option value="">未确认一手来源</option><option value="policy">政策原文</option><option value="research">原始研究</option><option value="report">原始数据或报告</option><option value="announcement">主体公告</option></select></label>
      <label class="editorial-check"><input v-model="provenanceLocked" type="checkbox">锁定来源判断，重新评分时保留</label>
      <button v-if="stale" type="button" :aria-pressed="reconfirm" @click="reconfirm = !reconfirm">{{ reconfirm ? '已确认，将随保存生效' : '确认当前关注点与来源' }}</button>
      <details v-if="evidence"><summary>查看判定依据</summary><p>{{ evidence }}</p></details>
    </template>
  </fieldset>
</template>
<script setup>
const props = defineProps({ itemId: { type: Number, required: true } })
const api = useApi()
const ready = ref(false), error = ref(''), point = ref(''), sourceType = ref('')
const attentionLocked = ref(false), provenanceLocked = ref(false), stale = ref(false), reconfirm = ref(false), evidence = ref('')
let original = {}
onMounted(async () => {
  try {
    const data = await api.adminItemEditorial(props.itemId)
    point.value = data.attention_point || data.meta?.stale_attention || ''
    sourceType.value = data.source_provenance?.type || ''
    attentionLocked.value = !!data.meta?.attention_locked
    provenanceLocked.value = !!data.meta?.provenance_locked
    stale.value = data.meta?.status === 'pending' || !!data.meta?.stale_attention
    evidence.value = data.meta?.provenance_evidence?.manual ? '管理员确认' : data.meta?.provenance_evidence?.quote || ''
    original = { point: point.value, source: sourceType.value, attentionLocked: attentionLocked.value, provenanceLocked: provenanceLocked.value }
    ready.value = true
  } catch (e) { error.value = e.message }
})
function patch() {
  if (!ready.value) return null
  const result = {}
  if (reconfirm.value || point.value !== original.point) result.attention_point = point.value.trim() || null
  if (reconfirm.value || sourceType.value !== original.source) result.source_provenance = { type: sourceType.value || null }
  if (attentionLocked.value !== original.attentionLocked || 'attention_point' in result) result.attention_locked = attentionLocked.value
  if (provenanceLocked.value !== original.provenanceLocked || 'source_provenance' in result) result.provenance_locked = provenanceLocked.value
  return Object.keys(result).length ? result : null
}
defineExpose({ patch })
</script>
<style scoped>
.editorial-editor { border: 1px solid #d3dfce; border-radius: 8px; padding: 12px; display: grid; gap: 12px; font-size: 12px; color: #637168; }
legend { padding: 0 5px; color: #234e22; }
label { display: grid; gap: 6px; }
textarea, select { width: 100%; padding: 8px; border: 1px solid #d3dfce; border-radius: 6px; color: #20332a; background: white; }
.editorial-check { display: flex; align-items: center; gap: 6px; }
.editorial-stale { color: #796231; line-height: 1.8; }
button { padding: 8px; border: 1px solid #b8ccb1; border-radius: 6px; color: #234e22; }
details p { margin-top: 8px; line-height: 1.8; overflow-wrap: anywhere; }
</style>
