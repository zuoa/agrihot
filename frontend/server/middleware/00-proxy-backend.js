const EXACT = new Set(['/openapi.json', '/redoc', '/robots.txt', '/sitemap.xml'])

export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  const path = url.pathname
  if (!path.startsWith('/api') && !path.startsWith('/docs') && !EXACT.has(path)) return
  const { apiBase } = useRuntimeConfig(event)
  return proxyRequest(event, `${apiBase}${path}${url.search}`)
})
