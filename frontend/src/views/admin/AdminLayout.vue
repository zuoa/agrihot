<template>
  <div class="min-h-screen flex flex-col lg:flex-row bg-stone-100 text-stone-800">
    <aside class="lg:w-52 shrink-0 bg-leaf-950 text-leaf-50 lg:min-h-screen">
      <div class="flex items-center gap-2 px-4 py-4 border-b border-white/10">
        <span class="w-8 h-8 rounded-md bg-leaf-600 text-white grid place-items-center text-sm">🌾</span>
        <div class="leading-tight">
          <div class="font-bold text-sm">AgriHot</div>
          <div class="text-[10px] text-leaf-300 tracking-wide">运营控制台</div>
        </div>
      </div>
      <nav class="flex lg:flex-col overflow-x-auto px-2 py-2 gap-1">
        <router-link v-for="l in links" :key="l.to" :to="l.to"
          class="px-3 py-2 rounded-md text-sm whitespace-nowrap transition-colors"
          :class="isActive(l)
            ? 'bg-leaf-700 text-white'
            : 'text-leaf-200 hover:bg-white/10 hover:text-white'">
          {{ l.label }}
        </router-link>
      </nav>
    </aside>

    <div class="flex-1 min-w-0 flex flex-col">
      <header class="h-12 px-4 sm:px-6 flex items-center justify-between bg-white border-b border-stone-200">
        <h1 class="text-sm font-bold text-stone-800">{{ title }}</h1>
        <div class="flex items-center gap-3 text-xs">
          <router-link to="/" class="text-stone-500 hover:text-leaf-700">公开站 ↗</router-link>
          <button @click="logout" class="text-stone-500 hover:text-red-600">退出</button>
        </div>
      </header>
      <div class="flex-1 px-4 sm:px-6 py-5 max-w-6xl w-full">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminSession, api } from '../../api'

const route = useRoute()
const router = useRouter()

const links = [
  { to: '/admin', name: 'admin-home', label: '总览' },
  { to: '/admin/items', name: 'admin-items', label: '内容' },
  { to: '/admin/jobs', name: 'admin-jobs', label: '任务' },
  { to: '/admin/settings', name: 'admin-settings', label: '配置' },
  { to: '/admin/watchlist', name: 'admin-watchlist', label: '关注面' },
  { to: '/admin/keys', name: 'admin-keys', label: 'API Key' },
]

const title = computed(() => route.meta.title || '后台')
const isActive = (l) => route.name === l.name

onMounted(async () => {
  try {
    await api.adminMe()
  } catch {
    adminSession.clear()
    router.replace({ name: 'admin-login', query: { redirect: route.fullPath } })
  }
})

function logout() {
  adminSession.clear()
  router.push('/')
}
</script>
