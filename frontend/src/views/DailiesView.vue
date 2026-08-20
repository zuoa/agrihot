<template>
  <div>
    <div class="flex items-center justify-between mb-5">
      <h1 class="text-xl font-bold text-leaf-800">农业日报</h1>
      <div v-if="adminSession.loggedIn" class="flex items-center gap-2">
        <button @click="generateToday" :disabled="generating"
          class="text-xs px-2.5 py-1 rounded-md border border-dashed border-leaf-300 text-leaf-600 hover:bg-leaf-50 disabled:opacity-50">
          {{ generating ? '生成中…' : '生成今日日报' }}
        </button>
        <span v-if="generateMsg" class="text-xs text-stone-400">{{ generateMsg }}</span>
      </div>
    </div>
    <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else-if="!dailies.length" class="text-center text-stone-400 py-16">暂无日报</div>
    <div v-else class="space-y-3">
      <router-link v-for="d in dailies" :key="d.date" :to="`/dailies/${d.date}`"
        class="flex items-center gap-4 bg-white rounded-xl border border-leaf-100 p-5 hover:border-leaf-300 transition-colors">
        <div class="w-14 h-14 rounded-xl bg-leaf-600 text-white grid place-items-center shrink-0">
          <div class="text-center leading-tight">
            <div class="text-xl font-bold">{{ day(d.date) }}</div>
            <div class="text-[10px]">{{ month(d.date) }}</div>
          </div>
        </div>
        <div class="min-w-0">
          <h2 class="font-bold text-stone-900">{{ d.title }}</h2>
          <p class="text-xs text-stone-400 mt-1">{{ d.highlight_count }} 条要点 · {{ d.item_count }} 条资讯</p>
        </div>
        <span class="ml-auto text-leaf-300">→</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { adminSession, api, fmtDateKey } from '../api'

const dailies = ref([])
const loading = ref(true)
const generating = ref(false)
const generateMsg = ref('')

onMounted(async () => {
  try {
    dailies.value = (await api.dailies({ page_size: 60 })).dailies
  } finally {
    loading.value = false
  }
})

async function generateToday() {
  const today = fmtDateKey(new Date())
  generating.value = true
  generateMsg.value = ''
  try {
    const res = await api.adminGenerateDaily(today)
    generateMsg.value = `已生成：${res.highlight_count} 条要点 · ${res.item_count} 条资讯`
    dailies.value = (await api.dailies({ page_size: 60 })).dailies
  } catch (e) {
    generateMsg.value = e.message
  } finally {
    generating.value = false
  }
}

const day = (iso) => new Date(iso).getDate()
const month = (iso) => `${new Date(iso).getMonth() + 1}月`
</script>
