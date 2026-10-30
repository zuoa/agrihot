<template>
  <div class="space-y-5">
    <div class="flex flex-wrap gap-3 items-center justify-between"><p class="text-sm text-stone-500">自动发现专题并核验引用。编辑会锁定对应内容，后续自动更新保留人工修改。</p><button class="admin-special-button" :disabled="busy" @click="generate">发现与更新专题</button></div>
    <p v-if="message" role="status" class="text-sm text-leaf-800">{{ message }}</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <p v-if="loading" class="text-sm text-stone-500">加载中…</p>
    <div v-else-if="!data.specials.length" class="bg-white border rounded-lg p-8 text-sm text-stone-500">暂无专题。配置 DeepSeek 后，点击“发现与更新专题”或等待每日定时运行。材料不足时不会强行生成。</div>
    <div v-else class="overflow-x-auto bg-white border border-stone-200 rounded-lg"><table class="w-full text-sm text-left"><thead class="bg-stone-50 text-stone-500"><tr><th class="p-3">专题</th><th class="p-3">状态</th><th class="p-3">外部补充</th><th class="p-3">最近检查</th><th class="p-3">操作</th></tr></thead><tbody><tr v-for="s in data.specials" :key="s.id" class="border-t border-stone-100"><td class="p-3 max-w-sm"><span class="text-xs text-stone-400">#{{ s.id }} · {{ s.kind === 'research' ? '研究前沿' : '事件追踪' }}{{ s.pinned ? ' · 置顶' : '' }}</span><p class="mt-1">{{ s.title }}</p><p v-if="s.last_error" class="text-xs text-red-700 mt-1">{{ s.last_error }}</p></td><td class="p-3 whitespace-nowrap">{{ statuses[s.status] || s.status }}<p v-if="!s.evidence_valid && ['published', 'archived'].includes(s.status)" class="text-xs text-amber-700">来源变更，公开页暂不可见</p><p v-if="s.locked_fields.length" class="text-xs text-stone-400">已锁定 {{ s.locked_fields.join('、') }}</p></td><td class="p-3 text-xs">{{ externalStatuses[s.external_status] || s.external_status }}</td><td class="p-3 text-xs whitespace-nowrap">{{ s.checked_at ? fmtDateTime(s.checked_at) : '尚未检查' }}</td><td class="p-3"><div class="flex flex-wrap gap-3"><button class="text-leaf-700" @click="open(s.id)">编辑</button><NuxtLink v-if="s.evidence_valid && ['published', 'archived'].includes(s.status)" :to="`/specials/${s.id}`" target="_blank" class="text-leaf-700">预览 ↗</NuxtLink></div></td></tr></tbody></table></div>
    <div class="flex gap-4 items-center text-sm"><button :disabled="page === 1" @click="page--; load()">上一页</button><span>{{ page }}</span><button :disabled="page * 20 >= data.total" @click="page++; load()">下一页</button></div>
    <section v-if="editing" class="bg-white border border-stone-200 rounded-xl p-5 space-y-4">
      <div class="flex justify-between items-center"><h2 class="font-bold">编辑专题 #{{ editing.id }}</h2><button @click="editing = null">关闭</button></div>
      <label class="block text-sm">标题<input v-model="editing.title" maxlength="200" class="admin-special-input"></label>
      <label class="block text-sm">议题范围<textarea v-model="editing.scope" rows="3" class="admin-special-input" /></label>
      <div class="flex flex-wrap gap-5"><label class="text-sm">状态<select v-model="editing.status" class="admin-special-input"><option v-for="(label, value) in statuses" :key="value" :value="value" :disabled="value === 'merged' || value === 'draft'">{{ label }}</option></select></label><label class="flex items-center gap-2 text-sm"><input v-model="editing.pinned" type="checkbox">首页置顶</label></div>
      <fieldset class="flex flex-wrap gap-5 text-sm"><legend class="text-xs text-stone-500 mb-2">锁定内容（取消勾选后恢复自动更新）</legend><label v-for="field in lockOptions" :key="field.value" class="flex gap-2"><input v-model="editing.locked_fields" type="checkbox" :value="field.value">{{ field.label }}</label></fieldset>
      <details><summary class="cursor-pointer text-sm text-leaf-700">调整关联文章</summary><p class="text-xs text-stone-500 mt-3">文章 ID 来自内容页；同一成果的报道应使用相同证据组。保存后，重新生成使文章变更进入公开版本。</p><div v-for="(entry, index) in editing.items" :key="index" class="grid sm:grid-cols-4 gap-2 border-b py-3"><label class="text-xs">文章 ID<input v-model.number="entry.item_id" type="number" min="1" class="admin-special-input"></label><label class="text-xs">角色<select v-model="entry.role" class="admin-special-input"><option value="core">核心材料</option><option value="background">背景阅读</option></select></label><label class="text-xs">证据组<input v-model="entry.evidence_group" class="admin-special-input"></label><label class="text-xs">关联原因<input v-model="entry.reason" class="admin-special-input"></label><button class="text-xs text-red-700 text-left" @click="editing.items.splice(index, 1)">移除文章</button></div><button class="text-sm text-leaf-700 mt-3" @click="editing.items.push({ item_id: null, role: 'core', reason: '', evidence_group: '' })">添加文章</button></details>
      <details><summary class="cursor-pointer text-sm text-leaf-700">修订综合内容与引用</summary><p class="text-xs text-stone-500 my-3">保留结构及来源 ID，引用 quote 必须能在来源中找到。保存后将锁定综合内容。</p><textarea v-model="documentText" rows="18" spellcheck="false" aria-label="专题综合内容 JSON" class="admin-special-input font-mono text-xs" /></details>
      <details><summary class="cursor-pointer text-sm text-leaf-700">来源与发布记录</summary><ul class="space-y-2 mt-3 text-xs text-stone-500"><li v-for="source in editing.sources" :key="source.id">{{ source.id }} · {{ source.title }} · {{ source.basis === 'abstract' ? '摘要' : '正文片段' }}</li><li v-for="version in editing.versions" :key="version.id">{{ fmtDateTime(version.date) }} · {{ version.changes }}</li></ul></details>
      <div class="flex flex-wrap gap-3"><button class="admin-special-button" :disabled="busy" @click="save">保存修改</button><button class="admin-special-button admin-special-secondary" :disabled="busy" @click="regenerate">重新生成</button></div>
      <details class="border-t pt-4"><summary class="cursor-pointer text-sm text-stone-500">合并到其他专题</summary><p class="text-xs text-stone-500 mt-2">合并后当前专题链接转到目标专题，关联文章汇入目标；请在合并后重新生成目标专题。</p><div class="flex gap-3 mt-3"><label class="text-xs">目标专题 ID<input v-model.number="mergeId" type="number" min="1" class="admin-special-input"></label><button class="text-sm text-leaf-700" :disabled="busy || !mergeId" @click="merge">合并专题</button></div></details>
    </section>
  </div>
</template>
<script setup>
definePageMeta({ layout: 'admin', title: '热点专题', middleware: 'admin-auth' })
const api = useApi()
const page = ref(1)
const data = ref({ specials: [], total: 0 })
const loading = ref(true)
const busy = ref(false)
const message = ref('')
const error = ref('')
const editing = ref(null)
const original = ref(null)
const documentText = ref('')
const mergeId = ref(null)
const statuses = { draft: '待生成', published: '已发布', archived: '已归档', withdrawn: '已下架', merged: '已合并' }
const externalStatuses = { not_run: '尚未运行', ok: '已补充', partial: '部分成功', academic_only: '仅学术资料', academic_partial: '学术资料部分成功', unavailable: '服务暂不可用', no_results: '暂无可用资料' }
const lockOptions = [{ value: 'title', label: '标题' }, { value: 'scope', label: '范围' }, { value: 'items', label: '关联文章' }, { value: 'document', label: '综合内容' }]
async function load() { loading.value = true; try { data.value = await api.adminSpecials({ page: page.value }) } catch (e) { error.value = e.message } finally { loading.value = false } }
async function action(fn, success) { busy.value = true; error.value = ''; message.value = ''; try { await fn(); message.value = success; await load() } catch (e) { error.value = e.message } finally { busy.value = false } }
async function open(id) { error.value = ''; try { editing.value = await api.adminSpecial(id); original.value = JSON.parse(JSON.stringify(editing.value)); documentText.value = JSON.stringify(editing.value.document, null, 2) } catch (e) { error.value = e.message } }
async function save() { await action(async () => { const body = { pinned: editing.value.pinned, locked_fields: editing.value.locked_fields }; for (const key of ['title', 'scope', 'status', 'items']) if (JSON.stringify(editing.value[key]) !== JSON.stringify(original.value[key])) body[key] = editing.value[key]; if (documentText.value !== JSON.stringify(original.value.document, null, 2)) body.document = JSON.parse(documentText.value); await api.adminEditSpecial(editing.value.id, body); await open(editing.value.id) }, '专题已保存') }
async function generate() { await action(async () => { const result = await api.adminGenerateSpecials(); if (!result.accepted) throw new Error('专题任务已在队列或运行中，请到任务页查看进度') }, '任务已提交，可到“任务”查看进度') }
async function regenerate() { await action(async () => { const result = await api.adminRegenerateSpecial(editing.value.id); if (!result.accepted) throw new Error('专题任务已在队列或运行中'); }, '重新生成任务已提交；已锁定的综合内容会跳过，请按需解锁') }
async function merge() { await action(async () => { const result = await api.adminMergeSpecial(editing.value.id, mergeId.value); await open(result.target_id) }, '专题已合并，请重新生成目标专题') }
onMounted(load)
</script>
<style scoped>
.admin-special-input { display: block; width: 100%; margin-top: 6px; padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px; background: white; }
.admin-special-button { padding: 9px 15px; border-radius: 7px; background: #234e22; color: white; font-size: 13px; }
.admin-special-button:disabled { opacity: .5; }
.admin-special-secondary { background: white; border: 1px solid #ddd; color: #234e22; }
button:disabled { opacity: .45; }
</style>
