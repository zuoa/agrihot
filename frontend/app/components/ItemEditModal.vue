<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 overflow-y-auto bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="item-edit-title" @keydown.esc="$emit('close')" @click.self="$emit('close')">
      <div class="w-full max-w-2xl mx-auto my-10 bg-white rounded-2xl shadow-xl p-6">
        <h2 id="item-edit-title" class="text-lg font-bold text-stone-900 mb-4">编辑条目 #{{ item.id }}</h2>

        <form @submit.prevent="save" class="space-y-3 text-sm">
          <label class="block">
            <span class="text-xs text-stone-500">标题</span>
            <input v-model="form.title" required
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="block">
            <span class="text-xs text-stone-500">摘要（原文）</span>
            <textarea v-model="form.summary" rows="3" required
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="block">
            <span class="text-xs text-stone-500">中文摘要（外文译文，可空）</span>
            <textarea v-model="form.summary_zh" rows="3"
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          </label>

          <label class="block">
            <span class="text-xs text-stone-500">全文（Markdown，留空则不展示）</span>
            <textarea v-model="form.content" rows="10"
              class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 font-mono text-xs focus:outline-none focus:border-leaf-500" />
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

          <fieldset class="rounded-lg border border-leaf-200 p-3 space-y-3">
            <legend class="px-1 text-xs text-leaf-800">主题归属</legend>
            <p v-if="topicError" class="text-xs text-red-600">主题目录加载失败，请关闭后重试。</p>
            <label class="block">
              <span class="text-xs text-stone-500">主主题</span>
              <select v-model="assignment.primary_code" aria-label="主主题" :disabled="!topics.length" class="mt-1 w-full px-3 py-2 rounded-lg border border-leaf-200 bg-white">
                <option value="">待分类</option>
                <optgroup v-for="root in topics" :key="root.code" :label="root.name">
                  <option :value="root.code">{{ root.name }}（待细分）</option>
                  <option v-for="child in root.children" :key="child.code" :value="child.code">{{ child.name }}</option>
                </optgroup>
              </select>
            </label>
            <div class="grid sm:grid-cols-2 gap-3">
              <label v-for="i in [0, 1]" :key="i" class="block">
                <span class="text-xs text-stone-500">辅主题 {{ i + 1 }}</span>
                <select v-model="assignment.secondary_codes[i]" :aria-label="`辅主题 ${i + 1}`" :disabled="!topics.length || !assignment.primary_code" class="mt-1 w-full px-2 py-2 rounded-lg border border-leaf-200 bg-white">
                  <option value="">无</option>
                  <optgroup v-for="root in topics" :key="root.code" :label="root.name">
                    <option v-for="child in root.children" :key="child.code" :value="child.code"
                      :disabled="child.code === assignment.primary_code || child.parent_code === assignment.primary_code || child.code === assignment.secondary_codes[1 - i]">{{ child.name }}</option>
                  </optgroup>
                </select>
              </label>
            </div>
            <label class="flex items-center gap-2 text-xs text-stone-600">
              <input v-model="assignment.locked" type="checkbox" class="accent-leaf-600" />锁定归属，保留人工确认结果
            </label>
            <p v-if="item.classification?.evidence?.reason" class="text-xs text-stone-500">{{ item.classification.evidence.reason }}</p>
          </fieldset>

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

const api = useApi()
const props = defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const form = reactive({
  title: props.item.title,
  summary: props.item.summary,
  summary_zh: props.item.summary_zh || '',
  content: props.item.content || '',
  category: props.item.category,
  hotness: props.item.hotness,
  url: props.item.url,
  is_selected: props.item.is_selected,
})
const tagsText = ref((props.item.tags || []).join(', '))
const error = ref('')
const saving = ref(false)
const topics = ref([])
const topicError = ref(false)
const assignment = reactive({
  primary_code: props.item.primary_topic?.code || '',
  secondary_codes: [props.item.secondary_topics?.[0]?.code || '', props.item.secondary_topics?.[1]?.code || ''],
  locked: props.item.classification?.locked || false,
})
const originalAssignment = JSON.stringify(assignment)
watch(() => [assignment.primary_code, ...assignment.secondary_codes], () => { assignment.locked = true })
watch(() => assignment.primary_code, value => {
  assignment.secondary_codes = assignment.secondary_codes.map(code => value && code !== value ? code : '')
})
onMounted(async () => {
  try { topics.value = (await api.taxonomy()).topics } catch { topicError.value = true }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    const patch = { ...form }
    // 空字符串 -> null：清空全文而不是存一个空串（后端 exclude_unset，null 是显式赋值）
    patch.content = form.content.trim() || null
    patch.summary_zh = form.summary_zh.trim() || null
    patch.tags = tagsText.value.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
    if (JSON.stringify(assignment) !== originalAssignment) {
      patch.taxonomy = { primary_code: assignment.primary_code || null,
        secondary_codes: assignment.secondary_codes.filter(Boolean), locked: assignment.locked }
    }
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
