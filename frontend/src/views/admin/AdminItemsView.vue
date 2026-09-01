<template>
  <div class="space-y-4">
    <form class="bg-white border border-stone-200 rounded-lg p-3 grid sm:grid-cols-4 gap-2 text-sm" @submit.prevent="applyFilters">
      <input v-model="form.q" placeholder="搜索标题 / 摘要"
        class="px-3 py-1.5 rounded-md border border-stone-200 focus:outline-none focus:border-leaf-500 sm:col-span-2" />
      <select v-model="form.category" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="">全部分类</option>
        <option v-for="c in ['政策', '报道', '论文', '行业']" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="form.has_content" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="">全文不限</option>
        <option value="true">有全文</option>
        <option value="false">无全文</option>
      </select>
      <select v-model="form.scored" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="">评分不限</option>
        <option value="true">已评分</option>
        <option value="false">未评分</option>
      </select>
      <select v-model="form.is_selected" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="">精选不限</option>
        <option value="true">精选</option>
        <option value="false">非精选</option>
      </select>
      <select v-model="form.ingested_from" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="">来源不限</option>
        <option value="agent">Agent / 新闻</option>
        <option value="openalex">OpenAlex</option>
      </select>
      <select v-model="form.sort" class="px-3 py-1.5 rounded-md border border-stone-200 bg-white">
        <option value="created_at">按入库时间</option>
        <option value="score">按评分</option>
        <option value="view_count">按阅读</option>
      </select>
      <button type="submit" class="px-3 py-1.5 rounded-md bg-leaf-700 text-white text-sm hover:bg-leaf-800">筛选</button>
    </form>

    <div class="flex items-center justify-between text-xs text-stone-500">
      <span>共 {{ total }} 条 · 已选 {{ selected.length }}</span>
      <div class="flex gap-2">
        <button :disabled="!selected.length || busy" @click="batchFetch(false)"
          class="px-2.5 py-1 rounded-md border border-stone-200 hover:bg-white disabled:opacity-40">批量抓全文</button>
        <button :disabled="!selected.length || busy" @click="batchDelete"
          class="px-2.5 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-40">批量删除</button>
      </div>
    </div>
    <p v-if="msg" class="text-xs text-stone-500">{{ msg }}</p>

    <div class="bg-white border border-stone-200 rounded-lg overflow-x-auto">
      <table class="w-full text-sm min-w-[720px]">
        <thead class="bg-stone-50 text-xs text-stone-500">
          <tr>
            <th class="px-3 py-2 w-8"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
            <th class="text-left font-medium px-3 py-2">标题</th>
            <th class="text-left font-medium px-3 py-2">分类</th>
            <th class="text-left font-medium px-3 py-2">评分</th>
            <th class="text-left font-medium px-3 py-2">全文</th>
            <th class="text-left font-medium px-3 py-2">精选</th>
            <th class="text-right font-medium px-3 py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="px-3 py-10 text-center text-stone-400">加载中…</td></tr>
          <tr v-else-if="!items.length"><td colspan="7" class="px-3 py-10 text-center text-stone-400">没有匹配的条目</td></tr>
          <tr v-for="it in items" :key="it.id" class="border-t border-stone-100 align-top">
            <td class="px-3 py-2"><input type="checkbox" :value="it.id" v-model="selected" /></td>
            <td class="px-3 py-2">
              <router-link :to="`/items/${it.id}`" class="font-medium text-stone-900 hover:text-leaf-700 line-clamp-2">{{ it.title }}</router-link>
              <div class="text-[11px] text-stone-400 mt-0.5">{{ it.source_name }} · {{ fmtDate(it.created_at) }}</div>
            </td>
            <td class="px-3 py-2 text-xs text-stone-500">{{ it.category }}</td>
            <td class="px-3 py-2 tabular-nums">{{ it.score == null ? '—' : it.score }}</td>
            <td class="px-3 py-2 text-xs">{{ it.content ? '有' : '无' }}</td>
            <td class="px-3 py-2 text-xs">{{ it.is_selected ? '是' : '' }}</td>
            <td class="px-3 py-2">
              <div class="flex flex-wrap gap-1 justify-end">
                <button class="text-xs px-2 py-0.5 rounded border border-stone-200 hover:bg-stone-50" @click="edit = it">编辑</button>
                <button class="text-xs px-2 py-0.5 rounded border border-stone-200 hover:bg-stone-50" :disabled="busy" @click="fetchOne(it)">抓全文</button>
                <button class="text-xs px-2 py-0.5 rounded border border-stone-200 hover:bg-stone-50" :disabled="busy" @click="rescore(it)">重评</button>
                <button class="text-xs px-2 py-0.5 rounded border border-red-200 text-red-600 hover:bg-red-50" :disabled="busy" @click="remove(it)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="pages > 1" class="flex justify-center gap-2 text-sm">
      <button :disabled="page <= 1" @click="go(page - 1)" class="px-3 py-1 rounded border border-stone-200 disabled:opacity-40">上一页</button>
      <span class="px-2 py-1 text-stone-500">{{ page }} / {{ pages }}</span>
      <button :disabled="page >= pages" @click="go(page + 1)" class="px-3 py-1 rounded border border-stone-200 disabled:opacity-40">下一页</button>
    </div>

    <ItemEditModal v-if="edit" :item="edit" @close="edit = null" @saved="onSaved" />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../api'
import ItemEditModal from '../../components/ItemEditModal.vue'

const route = useRoute()
const router = useRouter()
const items = ref([])
const total = ref(0)
const loading = ref(true)
const busy = ref(false)
const msg = ref('')
const selected = ref([])
const edit = ref(null)
const pageSize = 20

const form = reactive({
  q: '',
  category: '',
  has_content: '',
  scored: '',
  is_selected: '',
  ingested_from: '',
  sort: 'created_at',
})

const page = computed(() => Math.max(1, Number(route.query.page) || 1))
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const allChecked = computed(() => items.value.length > 0 && items.value.every((it) => selected.value.includes(it.id)))

function syncFormFromQuery() {
  form.q = route.query.q || ''
  form.category = route.query.category || ''
  form.has_content = route.query.has_content || ''
  form.scored = route.query.scored || ''
  form.is_selected = route.query.is_selected || ''
  form.ingested_from = route.query.ingested_from || ''
  form.sort = route.query.sort || 'created_at'
}

function queryPayload(extra = {}) {
  const q = { page: page.value, page_size: pageSize, sort: form.sort, ...extra }
  for (const k of ['q', 'category', 'has_content', 'scored', 'is_selected', 'ingested_from']) {
    if (form[k] !== '') q[k] = form[k]
  }
  return q
}

async function load() {
  loading.value = true
  msg.value = ''
  try {
    const res = await api.adminItems(queryPayload())
    items.value = res.items
    total.value = res.total
    selected.value = selected.value.filter((id) => items.value.some((it) => it.id === id))
  } catch (e) {
    msg.value = e.message
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  const query = { ...form }
  Object.keys(query).forEach((k) => { if (!query[k]) delete query[k] })
  router.push({ name: 'admin-items', query })
}

function go(p) {
  router.push({ name: 'admin-items', query: { ...route.query, page: p } })
}

function toggleAll(ev) {
  selected.value = ev.target.checked ? items.value.map((it) => it.id) : []
}

watch(() => route.query, () => {
  syncFormFromQuery()
  load()
}, { immediate: true })

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function onSaved(updated) {
  const i = items.value.findIndex((x) => x.id === updated.id)
  if (i >= 0) items.value[i] = updated
}

async function fetchOne(it) {
  if (it.content && !confirm('已有全文，重新抓取将覆盖。继续？')) return
  busy.value = true
  try {
    const updated = await api.adminFetchContent(it.id)
    onSaved(updated)
  } catch (e) {
    alert(e.message)
  } finally {
    busy.value = false
  }
}

async function rescore(it) {
  busy.value = true
  try {
    onSaved(await api.adminRescoreItem(it.id))
  } catch (e) {
    alert(e.message)
  } finally {
    busy.value = false
  }
}

async function remove(it) {
  if (!confirm(`确定删除「${it.title.slice(0, 30)}」？不可恢复。`)) return
  busy.value = true
  try {
    await api.adminDeleteItem(it.id)
    await load()
  } catch (e) {
    alert(e.message)
  } finally {
    busy.value = false
  }
}

async function batchDelete() {
  if (!confirm(`确定删除选中的 ${selected.value.length} 条？不可恢复。`)) return
  busy.value = true
  try {
    const res = await api.adminBatchDelete(selected.value)
    msg.value = `已删除 ${res.deleted.length} 条` + (res.missing.length ? `，${res.missing.length} 条不存在` : '')
    selected.value = []
    await load()
  } catch (e) {
    alert(e.message)
  } finally {
    busy.value = false
  }
}

async function batchFetch(force) {
  busy.value = true
  try {
    await api.adminBatchFetch(selected.value, force)
    msg.value = '已开始后台抓取，稍后刷新查看结果'
    selected.value = []
  } catch (e) {
    alert(e.message)
  } finally {
    busy.value = false
  }
}
</script>
