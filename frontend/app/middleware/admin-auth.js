export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) return
  const session = useAdminSession()
  session.hydrateFromStorage()
  if (to.path === '/admin/login') {
    if (session.loggedIn.value) return navigateTo('/admin')
    return
  }
  if (!session.loggedIn.value) {
    return navigateTo({ path: '/admin/login', query: { redirect: to.fullPath } })
  }
})
