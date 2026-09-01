<template>
  <div v-if="loading" class="text-sm text-stone-400 py-16 text-center">加载中…</div>
  <form v-else class="space-y-6" @submit.prevent="save">
    <p class="text-sm text-stone-500">改这里立刻影响下一轮文献拉取。保存写入数据库，容器重建也不会丢。</p>

    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold">研究方向</h2>
        <button type="button" class="text-xs text-leaf-700" @click="data.directions.push({ name: '', queries: [] })">+ 方向</button>
      </div>
      <div v-for="(d, i) in data.directions" :key="i" class="bg-white border border-stone-200 rounded-lg p-4 space-y-2">
        <div class="flex gap-2">
          <input v-model="d.name" placeholder="方向名称" required
            class="flex-1 px-3 py-1.5 text-sm rounded-md border border-stone-200" />
          <button type="button" class="text-xs text-red-600" @click="data.directions.splice(i, 1)">删除</button>
        </div>
        <textarea :value="(d.queries || []).join('\n')"
          @input="d.queries = $event.target.value.split('\n').map((s) => s.trim()).filter(Boolean)"
          rows="3" placeholder="检索式，一行一条"
          class="w-full px-3 py-1.5 text-sm rounded-md border border-stone-200 font-mono" />
      </div>
    </section>

    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold">核心期刊</h2>
        <button type="button" class="text-xs text-leaf-700" @click="data.journals.push({ name: '', issn: '' })">+ 期刊</button>
      </div>
      <div class="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-xs text-stone-500">
            <tr>
              <th class="text-left font-medium px-3 py-2">刊名</th>
              <th class="text-left font-medium px-3 py-2">ISSN</th>
              <th class="w-16"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(j, i) in data.journals" :key="i" class="border-t border-stone-100">
              <td class="px-3 py-1.5"><input v-model="j.name" class="w-full px-2 py-1 rounded border border-stone-200" /></td>
              <td class="px-3 py-1.5"><input v-model="j.issn" required class="w-full px-2 py-1 rounded border border-stone-200 font-mono" /></td>
              <td class="px-3 py-1.5 text-right"><button type="button" class="text-xs text-red-600" @click="data.journals.splice(i, 1)">删</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold">学者</h2>
        <button type="button" class="text-xs text-leaf-700" @click="data.authors.push({ name: '', openalex_id: '' })">+ 学者</button>
      </div>
      <div class="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-xs text-stone-500">
            <tr>
              <th class="text-left font-medium px-3 py-2">姓名</th>
              <th class="text-left font-medium px-3 py-2">OpenAlex ID</th>
              <th class="w-16"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!data.authors.length"><td colspan="3" class="px-3 py-3 text-xs text-stone-400">暂无。有明确跟踪对象再填 A… ID。</td></tr>
            <tr v-for="(a, i) in data.authors" :key="i" class="border-t border-stone-100">
              <td class="px-3 py-1.5"><input v-model="a.name" class="w-full px-2 py-1 rounded border border-stone-200" /></td>
              <td class="px-3 py-1.5"><input v-model="a.openalex_id" class="w-full px-2 py-1 rounded border border-stone-200 font-mono" /></td>
              <td class="px-3 py-1.5 text-right"><button type="button" class="text-xs text-red-600" @click="data.authors.splice(i, 1)">删</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="space-y-2">
      <h2 class="text-sm font-bold">预筛词</h2>
      <textarea :value="(data.prescreen || []).join('\n')"
        @input="data.prescreen = $event.target.value.split('\n').map((s) => s.trim()).filter(Boolean)"
        rows="8" class="w-full px-3 py-2 text-sm rounded-lg border border-stone-200 font-mono bg-white" />
      <p class="text-[11px] text-stone-400">方向检索 / 学者订阅命中任一即可；核心期刊不过这道闸。</p>
    </section>

    <p v-if="msg" class="text-xs" :class="ok ? 'text-leaf-700' : 'text-red-600'">{{ msg }}</p>
    <button type="submit" :disabled="saving"
      class="px-4 py-2 text-sm rounded-lg bg-leaf-700 text-white hover:bg-leaf-800 disabled:opacity-50">
      {{ saving ? '保存中…' : '保存关注面' }}
    </button>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../api'

const loading = ref(true)
const saving = ref(false)
const msg = ref('')
const ok = ref(false)
const data = reactive({
  directions: [],
  journals: [],
  authors: [],
  prescreen: [],
})

onMounted(async () => {
  try {
    const w = await api.adminWatchlist()
    data.directions = w.directions || []
    data.journals = w.journals || []
    data.authors = w.authors || []
    data.prescreen = w.prescreen || []
  } catch (e) {
    msg.value = e.message
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  msg.value = ''
  try {
    const saved = await api.adminPutWatchlist({
      directions: data.directions,
      journals: data.journals,
      authors: data.authors,
      prescreen: data.prescreen,
    })
    data.directions = saved.directions
    data.journals = saved.journals
    data.authors = saved.authors
    data.prescreen = saved.prescreen
    ok.value = true
    msg.value = '已保存'
  } catch (e) {
    ok.value = false
    msg.value = e.message
  } finally {
    saving.value = false
  }
}
</script>
