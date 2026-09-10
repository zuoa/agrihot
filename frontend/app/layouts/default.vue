<template>
  <div class="min-h-screen flex flex-col">
    <header class="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-leaf-100">
      <div class="max-w-3xl mx-auto px-4">
        <div class="flex items-center gap-2 py-3">
          <NuxtLink to="/" class="flex items-center gap-2 mr-4">
            <span class="w-8 h-8 rounded-lg bg-leaf-600 text-white grid place-items-center text-lg">🌾</span>
            <div class="leading-tight">
              <div class="font-bold text-leaf-800 text-lg">AgriHot</div>
              <div class="text-[11px] text-stone-400 hidden sm:block">农业信息化动态聚合 · 每日精选</div>
            </div>
          </NuxtLink>
          <nav class="flex items-center gap-1 text-sm overflow-x-auto">
            <NuxtLink
              v-for="l in links"
              :key="l.to"
              :to="l.to"
              class="px-3 py-1.5 rounded-full whitespace-nowrap transition-colors"
              :class="isActive(l) ? 'bg-leaf-600 text-white font-medium' : 'text-stone-600 hover:bg-leaf-100'"
            >
              {{ l.label }}
            </NuxtLink>
          </nav>
          <button
            @click="onAdminClick"
            class="ml-auto shrink-0 px-3 py-1.5 text-xs rounded-full border transition-colors"
            :class="showAdmin
              ? 'border-leaf-600 text-leaf-700 bg-leaf-50 hover:bg-leaf-100'
              : 'border-stone-200 text-stone-400 hover:border-leaf-300 hover:text-leaf-600'"
          >
            {{ showAdmin ? '后台' : '管理' }}
          </button>
        </div>
      </div>
    </header>

    <main class="flex-1 max-w-3xl mx-auto w-full px-4 py-6">
      <slot />
    </main>

    <footer class="border-t border-leaf-100 bg-white">
      <div class="max-w-3xl mx-auto px-4 py-6 text-center text-xs text-stone-400 space-y-1">
        <p>AgriHot · 农业信息化动态聚合 — 内容整理自公开来源，摘要由 AI 生成，引用请以官方原文为准</p>
        <p>
          <NuxtLink to="/agent" class="text-leaf-600 hover:underline">Agent 接入说明</NuxtLink>
          · <NuxtLink to="/about" class="text-leaf-600 hover:underline">关于本站</NuxtLink>
          · Made with 🩷 By <a href="mailto:ijedyu@gmail.com" class="text-leaf-600 hover:underline">AJ</a>
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup>
const route = useRoute()
const router = useRouter()
const showAdmin = useClientAdmin()
const session = useAdminSession()

function onAdminClick() {
  session.hydrateFromStorage()
  router.push(session.loggedIn.value ? '/admin' : '/admin/login')
}

const links = [
  { to: '/', label: '精选', name: 'index' },
  { to: '/feed', label: '全部动态', name: 'feed' },
  { to: '/dailies', label: '农业日报', name: 'dailies' },
  { to: '/tags', label: '主题', name: 'tags' },
  { to: '/agent', label: 'Agent 接入', name: 'agent' },
  { to: '/about', label: '关于', name: 'about' },
]

const isActive = (l) => {
  if (l.to === '/') return route.path === '/'
  if (l.to === '/dailies') return route.path.startsWith('/dailies')
  if (l.to === '/tags') return route.path.startsWith('/tags')
  return route.path === l.to
}
</script>
