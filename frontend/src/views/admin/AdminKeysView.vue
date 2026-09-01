<template>
  <div class="space-y-4 max-w-3xl">
    <form class="bg-white border border-stone-200 rounded-lg p-4 flex gap-2 items-end" @submit.prevent="create">
      <label class="flex-1 text-sm">
        <span class="text-xs text-stone-500">Key 名称（例如 crawler-policy）</span>
        <input v-model="name" required maxlength="100"
          class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
      </label>
      <button type="submit" :disabled="busy || !name.trim()"
        class="px-4 py-1.5 text-sm rounded-md bg-leaf-700 text-white hover:bg-leaf-800 disabled:opacity-50">
        签发
      </button>
    </form>

    <div v-if="createdKey" class="border border-amber-200 bg-amber-50 rounded-lg p-4 text-sm">
      <div class="font-medium text-amber-900 mb-1">请立即复制，明文只显示这一次</div>
      <code class="block break-all text-xs bg-white border border-amber-100 rounded px-2 py-1.5">{{ createdKey }}</code>
      <button type="button" class="mt-2 text-xs text-amber-800 hover:underline" @click="copy">复制</button>
    </div>

    <p v-if="msg" class="text-xs text-stone-500">{{ msg }}</p>

    <div class="bg-white border border-stone-200 rounded-lg overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-stone-50 text-xs text-stone-500">
          <tr>
            <th class="text-left font-medium px-3 py-2">名称</th>
            <th class="text-left font-medium px-3 py-2">状态</th>
            <th class="text-left font-medium px-3 py-2 hidden sm:table-cell">最近使用</th>
            <th class="text-right font-medium px-3 py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="4" class="px-3 py-10 text-center text-stone-400">加载中…</td></tr>
          <tr v-else-if="!keys.length"><td colspan="4" class="px-3 py-10 text-center text-stone-400">还没有 Key</td></tr>
          <tr v-for="k in keys" :key="k.id" class="border-t border-stone-100">
            <td class="px-3 py-2 font-medium">{{ k.name }}</td>
            <td class="px-3 py-2 text-xs">
              <span :class="k.is_active ? 'text-leaf-700' : 'text-stone-400'">{{ k.is_active ? '启用' : '停用' }}</span>
            </td>
            <td class="px-3 py-2 text-xs text-stone-400 hidden sm:table-cell">{{ k.last_used_at ? fmtWhen(k.last_used_at) : '从未' }}</td>
            <td class="px-3 py-2 text-right">
              <button class="text-xs px-2 py-0.5 rounded border border-stone-200 hover:bg-stone-50"
                :disabled="busy" @click="toggle(k)">
                {{ k.is_active ? '停用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'

const keys = ref([])
const loading = ref(true)
const busy = ref(false)
const name = ref('')
const createdKey = ref('')
const msg = ref('')

onMounted(load)

async function load() {
  loading.value = true
  try {
    keys.value = await api.adminApiKeys()
  } catch (e) {
    msg.value = e.message
  } finally {
    loading.value = false
  }
}

async function create() {
  busy.value = true
  msg.value = ''
  try {
    const created = await api.adminCreateApiKey(name.value.trim())
    createdKey.value = created.key
    name.value = ''
    await load()
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = false
  }
}

async function toggle(k) {
  busy.value = true
  try {
    await api.adminPatchApiKey(k.id, { is_active: !k.is_active })
    await load()
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = false
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(createdKey.value)
    msg.value = '已复制到剪贴板'
  } catch {
    msg.value = '复制失败，请手动选中'
  }
}

function fmtWhen(iso) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>
