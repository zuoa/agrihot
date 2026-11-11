export default defineEventHandler((event) => {
  setHeader(event, 'Cache-Control', 'no-store')
  setHeader(event, 'X-Agrihot-Layer', 'frontend')
  return { status: 'ok', service: 'agrihot-frontend' }
})
