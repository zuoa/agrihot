<template>
  <div class="min-h-screen grid place-items-center px-4 py-12 bg-stone-100">
    <div class="w-full max-w-sm">
      <div class="flex items-center gap-3 mb-8">
        <span class="w-10 h-10 rounded-lg bg-leaf-800 text-white grid place-items-center text-lg">🌾</span>
        <div>
          <div class="font-bold text-leaf-900">AgriHot 后台</div>
          <div class="text-xs text-stone-400">运营控制台</div>
        </div>
      </div>
      <form @submit.prevent="submit" class="bg-white border border-stone-200 rounded-xl p-6 shadow-sm">
        <h1 class="text-base font-bold text-stone-900 mb-1">登录</h1>
        <p class="text-xs text-stone-400 mb-5">使用 ADMIN_PASSWORD 进入配置、调度与内容审核。</p>
        <label class="block">
          <span class="text-xs text-stone-500">管理密码</span>
          <input v-model="password" type="password" autofocus required
            class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-stone-200 focus:outline-none focus:border-leaf-500" />
        </label>
        <p v-if="error" class="mt-2 text-xs text-red-600">{{ error }}</p>
        <button type="submit" :disabled="loading || !password"
          class="mt-5 w-full py-2 text-sm rounded-lg bg-leaf-700 text-white font-medium hover:bg-leaf-800 disabled:opacity-50">
          {{ loading ? '验证中…' : '进入后台' }}
        </button>
      </form>
      <p class="mt-4 text-center text-xs text-stone-400">
        <router-link to="/" class="hover:text-leaf-700">← 返回公开站</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../../api'

const route = useRoute()
const router = useRouter()
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.adminLogin(password.value)
    const dest = typeof route.query.redirect === 'string' ? route.query.redirect : '/admin'
    router.replace(dest.startsWith('/admin') ? dest : '/admin')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
