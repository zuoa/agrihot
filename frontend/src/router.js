import { createRouter, createWebHistory } from 'vue-router'
import { adminSession } from './api'

const routes = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue'), meta: { title: '精选' } },
  { path: '/feed', name: 'feed', component: () => import('./views/FeedView.vue'), meta: { title: '全部动态' } },
  { path: '/dailies', name: 'dailies', component: () => import('./views/DailiesView.vue'), meta: { title: '农业日报' } },
  { path: '/dailies/:date', name: 'daily-detail', component: () => import('./views/DailyDetailView.vue'), meta: { title: '日报详情' } },
  { path: '/items/:id', name: 'item-detail', component: () => import('./views/ItemDetailView.vue'), meta: { title: '资讯详情' } },
  { path: '/tags', name: 'tags', component: () => import('./views/TagsView.vue'), meta: { title: '主题' } },
  { path: '/tags/:name', name: 'tag-detail', component: () => import('./views/TagDetailView.vue'), meta: { title: '主题' } },
  { path: '/agent', name: 'agent', component: () => import('./views/AgentDocsView.vue'), meta: { title: 'Agent 接入' } },
  { path: '/about', name: 'about', component: () => import('./views/AboutView.vue'), meta: { title: '关于' } },
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
  document.title = to.meta.title ? `${to.meta.title} · AgriHot` : 'AgriHot · 农业信息化动态聚合'
})

export default router
