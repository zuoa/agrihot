<template>
  <div>
    <h1 class="text-xl font-bold text-leaf-800 mb-5">主题</h1>
    <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else class="flex flex-wrap gap-2.5">
      <router-link v-for="t in tags" :key="t.name" :to="`/tags/${encodeURIComponent(t.name)}`"
        class="px-4 py-2 rounded-full bg-white border border-leaf-200 text-sm text-stone-700 hover:border-leaf-500 hover:text-leaf-700 transition-colors">
        #{{ t.name }}
        <span class="ml-1 text-xs text-stone-400">{{ t.count }}</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const tags = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    tags.value = await api.tags()
  } finally {
    loading.value = false
  }
})
</script>
