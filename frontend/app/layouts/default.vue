<template>
  <div class="public-site min-h-screen flex flex-col">
    <a href="#main-content" class="skip-link">跳转到正文</a>
    <header class="site-header">
      <div class="max-w-6xl mx-auto px-4">
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
              class="site-nav-link"
              :class="{ 'is-active': isActive(l) }"
            >
              <span class="md:hidden">{{ l.mobileLabel || l.label }}</span>
              <span class="hidden md:inline">{{ l.label }}</span>
            </NuxtLink>
          </nav>
        </div>
      </div>
    </header>

    <main id="main-content" tabindex="-1" class="site-main flex-1 w-full max-w-6xl mx-auto px-4" :class="{ 'detail-main': isItemDetail }">
      <slot />
    </main>

    <footer class="site-footer">
      <div class="max-w-6xl mx-auto px-4">
        <div class="footer-top">
          <div><p class="footer-title">{{ DEFAULT_TITLE }}</p><p class="footer-note">内容整理自公开来源，摘要由 AI 生成，引用请以官方原文为准</p></div>
          <nav aria-label="页脚导航">
            <NuxtLink to="/agent">Agent 接入</NuxtLink>
            <NuxtLink to="/about">关于本站</NuxtLink>
            <button type="button" @click="onAdminClick">
              {{ showAdmin ? '管理后台' : '管理' }}
            </button>
          </nav>
        </div>
        <p class="footer-credit">Made with 🩷 By <a href="mailto:ijedyu@gmail.com">AJ</a></p>
      </div>
    </footer>
  </div>
</template>

<script setup>
const route = useRoute()
const router = useRouter()
const showAdmin = useClientAdmin()
const session = useAdminSession()
const isItemDetail = computed(() => route.path.startsWith('/items/'))

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
