<template>
  <div class="space-y-5">
    <section class="rounded-xl border border-stone-200 bg-white p-5">
      <div class="flex flex-wrap items-center justify-between gap-3"><h2 class="font-bold">召回索引</h2><div class="flex gap-3 text-xs"><button class="text-leaf-700 hover:underline disabled:opacity-50" :disabled="busy" @click="load">刷新状态</button><button class="rounded border border-leaf-200 px-3 py-1.5 text-leaf-700 hover:bg-leaf-50 disabled:opacity-50" :disabled="busy" @click="backfill">补建 / 重试索引</button></div></div>
      <template v-if="index">
        <p class="mt-3 text-sm text-stone-600">{{ index.model }} · {{ index.dimensions }} 维 · {{ index.enabled ? '后台索引已开启' : '后台索引已暂停' }}</p>
        <p v-if="!index.configured" class="mt-2 text-sm text-amber-800">未配置 EMBEDDING_API_KEY，语义召回未启用，查询使用关键词检索。</p>
        <div class="mt-4 grid grid-cols-3 gap-3 text-sm"><div class="rounded-lg bg-stone-50 p-3"><p class="text-xs text-stone-500">已完成 / 总量</p><p class="mt-1 font-bold text-leaf-800">{{ index.indexed }} / {{ index.total }}</p></div><div class="rounded-lg bg-stone-50 p-3"><p class="text-xs text-stone-500">覆盖率</p><p class="mt-1 font-bold text-leaf-800">{{ Math.round(index.coverage * 100) }}%</p></div><div class="rounded-lg bg-stone-50 p-3"><p class="text-xs text-stone-500">待完成</p><p class="mt-1 font-bold text-leaf-800">{{ index.pending }}</p></div></div>
        <ul v-if="index.errors.length" class="mt-3 space-y-1 text-xs text-amber-800"><li v-for="entry in index.errors" :key="entry.item_id">条目 #{{ entry.item_id }}：{{ entry.error }}（后台自动重试）</li></ul>
      </template>
    </section>

    <section class="rounded-xl border border-stone-200 bg-white p-5">
      <div class="flex items-center justify-between"><h2 class="font-bold">读取 Key 申请</h2><NuxtLink to="/admin/keys" class="text-xs text-leaf-700 hover:underline">管理已签发 Key ↗</NuxtLink></div>
      <p class="mt-2 text-xs text-stone-500">审批通过后，复制新 Key 并通过申请人的联系方式人工交付。</p>
      <div v-if="created" class="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
        <h3 class="font-medium text-amber-900">{{ created.name }} 的读取 Key（明文仅显示一次）</h3>
        <p class="mt-1 text-xs text-amber-800">交付给：{{ created.contact }}</p>
        <code class="mt-2 block break-all rounded border border-amber-100 bg-white p-2 text-xs">{{ created.key }}</code>
        <button class="mt-2 text-xs text-amber-800 hover:underline" @click="copy">复制 Key</button>
        <button class="ml-4 text-xs text-stone-500 hover:underline" @click="created = null">已保存，关闭</button>
      </div>
      <p v-if="loading" class="py-8 text-sm text-stone-400">加载中…</p>
      <p v-else-if="!applications.length" class="py-8 text-center text-sm text-stone-400">暂无接入申请。</p>
      <article v-for="application in applications" :key="application.id" class="mt-4 border-t border-stone-100 pt-4">
        <div class="flex flex-wrap items-center justify-between gap-2"><h3 class="text-sm font-bold">#{{ application.id }} {{ application.name }}</h3><span class="text-xs" :class="application.status === 'pending' ? 'text-amber-700' : 'text-stone-500'">{{ labels[application.status] }}</span></div>
        <p class="mt-1 text-xs text-stone-500 break-all">{{ application.contact }}</p><p class="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-stone-600">{{ application.use_case }}</p>
        <p v-if="application.note" class="mt-2 text-xs text-stone-500">处理备注：{{ application.note }}</p>
        <div v-if="application.status === 'pending'" class="mt-3 flex flex-wrap gap-2">
          <input v-model="notes[application.id]" :aria-label="`申请 ${application.id} 的处理备注`" placeholder="处理备注（选填）" maxlength="500" class="min-w-0 flex-1 rounded border border-stone-200 px-3 py-1.5 text-xs" />
          <button :disabled="busy || !!created" class="rounded bg-leaf-700 px-3 py-1.5 text-xs text-white hover:bg-leaf-800 disabled:opacity-50" @click="review(application, 'approve')">批准并签发</button>
          <button :disabled="busy" class="rounded border border-stone-200 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-50 disabled:opacity-50" @click="review(application, 'reject')">拒绝申请</button>
        </div>
      </article>
      <div class="mt-4 flex items-center justify-end gap-4 text-xs"><button v-if="page > 1" :disabled="busy" class="text-leaf-700" @click="changePage(-1)">上一页</button><span class="text-stone-400">第 {{ page }} 页</span><button v-if="hasMore" :disabled="busy" class="text-leaf-700" @click="changePage(1)">下一页</button></div>
    </section>
    <p v-if="message" role="status" class="text-sm text-leaf-800">{{ message }}</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
  </div>
</template>

<script setup>
definePageMeta({ layout: 'admin', title: 'Agent 读取接入', middleware: 'admin-auth' })
useHead({ meta: [{ name: 'robots', content: 'noindex, nofollow' }] })
const api = useApi()
const index = ref(null), applications = ref([]), loading = ref(true), busy = ref(false), created = ref(null), page = ref(1), hasMore = ref(false), message = ref(''), error = ref('')
const notes = reactive({}), labels = { pending: '待审核', approved: '已批准', rejected: '已拒绝' }
onMounted(load)
async function load() {
  loading.value = true; error.value = ''
  try {
    const [status, result] = await Promise.all([api.adminAgentIndex(), api.adminAgentApplications(page.value)])
    index.value = status; applications.value = result.applications; hasMore.value = result.has_more
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}
async function review(application, decision) {
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.adminAgentReview(application.id, decision, notes[application.id] || '')
    if (result.key) created.value = { key: result.key, name: application.name, contact: application.contact }
    await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function backfill() {
  busy.value = true; error.value = ''
  try { const result = await api.adminAgentBackfill(); message.value = `已提交 ${result.queued} 条索引任务，后台会自动处理。`; await load() }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function changePage(delta) { page.value += delta; await load() }
async function copy() {
  try { await navigator.clipboard.writeText(created.value.key); message.value = '读取 Key 已复制，请妥善交付。' }
  catch { error.value = '复制失败，请手动选中 Key 复制。' }
}
</script>
