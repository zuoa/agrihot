<template>
  <div class="min-h-screen flex flex-col">
    <header class="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-leaf-100">
      <div class="max-w-4xl mx-auto px-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between md:gap-4">
          <NuxtLink to="/" aria-label="AgriHot 首页" class="flex w-fit shrink-0 items-center gap-2.5 pt-3 pb-2 md:py-3 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-leaf-600">
            <BrandMark class="w-8 h-8" />
            <div class="leading-tight">
              <div class="font-bold text-leaf-900 text-lg tracking-tight">AgriHot<span class="text-leaf-500">.</span></div>
              <div class="text-[11px] text-stone-500">{{ SITE_TAGLINE }}</div>
            </div>
          </NuxtLink>
          <nav aria-label="主导航" class="grid grid-cols-6 items-center gap-0.5 pb-2 text-[13px] md:flex md:py-3 md:text-sm">
            <NuxtLink
              v-for="l in links"
              :key="l.to"
              :to="l.to"
              :aria-current="isActive(l) ? 'page' : undefined"
              class="flex min-h-11 items-center justify-center rounded-xl px-1 whitespace-nowrap transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf-600 md:min-h-10 md:rounded-full md:px-3"
              :class="isActive(l) ? 'bg-leaf-600 text-white font-medium' : 'text-stone-600 hover:bg-leaf-100'"
            >
              <span class="md:hidden">{{ l.mobileLabel || l.label }}</span>
              <span class="hidden md:inline">{{ l.label }}</span>
            </NuxtLink>
          </nav>
        </div>
      </div>
    </header>

    <main class="flex-1 w-full px-4 py-6 mx-auto max-w-4xl" :class="wide ? 'xl:max-w-7xl' : ''">
      <slot />
    </main>

    <footer class="border-t border-leaf-100 bg-white">
      <div class="max-w-4xl mx-auto px-4 py-6 text-center text-xs text-stone-400">
        <p class="font-medium text-stone-600">{{ DEFAULT_TITLE }}</p>
        <p class="mt-2 leading-5">内容整理自公开来源，摘要由 AI 生成，引用请以官方原文为准</p>
        <nav aria-label="页脚导航" class="mt-2 flex flex-wrap items-center justify-center gap-x-4">
          <NuxtLink to="/agent" class="inline-flex min-h-11 items-center text-leaf-700 hover:underline focus-visible:outline-leaf-600">Agent 接入</NuxtLink>
          <NuxtLink to="/about" class="inline-flex min-h-11 items-center text-leaf-700 hover:underline focus-visible:outline-leaf-600">关于本站</NuxtLink>
          <button type="button" @click="onAdminClick" class="min-h-11 text-stone-500 hover:text-leaf-700 hover:underline focus-visible:outline-leaf-600">
            {{ showAdmin ? '管理后台' : '管理' }}
          </button>
        </nav>
        <p>Made with 🩷 By <a href="mailto:ijedyu@gmail.com" class="inline-flex min-h-8 items-center text-leaf-700 hover:underline">AJ</a></p>
      </div>
    </footer>
  </div>
</template>

<script setup>
const route = useRoute()
const router = useRouter()
const showAdmin = useClientAdmin()
const wide = computed(() => route.path.startsWith('/items/'))
const session = useAdminSession()

function onAdminClick() {
  session.hydrateFromStorage()
  router.push(session.loggedIn.value ? '/admin' : '/admin/login')
}

const links = [
  { to: '/', label: '精选', name: 'index' },
  { to: '/feed', label: '全部动态', mobileLabel: '动态', name: 'feed' },
  { to: '/dailies', label: '农业日报', mobileLabel: '日报', name: 'dailies' },
  { to: '/topic', label: '主题', name: 'topic' },
  { to: '/agent', label: 'Agent 接入', mobileLabel: 'Agent', name: 'agent' },
  { to: '/about', label: '关于', name: 'about' },
]

const isActive = (l) => {
  if (l.to === '/') return route.path === '/'
  if (l.to === '/dailies') return route.path.startsWith('/dailies')
  if (l.to === '/topic') return route.path.startsWith('/topic') || route.path.startsWith('/tags')
  return route.path === l.to
}
</script>
