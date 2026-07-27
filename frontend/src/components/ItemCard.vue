<template>
  <article class="bg-white rounded-xl border border-leaf-100 p-4 sm:p-5 hover:border-leaf-300 transition-colors">
    <div class="flex items-center gap-2 text-xs text-stone-400 flex-wrap">
      <span class="text-leaf-700 font-medium">{{ item.source_name || '未知来源' }}</span>
      <span>·</span>
      <span>{{ timeText }}</span>
      <span class="inline-flex items-center gap-0.5 text-amber-600" v-if="item.hotness >= 60">
        🔥 {{ item.hotness }}
      </span>
      <span v-if="item.is_selected"
        class="px-1.5 py-0.5 rounded bg-leaf-100 text-leaf-700 font-medium">精选</span>
      <span class="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">{{ item.category }}</span>
      <span v-if="item.sources && item.sources.length > 1" class="text-leaf-600">
        {{ item.sources.length }} 个信源同时报道
      </span>
    </div>

    <router-link :to="`/items/${item.id}`" class="block mt-2">
      <h2 class="text-base sm:text-lg font-bold text-stone-900 leading-snug hover:text-leaf-700 transition-colors">
        {{ item.title }}
      </h2>
    </router-link>

    <p class="mt-2 text-sm text-stone-600 leading-6" :class="{ 'line-clamp-3': clamp }">
      {{ item.summary }}
    </p>

    <div class="mt-3 flex flex-wrap gap-1.5" v-if="item.tags?.length">
      <router-link v-for="t in item.tags" :key="t" :to="`/tags/${encodeURIComponent(t)}`"
        class="px-2 py-0.5 text-xs rounded-full bg-leaf-50 text-leaf-700 border border-leaf-100 hover:bg-leaf-100 transition-colors">
        #{{ t }}
      </router-link>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { fmtTime, fmtDay } from '../api'

const props = defineProps({
  item: { type: Object, required: true },
  clamp: { type: Boolean, default: true },
})

const timeText = computed(() => {
  const iso = props.item.published_at || props.item.created_at
  const today = new Date().toDateString() === new Date(iso).toDateString()
  return today ? fmtTime(iso) : fmtDay(iso)
})
</script>
