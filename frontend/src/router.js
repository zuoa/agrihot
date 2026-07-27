import { createRouter, createWebHistory } from 'vue-router'

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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · AgriHot` : 'AgriHot · 农业信息化动态聚合'
})

export default router
