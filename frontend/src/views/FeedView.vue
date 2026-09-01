<template>
  <div>
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <h1 class="text-xl font-bold text-leaf-800">全部动态</h1>
      <input v-model="q" @keyup.enter="search" placeholder="搜索标题 / 摘要…"
        class="px-3 py-1.5 text-sm rounded-full border border-leaf-200 bg-white focus:outline-none focus:border-leaf-500 w-56" />
    </div>

    <div class="flex gap-2 overflow-x-auto pb-1"
      :class="category === '论文' && directions.length ? 'mb-3' : 'mb-5'">
      <button v-for="c in categories" :key="c" @click="pickCategory(c)"
        class="px-3.5 py-1.5 text-sm rounded-full border whitespace-nowrap transition-colors"
        :class="(category || '全部') === c
          ? 'bg-leaf-600 text-white border-leaf-600'
          : 'bg-white text-stone-600 border-leaf-200 hover:border-leaf-400'">
        {{ c }}
      </button>
    </div>
    <div v-if="category === '论文' && directions.length" class="flex gap-2 mb-5 overflow-x-auto pb-1">
      <button v-for="d in [{ name: '全部方向', count: 0 }, ...directions]" :key="d.name"
        @click="pickDirection(d.name === '全部方向' ? '' : d.name)"
        class="px-3 py-1 text-xs rounded-full border whitespace-nowrap transition-colors"
        :class="(direction || '全部方向') === d.name || (!direction && d.name === '全部方向')
          ? 'bg-leaf-700 text-white border-leaf-700'
          : 'bg-white text-stone-500 border-leaf-200 hover:border-leaf-400'">
        {{ d.name }}<span v-if="d.count" class="ml-1 tabular-nums opacity-70">{{ d.count }}</span>
      </button>
    </div>

    <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
    <template v-else>
      <section v-for="g in groups" :key="g.key" class="mb-8">
        <div class="flex items-baseline gap-3 mb-3">
          <h2 class="text-lg font-bold text-leaf-800">{{ g.label }}</h2>
          <span class="text-xs text-stone-400">{{ g.items.length }} 条</span>
          <div class="flex-1 border-t border-leaf-100"></div>
        </div>
        <div class="space-y-3">
          <ItemCard v-for="it in g.items" :key="it.id" :item="it"
            @updated="load(page)" @deleted="load(page)" />
        </div>
      </section>
      <div v-if="!groups.length" class="text-center text-stone-400 py-16">暂无内容</div>

      <div class="flex justify-center gap-3 mt-6" v-if="totalPages > 1">
        <button :disabled="page <= 1" @click="load(page - 1)"
          class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white disabled:opacity-40 hover:border-leaf-400">上一页</button>
        <span class="text-sm text-stone-500 self-center">{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="load(page + 1)"
          class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white disabled:opacity-40 hover:border-leaf-400">下一页</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, groupByDay } from '../api'
import ItemCard from '../components/ItemCard.vue'

const CATEGORIES = ['政策', '报道', '论文', '行业']
const categories = ['全部', ...CATEGORIES]
const route = useRoute()
const router = useRouter()
const category = ref('')
const direction = ref('')
const directions = ref([])
const q = ref('')
const page = ref(1)
const total = ref(0)
const pageSize = 20
const items = ref([])
const loading = ref(true)

watch(
  () => [route.query.category, route.query.direction],
  async ([c, d]) => {
    category.value = CATEGORIES.includes(c) ? c : ''
    direction.value = category.value === '论文' && d ? String(d) : ''
    if (category.value === '论文') {
      try { directions.value = await api.paperDirections() } catch { directions.value = [] }
    } else {
      directions.value = []
    }
    load(1)
  },
  { immediate: true },
)

function pickCategory(c) {
  const query = { ...route.query }
  if (c === '全部') delete query.category
  else query.category = c
  delete query.direction
  router.replace({ query })
}

function pickDirection(name) {
  const query = { ...route.query, category: '论文' }
  if (!name) delete query.direction
  else query.direction = name
  router.replace({ query })
}

function search() { load(1) }

async function load(p) {
  loading.value = true
  page.value = p
  try {
    const data = await api.items({
      mode: 'all',
      category: category.value,
      direction: direction.value,
      q: q.value,
      page: p,
      page_size: pageSize,
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const groups = computed(() => groupByDay(items.value))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
</script>
