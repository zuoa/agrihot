<template>
  <div>
    <header class="mb-7 border-b border-leaf-200 pb-6">
      <div class="flex items-center justify-between gap-3 text-xs text-stone-500 mb-3">
        <span class="tracking-widest text-leaf-700">AGRIHOT · 主题索引</span>
        <NuxtLink to="/tags" class="hover:text-leaf-700 underline underline-offset-4">查找全部标签</NuxtLink>
      </div>
      <h1 class="text-3xl font-bold text-leaf-900 tracking-tight">从领域出发，读懂农业新进展</h1>
      <p class="mt-3 text-sm leading-7 text-stone-500">沿着产业、技术与乡村发展的脉络，浏览政策、动态和研究。</p>
      <label class="block mt-5">
        <span class="sr-only">查找主题</span>
        <input v-model="query" type="search" placeholder="查找主题，如水稻、遥感、种业…"
          class="w-full rounded-lg border border-leaf-200 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-leaf-500" />
      </label>
    </header>

    <div v-if="pending" class="py-16 text-center text-stone-500" role="status">正在整理主题…</div>
    <div v-else-if="error" class="py-12 text-center text-stone-500" role="alert">
      <p>主题暂时加载失败，请稍后重试。</p>
      <button class="mt-4 text-leaf-700 underline" @click="refresh">重新加载</button>
    </div>
    <div v-else-if="!topics.length" class="py-12 text-center text-stone-500">
      <p>{{ query ? '没有找到这个主题，换个词试试。' : '主题目录正在准备中。' }}</p>
      <button v-if="query" class="mt-3 text-leaf-700 underline" @click="query = ''">查看全部主题</button>
    </div>
    <div v-else class="grid sm:grid-cols-2 gap-4">
      <section v-for="topic in topics" :key="topic.code" class="topic-branch bg-white rounded-xl border border-leaf-200 p-5">
        <NuxtLink :to="topic.path" class="group flex items-start justify-between gap-3 focus-visible:outline-leaf-600">
          <div>
            <h2 class="text-lg font-bold text-leaf-900 group-hover:text-leaf-600">{{ topic.name }}</h2>
            <p class="text-xs text-stone-500 leading-6 mt-1">{{ shortDescription(topic) }}</p>
          </div>
          <span class="text-xs text-leaf-700 tabular-nums shrink-0 mt-1">{{ topic.count }} 篇 <span aria-hidden="true">↗</span></span>
        </NuxtLink>
        <div class="mt-4 border-l-2 border-leaf-100 pl-3 space-y-1">
          <NuxtLink v-for="child in featured(topic)" :key="child.code" :to="child.path"
            class="flex justify-between gap-3 py-1.5 text-sm text-stone-600 hover:text-leaf-700">
            <span>{{ child.name }}</span><span class="text-xs text-stone-400 tabular-nums self-center">{{ child.count }}</span>
          </NuxtLink>
        </div>
        <NuxtLink :to="topic.path" class="inline-block mt-3 text-xs text-leaf-700 hover:underline">查看全部 {{ topic.children.length }} 个方向 →</NuxtLink>
      </section>
    </div>
  </div>
</template>

<script setup>
const api = useApi()
const query = ref('')
const { data, pending, error, refresh } = await useAsyncData('taxonomy', () => api.taxonomy())
const topics = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (data.value?.topics || []).filter(t => !q || [t.name, t.description, ...t.children.map(c => c.name)].some(s => s.toLowerCase().includes(q)))
})
function featured(topic) {
  const children = [...topic.children].sort((a, b) => b.count - a.count)
  const q = query.value.trim().toLowerCase()
  return (q && children.some(c => c.name.toLowerCase().includes(q)) ? children.filter(c => c.name.toLowerCase().includes(q)) : children).slice(0, 3)
}
function shortDescription(topic) {
  return [...topic.children].sort((a, b) => b.count - a.count).slice(0, 3).map(c => c.name).join(' · ')
}
usePageSeo({ title: '主题索引 · AgriHot', description: '按农业产业、数字技术、资源环境与乡村发展浏览政策、动态和研究。', path: '/topic' })
</script>

<style scoped>
.topic-branch { border-top: 3px solid #96ce8b; }
.topic-branch:hover { border-top-color: #327a2d; }
</style>
