<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" @click.self="$emit('close')">
      <div class="w-full max-w-sm bg-white rounded-2xl shadow-xl p-6">
        <h2 class="text-lg font-bold text-stone-900 mb-1">管理登录</h2>
        <p class="text-xs text-stone-400 mb-4">输入管理密码后可编辑 / 删除条目</p>

        <form @submit.prevent="submit">
          <input v-model="password" type="password" placeholder="管理密码" autofocus
            class="w-full px-3.5 py-2.5 text-sm rounded-lg border border-leaf-200 focus:outline-none focus:border-leaf-500" />
          <p v-if="error" class="mt-2 text-xs text-red-600">{{ error }}</p>
          <div class="mt-4 flex gap-2 justify-end">
            <button type="button" @click="$emit('close')"
              class="px-4 py-2 text-sm rounded-full border border-stone-200 text-stone-600 hover:bg-stone-50">取消</button>
            <button type="submit" :disabled="loading || !password"
              class="px-4 py-2 text-sm rounded-full bg-leaf-600 text-white font-medium hover:bg-leaf-700 disabled:opacity-50">
              {{ loading ? '验证中…' : '登录' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['close', 'success'])
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.adminLogin(password.value)
    emit('success')
    emit('close')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
