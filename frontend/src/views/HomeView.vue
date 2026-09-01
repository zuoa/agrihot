<template>
  <div>
    <!-- 今日热点 TOP 1 -->
    <section v-if="topItem" class="mb-6">
      <router-link :to="`/items/${topItem.id}`"
        class="block rounded-2xl bg-gradient-to-br from-leaf-700 to-leaf-900 text-white p-6 sm:p-8 shadow-lg shadow-leaf-200 hover:from-leaf-600 hover:to-leaf-800 transition-all">
        <div class="flex items-center gap-2 text-xs text-leaf-200 mb-3">
          <span class="px-2 py-0.5 rounded-full bg-white/15 font-medium">今日热点 TOP 1</span>
          <span>{{ topItem.source_name }}</span>
          <span v-if="topItem.sources?.length > 1">· {{ topItem.sources.length }} 个信源同时报道</span>
        </div>
        <h1 class="text-xl sm:text-2xl font-bold leading-snug">{{ topItem.title }}</h1>
        <p class="mt-3 text-sm text-leaf-100 leading-6 line-clamp-2">{{ topItem.summary_zh || topItem.summary }}</p>
      </router-link>
    </section>

    <!-- 分类过滤 -->
    <div class="flex gap-2 mb-5 overflow-x-auto pb-1">
      <button v-for="c in categories" :key="c" @click="category = c === '全部' ? '' : c"
        class="px-3.5 py-1.5 text-sm rounded-full border whitespace-nowrap transition-colors"
        :class="(category || '全部') === c
          ? 'bg-leaf-600 text-white border-leaf-600'
          : 'bg-white text-stone-600 border-leaf-200 hover:border-leaf-400'">
        {{ c }}
      </button>
    </div>

    <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else-if="!groups.length" class="text-center text-stone-400 py-16">暂无内容</div>

    <!-- 按日期分组 -->
    <section v-for="g in groups" :key="g.key" class="mb-8">
      <div class="flex items-baseline gap-3 mb-3">
        <h2 class="text-lg font-bold text-leaf-800">{{ g.label }}</h2>
        <span class="text-xs text-stone-400">{{ g.items.length }} 条</span>
        <div class="flex-1 border-t border-leaf-100"></div>
      </div>
      <div class="space-y-3">
        <ItemCard v-for="it in g.items" :key="it.id" :item="it" @updated="load" @deleted="load" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api, groupByDay } from '../api'
import ItemCard from '../components/ItemCard.vue'

const categories = ['全部', '政策', '报道', '论文', '行业']
const category = ref('')
const items = ref([])
const loading = ref(true)

watch(category, load, { immediate: true })

async function load() {
  loading.value = true
  try {
    const data = await api.items({ mode: 'selected', category: category.value, page_size: 100 })
    items.value = data.items
  } finally {
    loading.value = false
  }
}

const topItem = computed(() => {
  if (category.value || !items.value.length) return null
  return [...items.value].sort((a, b) => b.hotness - a.hotness)[0]
})

const groups = computed(() => {
  const rest = topItem.value ? items.value.filter((i) => i.id !== topItem.value.id) : items.value
  return groupByDay(rest)
})
</script>
