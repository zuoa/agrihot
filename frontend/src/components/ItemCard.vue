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
      <router-link v-if="item.score != null" :to="`/items/${item.id}`"
        class="px-1.5 py-0.5 rounded font-medium tabular-nums"
        :class="item.score >= 85 ? 'bg-green-100 text-green-800' : item.score >= 75 ? 'bg-lime-100 text-lime-700' : 'bg-stone-100 text-stone-500'">
        {{ item.score }} 分
      </router-link>
      <span class="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">{{ item.category }}</span>
      <span v-if="item.sources && item.sources.length > 1" class="text-leaf-600">
        {{ item.sources.length }} 个信源同时报道
      </span>
      <span>阅读 {{ item.view_count ?? 0 }}</span>
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

    <!-- 管理操作 -->
    <div v-if="adminSession.loggedIn" class="mt-3 pt-3 border-t border-dashed border-stone-200 flex gap-2 justify-end">
      <button @click="showEdit = true"
        class="px-3 py-1 text-xs rounded-full border border-leaf-300 text-leaf-700 hover:bg-leaf-50">编辑</button>
      <button @click="remove" :disabled="deleting"
        class="px-3 py-1 text-xs rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50">
        {{ deleting ? '删除中…' : '删除' }}
      </button>
    </div>

    <ItemEditModal v-if="showEdit" :item="item"
      @close="showEdit = false" @saved="(it) => $emit('updated', it)" />
  </article>
</template>

<script setup>
import { computed, ref } from 'vue'
import { adminSession, api, fmtTime, fmtDay } from '../api'
import ItemEditModal from './ItemEditModal.vue'

const props = defineProps({
  item: { type: Object, required: true },
  clamp: { type: Boolean, default: true },
})
const emit = defineEmits(['updated', 'deleted'])

const showEdit = ref(false)
const deleting = ref(false)

async function remove() {
  if (!confirm(`确定删除「${props.item.title.slice(0, 30)}」？此操作不可恢复。`)) return
  deleting.value = true
  try {
    await api.adminDeleteItem(props.item.id)
    emit('deleted', props.item.id)
  } catch (e) {
    alert(e.message)
  } finally {
    deleting.value = false
  }
}

const timeText = computed(() => {
  const iso = props.item.published_at || props.item.created_at
  const today = new Date().toDateString() === new Date(iso).toDateString()
  return today ? fmtTime(iso) : fmtDay(iso)
})
</script>
