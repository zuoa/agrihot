const EXACT = new Set(['/openapi.json', '/redoc', '/robots.txt', '/sitemap.xml', '/llms.txt'])

export default defineEventHandler((event) => {
  const url = getRequestURL(event)
  const path = url.pathname
  if (!path.startsWith('/api') && !path.startsWith('/docs') && !path.startsWith('/agrihot-skill/') && !EXACT.has(path)) return
  const config = useRuntimeConfig(event)
  // h3 normally drops Host and Accept; MCP validates both at the transport boundary.
  const options = path === '/api/v1/mcp' ? {
    headers: {
      host: new URL(config.public.siteUrl).host,
      accept: getRequestHeader(event, 'accept') || 'application/json, text/event-stream',
    },
  } : {}
  return proxyRequest(event, `${config.apiBase}${path}${url.search}`, options)
})
