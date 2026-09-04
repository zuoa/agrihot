<template>
  <div>
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <h1 class="text-xl font-bold text-leaf-800">{{ heading }}</h1>
      <input v-model="q" @keyup.enter="search" placeholder="搜索标题 / 摘要…"
        class="px-3 py-1.5 text-sm rounded-full border border-leaf-200 bg-white focus:outline-none focus:border-leaf-500 w-56" />
    </div>

    <div class="flex gap-2 overflow-x-auto pb-1"
      :class="category === '论文' && directions.length ? 'mb-3' : 'mb-5'">
      <router-link v-for="c in categories" :key="c" :to="categoryLink(c)"
        class="px-3.5 py-1.5 text-sm rounded-full border whitespace-nowrap transition-colors"
        :class="(category || '全部') === c
          ? 'bg-leaf-600 text-white border-leaf-600'
          : 'bg-white text-stone-600 border-leaf-200 hover:border-leaf-400'">
        {{ c }}
      </router-link>
    </div>
    <div v-if="category === '论文' && directions.length" class="flex gap-2 mb-5 overflow-x-auto pb-1">
      <router-link v-for="d in [{ name: '全部方向', count: 0 }, ...directions]" :key="d.name"
        :to="directionLink(d.name === '全部方向' ? '' : d.name)"
        class="px-3 py-1 text-xs rounded-full border whitespace-nowrap transition-colors"
        :class="(direction || '全部方向') === d.name || (!direction && d.name === '全部方向')
          ? 'bg-leaf-700 text-white border-leaf-700'
          : 'bg-white text-stone-500 border-leaf-200 hover:border-leaf-400'">
        {{ d.name }}<span v-if="d.count" class="ml-1 tabular-nums opacity-70">{{ d.count }}</span>
      </router-link>
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
        <router-link v-if="page > 1" :to="pageLink(page - 1)"
          class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white hover:border-leaf-400">上一页</router-link>
        <span v-else class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white opacity-40">上一页</span>
        <span class="text-sm text-stone-500 self-center">{{ page }} / {{ totalPages }}</span>
        <router-link v-if="page < totalPages" :to="pageLink(page + 1)"
          class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white hover:border-leaf-400">下一页</router-link>
        <span v-else class="px-4 py-1.5 text-sm rounded-full border border-leaf-200 bg-white opacity-40">下一页</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, groupByDay } from '../api'
import ItemCard from '../components/ItemCard.vue'
import { setPageMeta } from '../seo'

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
const heading = computed(() => {
  const bits = ['全部动态']
  if (category.value) bits.push(category.value)
  if (category.value === '论文' && direction.value) bits.push(direction.value)
  return bits.join(' · ')
})

watch(
  () => [route.query.category, route.query.direction, route.query.q, route.query.page],
  async ([c, d, queryQ, queryPage]) => {
    category.value = CATEGORIES.includes(c) ? c : ''
    direction.value = category.value === '论文' && d ? String(d) : ''
    q.value = queryQ ? String(queryQ) : ''
    if (category.value === '论文') {
      try { directions.value = await api.paperDirections() } catch { directions.value = [] }
    } else {
      directions.value = []
    }
    const p = Math.max(1, parseInt(queryPage, 10) || 1)
    await load(p)
  },
  { immediate: true },
)

function categoryLink(c) {
  const query = {}
  if (c !== '全部') query.category = c
  if (q.value.trim()) query.q = q.value.trim()
  return { path: '/feed', query }
}

function directionLink(name) {
  const query = { category: '论文' }
  if (name) query.direction = name
  if (q.value.trim()) query.q = q.value.trim()
  return { path: '/feed', query }
}

function pageLink(p) {
  const query = { ...route.query }
  if (p <= 1) delete query.page
  else query.page = String(p)
  return { path: '/feed', query }
}

function search() {
  const query = { ...route.query }
  const trimmed = q.value.trim()
  if (trimmed) query.q = trimmed
  else delete query.q
  delete query.page
  router.replace({ path: '/feed', query })
}

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
  setPageMeta({
    title: `${heading.value} · AgriHot`,
    description: q.value
      ? `搜索「${q.value}」的农业信息化资讯`
      : `${heading.value}：政策、报道、学术论文与行业动态。`,
    path: route.fullPath,
    noindex: Boolean(q.value),
  })
}

const groups = computed(() => groupByDay(items.value))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
</script>
