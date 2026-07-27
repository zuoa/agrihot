<template>
  <div class="min-h-screen flex flex-col">
    <header class="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-leaf-100">
      <div class="max-w-3xl mx-auto px-4">
        <div class="flex items-center gap-2 py-3">
          <router-link to="/" class="flex items-center gap-2 mr-4">
            <span class="w-8 h-8 rounded-lg bg-leaf-600 text-white grid place-items-center text-lg">🌾</span>
            <div class="leading-tight">
              <div class="font-bold text-leaf-800 text-lg">AgriHot</div>
              <div class="text-[11px] text-stone-400 hidden sm:block">农业信息化动态聚合 · 每日精选</div>
            </div>
          </router-link>
          <nav class="flex items-center gap-1 text-sm overflow-x-auto">
            <router-link v-for="l in links" :key="l.to" :to="l.to"
              class="px-3 py-1.5 rounded-full whitespace-nowrap transition-colors"
              :class="isActive(l) ? 'bg-leaf-600 text-white font-medium' : 'text-stone-600 hover:bg-leaf-100'">
              {{ l.label }}
            </router-link>
          </nav>
        </div>
      </div>
    </header>

    <main class="flex-1 max-w-3xl mx-auto w-full px-4 py-6">
      <router-view />
    </main>

    <footer class="border-t border-leaf-100 bg-white">
      <div class="max-w-3xl mx-auto px-4 py-6 text-center text-xs text-stone-400 space-y-1">
        <p>AgriHot · 农业信息化动态聚合 — 内容整理自公开来源，摘要由 AI 生成，引用请以官方原文为准</p>
        <p>
          <router-link to="/agent" class="text-leaf-600 hover:underline">Agent 接入说明</router-link>
          · <router-link to="/about" class="text-leaf-600 hover:underline">关于本站</router-link>
          · Made with 🩷
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
const links = [
  { to: '/', label: '精选', name: 'home' },
  { to: '/feed', label: '全部动态', name: 'feed' },
  { to: '/dailies', label: '农业日报', name: 'dailies' },
  { to: '/tags', label: '主题', name: 'tags' },
  { to: '/agent', label: 'Agent 接入', name: 'agent' },
  { to: '/about', label: '关于', name: 'about' },
]
const isActive = (l) =>
  route.name === l.name ||
  (l.name === 'dailies' && route.name === 'daily-detail') ||
  (l.name === 'tags' && route.name === 'tag-detail')
</script>
