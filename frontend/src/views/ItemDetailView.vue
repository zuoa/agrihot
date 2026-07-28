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

    <ScoreBreakdown v-if="item.score != null" class="mt-5" :score="item.score" :detail="item.score_detail" />

    <div v-if="item.content" class="mt-5">
      <div class="text-xs font-bold text-stone-500 mb-2">全文</div>
      <!-- eslint-disable-next-line vue/no-v-html -- sanitized by DOMPurify in renderMarkdown -->
      <div class="prose-body text-sm text-stone-700" v-html="contentHtml"></div>
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

    <!-- 管理操作 -->
    <div v-if="adminSession.loggedIn" class="mt-6 pt-5 border-t border-dashed border-stone-200 flex gap-2 justify-end">
      <button @click="fetchContent" :disabled="fetching"
        class="px-4 py-1.5 text-xs rounded-full border border-sky-200 text-sky-700 hover:bg-sky-50 disabled:opacity-50">
        {{ fetching ? '抓取中…' : (item.content ? '重新获取全文' : '获取全文') }}
      </button>
      <button @click="showEdit = true"
        class="px-4 py-1.5 text-xs rounded-full border border-leaf-300 text-leaf-700 hover:bg-leaf-50">编辑</button>
      <button @click="remove" :disabled="deleting"
        class="px-4 py-1.5 text-xs rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50">
        {{ deleting ? '删除中…' : '删除' }}
      </button>
    </div>

    <ItemEditModal v-if="showEdit" :item="item"
      @close="showEdit = false" @saved="(it) => (item = it)" />
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminSession, api, fmtDay } from '../api'
import { renderMarkdown } from '../markdown'
import ItemEditModal from '../components/ItemEditModal.vue'
import ScoreBreakdown from '../components/ScoreBreakdown.vue'

const route = useRoute()
const router = useRouter()
const item = ref(null)
const loading = ref(true)
const showEdit = ref(false)
const deleting = ref(false)
const fetching = ref(false)

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

async function fetchContent() {
  if (item.value.content && !confirm('已有全文，重新抓取将覆盖现有内容，确定继续？')) return
  fetching.value = true
  try {
    // 返回的是更新后的完整条目（含新评分），直接替换本地状态
    item.value = await api.adminFetchContent(item.value.id)
  } catch (e) {
    alert(e.message)
  } finally {
    fetching.value = false
  }
}

async function remove() {
  if (!confirm(`确定删除「${item.value.title.slice(0, 30)}」？此操作不可恢复。`)) return
  deleting.value = true
  try {
    await api.adminDeleteItem(item.value.id)
    router.back()
  } catch (e) {
    alert(e.message)
  } finally {
    deleting.value = false
  }
}

const dateLabel = computed(() => (item.value ? fmtDay(item.value.published_at || item.value.created_at) : ''))
const contentHtml = computed(() => renderMarkdown(item.value?.content))
</script>
