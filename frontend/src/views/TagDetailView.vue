<template>
  <div>
    <div class="flex items-center gap-3 mb-5">
      <router-link to="/tags" class="text-sm text-stone-400 hover:text-leaf-600">← 主题</router-link>
      <h1 class="text-xl font-bold text-leaf-800">#{{ name }}</h1>
    </div>
    <div v-if="loading" class="text-center text-stone-400 py-16">加载中…</div>
    <div v-else-if="!items.length" class="text-center text-stone-400 py-16">该主题下暂无内容</div>
    <div v-else class="space-y-3">
      <ItemCard v-for="it in items" :key="it.id" :item="it" @updated="load" @deleted="load" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import ItemCard from '../components/ItemCard.vue'

const route = useRoute()
const items = ref([])
const loading = ref(true)

const name = computed(() => route.params.name)

watch(name, load, { immediate: true })

async function load() {
  loading.value = true
  try {
    items.value = (await api.items({ tag: name.value, page_size: 100 })).items
  } finally {
    loading.value = false
  }
}
</script>
