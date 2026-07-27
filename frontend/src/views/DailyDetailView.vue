<template>
  <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
  <div v-else-if="!daily" class="text-center text-stone-400 py-16">该日期暂无日报</div>
  <div v-else>
    <header class="mb-6">
      <div class="text-sm text-leaf-600 font-medium mb-1">{{ dateLabel }}</div>
      <h1 class="text-2xl font-bold text-stone-900">{{ daily.title }}</h1>
      <p class="text-sm text-stone-400 mt-2">{{ daily.content.replace(/[*-]/g, '').slice(0, 120) }}</p>
    </header>

    <!-- 今日要点 -->
    <section class="rounded-2xl bg-gradient-to-br from-leaf-50 to-white border border-leaf-200 p-5 sm:p-6 mb-8">
      <h2 class="font-bold text-leaf-800 mb-4 flex items-center gap-2">
        <span class="w-6 h-6 rounded-md bg-leaf-600 text-white grid place-items-center text-xs">要</span>今日要点
      </h2>
      <ol class="space-y-3">
        <li v-for="(h, i) in daily.highlights" :key="i" class="flex gap-3 text-sm leading-6">
          <span class="w-5 h-5 rounded-full bg-leaf-100 text-leaf-700 text-xs font-bold grid place-items-center shrink-0 mt-0.5">{{ i + 1 }}</span>
          <span class="text-stone-700">{{ h }}</span>
        </li>
      </ol>
    </section>

    <!-- 分节展示 -->
    <section v-for="sec in sections" :key="sec.name" class="mb-8">
      <div class="flex items-baseline gap-3 mb-3">
        <h2 class="text-lg font-bold text-leaf-800">{{ sec.name }}</h2>
        <span class="text-xs text-stone-400">{{ sec.items.length }} 条</span>
        <div class="flex-1 border-t border-leaf-100"></div>
      </div>
      <div class="space-y-3">
        <ItemCard v-for="it in sec.items" :key="it.id" :item="it" @updated="load" @deleted="load" />
      </div>
    </section>

    <p class="text-xs text-stone-400 border-t border-leaf-100 pt-4 leading-5">
      本日报内容整理自公开来源，外文资料已译为中文，翻译与摘要仅供参考；引用与决策请以官方原文与正式出版物为准。
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, fmtDay } from '../api'
import ItemCard from '../components/ItemCard.vue'

const route = useRoute()
const daily = ref(null)
const loading = ref(true)

watch(() => route.params.date, load, { immediate: true })
onMounted(() => {})

async function load() {
  loading.value = true
  daily.value = null
  try {
    daily.value = await api.daily(route.params.date)
  } catch {
    daily.value = null
  } finally {
    loading.value = false
  }
}

const dateLabel = computed(() => (daily.value ? fmtDay(daily.value.date) : ''))

const sections = computed(() => {
  if (!daily.value) return []
  const defs = [
    { name: '一、政策', cats: ['政策'] },
    { name: '二、报道', cats: ['报道'] },
    { name: '三、学术论文', cats: ['论文'] },
    { name: '四、行业动态', cats: ['行业'] },
  ]
  return defs
    .map((d) => ({ name: d.name, items: daily.value.items.filter((i) => d.cats.includes(i.category)) }))
    .filter((s) => s.items.length)
})
</script>
