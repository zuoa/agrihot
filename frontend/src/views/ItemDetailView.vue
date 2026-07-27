<template>
  <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
  <div v-else-if="!item" class="text-center text-stone-400 py-16">条目不存在</div>
  <article v-else class="bg-white rounded-2xl border border-leaf-100 p-6 sm:p-8">
    <div class="flex items-center gap-2 text-xs text-stone-400 flex-wrap mb-3">
      <span class="text-leaf-700 font-medium">{{ item.source_name || '未知来源' }}</span>
      <span>·</span>
      <span>{{ dateLabel }}</span>
      <span class="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">{{ item.category }}</span>
      <span v-if="item.is_selected" class="px-1.5 py-0.5 rounded bg-leaf-100 text-leaf-700 font-medium">精选</span>
      <span class="text-amber-600" v-if="item.hotness >= 60">🔥 {{ item.hotness }}</span>
    </div>

    <h1 class="text-xl sm:text-2xl font-bold text-stone-900 leading-snug">{{ item.title }}</h1>

    <div class="mt-5 rounded-xl bg-leaf-50 border border-leaf-100 p-4">
      <div class="text-xs font-bold text-leaf-700 mb-2">摘要</div>
      <p class="text-sm text-stone-700 leading-7 whitespace-pre-line">{{ item.summary }}</p>
    </div>

    <div v-if="item.content" class="mt-5 prose-body text-sm text-stone-700">
      <p v-for="(p, i) in item.content.split('\n').filter(Boolean)" :key="i">{{ p }}</p>
    </div>

    <div class="mt-5 flex flex-wrap gap-1.5" v-if="item.tags?.length">
      <router-link v-for="t in item.tags" :key="t" :to="`/tags/${encodeURIComponent(t)}`"
        class="px-2.5 py-1 text-xs rounded-full bg-leaf-50 text-leaf-700 border border-leaf-100 hover:bg-leaf-100 transition-colors">
        #{{ t }}
      </router-link>
    </div>

    <div class="mt-6 border-t border-leaf-100 pt-5">
      <div class="text-xs font-bold text-stone-500 mb-3">
        信源（{{ item.sources?.length || 1 }} 个）<span v-if="item.sources?.length > 1">· 多信源合并去重</span>
      </div>
      <ul class="space-y-2">
        <li v-for="(s, i) in item.sources?.length ? item.sources : [{ name: item.source_name, url: item.url }]" :key="i">
          <a :href="s.url || item.url" target="_blank" rel="noopener"
            class="text-sm text-leaf-700 hover:underline break-all">
            {{ s.name || '原文链接' }} ↗
          </a>
        </li>
      </ul>
    </div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, fmtDay } from '../api'

const route = useRoute()
const item = ref(null)
const loading = ref(true)

watch(() => route.params.id, load, { immediate: true })

async function load() {
  loading.value = true
  item.value = null
  try {
    item.value = await api.item(route.params.id)
  } catch {
    item.value = null
  } finally {
    loading.value = false
  }
}

const dateLabel = computed(() => (item.value ? fmtDay(item.value.published_at || item.value.created_at) : ''))
</script>
