<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 overflow-y-auto bg-black/40 p-4" @click.self="$emit('close')">
      <div class="w-full max-w-lg mx-auto my-10 bg-white rounded-2xl shadow-xl p-6">
        <h2 class="text-lg font-bold text-stone-900 mb-4">编辑条目 #{{ item.id }}</h2>

        <form @submit.prevent="save" class="space-y-3 text-sm">
          <label class="block">
            <span class="text-xs text-stone-500">标题</span>
            <input v-model="form.title" required
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="block">
            <span class="text-xs text-stone-500">摘要</span>
            <textarea v-model="form.summary" rows="3" required
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="text-xs text-stone-500">分类</span>
              <select v-model="form.category"
                class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 bg-white focus:outline-none focus:border-leaf-500">
                <option v-for="c in ['政策', '报道', '论文', '行业']" :key="c" :value="c">{{ c }}</option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-stone-500">热度</span>
              <input v-model.number="form.hotness" type="number" min="0"
                class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
            </label>
          </div>

          <label class="block">
            <span class="text-xs text-stone-500">标签（逗号分隔）</span>
            <input v-model="tagsText" placeholder="智慧农业, 数字乡村"
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="block">
            <span class="text-xs text-stone-500">原文链接</span>
            <input v-model="form.url" type="url" required
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="flex items-center gap-2 pt-1">
            <input v-model="form.is_selected" type="checkbox" class="accent-leaf-600 w-4 h-4" />
            <span>设为精选（出现在首页）</span>
          </label>

          <p v-if="error" class="text-xs text-red-600">{{ error }}</p>

          <div class="flex gap-2 justify-end pt-2">
            <button type="button" @click="$emit('close')"
              class="px-4 py-2 rounded-full border border-stone-200 text-stone-600 hover:bg-stone-50">取消</button>
            <button type="submit" :disabled="saving"
              class="px-4 py-2 rounded-full bg-leaf-600 text-white font-medium hover:bg-leaf-700 disabled:opacity-50">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const form = reactive({
  title: props.item.title,
  summary: props.item.summary,
  category: props.item.category,
  hotness: props.item.hotness,
  url: props.item.url,
  is_selected: props.item.is_selected,
})
const tagsText = ref((props.item.tags || []).join(', '))
const error = ref('')
const saving = ref(false)

async function save() {
  saving.value = true
  error.value = ''
  try {
    const patch = { ...form }
    patch.tags = tagsText.value.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
    const updated = await api.adminUpdateItem(props.item.id, patch)
    emit('saved', updated)
    emit('close')
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>
