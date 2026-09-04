import { createRouter, createWebHistory } from 'vue-router'
import { adminSession } from './api'
import { DEFAULT_DESC, DEFAULT_TITLE, setPageMeta, websiteJsonLd } from './seo'

const routes = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue'), meta: { title: '精选', description: '农业信息化每日精选：政策、报道、学术论文与行业动态。' } },
  { path: '/feed', name: 'feed', component: () => import('./views/FeedView.vue'), meta: { title: '全部动态', description: '农业信息化全部动态：政策、报道、学术论文与行业资讯。' } },
  { path: '/dailies', name: 'dailies', component: () => import('./views/DailiesView.vue'), meta: { title: '农业日报', description: '每日《农业农村日报》：农业信息化政策、报道、论文与行业动态精选。' } },
  { path: '/dailies/:date', name: 'daily-detail', component: () => import('./views/DailyDetailView.vue'), meta: { title: '日报详情', dynamic: true } },
  { path: '/items/:id', name: 'item-detail', component: () => import('./views/ItemDetailView.vue'), meta: { title: '资讯详情', dynamic: true } },
  { path: '/tags', name: 'tags', component: () => import('./views/TagsView.vue'), meta: { title: '主题', description: '按主题浏览农业信息化资讯与论文。' } },
  { path: '/tags/:name', name: 'tag-detail', component: () => import('./views/TagDetailView.vue'), meta: { title: '主题', dynamic: true } },
  { path: '/agent', name: 'agent', component: () => import('./views/AgentDocsView.vue'), meta: { title: 'Agent 接入', description: 'AgriHot 开放推送 API：农业信息化资讯接入、自动去重与精选评分。' } },
  { path: '/about', name: 'about', component: () => import('./views/AboutView.vue'), meta: { title: '关于', description: '关于 AgriHot：农业信息化资讯聚合、农业农村日报与学术论文雷达。' } },
  {
    path: '/admin/login',
    name: 'admin-login',
    component: () => import('./views/admin/AdminLoginView.vue'),
    meta: { title: '管理登录', admin: true },
  },
  {
    path: '/admin',
    component: () => import('./views/admin/AdminLayout.vue'),
    meta: { requiresAdmin: true, admin: true },
    children: [
      { path: '', name: 'admin-home', component: () => import('./views/admin/AdminDashboardView.vue'), meta: { title: '后台总览' } },
      { path: 'items', name: 'admin-items', component: () => import('./views/admin/AdminItemsView.vue'), meta: { title: '内容审核' } },
      { path: 'jobs', name: 'admin-jobs', component: () => import('./views/admin/AdminJobsView.vue'), meta: { title: '任务调度' } },
      { path: 'settings', name: 'admin-settings', component: () => import('./views/admin/AdminSettingsView.vue'), meta: { title: '运营配置' } },
      { path: 'watchlist', name: 'admin-watchlist', component: () => import('./views/admin/AdminWatchlistView.vue'), meta: { title: '文献关注面' } },
      { path: 'keys', name: 'admin-keys', component: () => import('./views/admin/AdminKeysView.vue'), meta: { title: 'API Key' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.matched.some((r) => r.meta.requiresAdmin) && !adminSession.loggedIn) {
    return { name: 'admin-login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'admin-login' && adminSession.loggedIn) {
    return { name: 'admin-home' }
  }
})

router.afterEach((to) => {
  const admin = to.matched.some((r) => r.meta.admin)
  if (to.meta.dynamic && !admin) return
  const title = to.meta.title ? `${to.meta.title} · AgriHot` : DEFAULT_TITLE
  setPageMeta({
    title,
    description: to.meta.description || DEFAULT_DESC,
    path: to.fullPath,
    noindex: admin || Boolean(to.query.q),
    jsonLd: to.name === 'home' ? websiteJsonLd() : null,
  })
})

export default router
