const apiBase = process.env.NUXT_API_BASE || 'http://localhost:8100'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  // Keep SSR data inline: encoded tag paths otherwise double-encode payload URLs.
  experimental: { payloadExtraction: false },
  css: ['~/assets/css/main.css'],
  app: {
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      charset: 'utf-8',
      viewport: 'width=device-width, initial-scale=1',
      link: [
        { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon.png' },
        { rel: 'sitemap', type: 'application/xml', href: '/sitemap.xml' },
        { rel: 'preconnect', href: 'https://wsrv.nl', crossorigin: '' },
        { rel: 'dns-prefetch', href: 'https://wsrv.nl' },
      ],
      meta: [
        { name: 'theme-color', content: '#234e22' },
        { name: 'author', content: 'AgriHot' },
      ],
    },
  },
  nitro: {
    compressPublicAssets: true,
  },
  runtimeConfig: {
    apiBase,
    // Server-only credentials; set NUXT_WECHAT_APP_ID / NUXT_WECHAT_APP_SECRET at runtime.
    wechatAppId: '',
    wechatAppSecret: '',
    public: {
      siteUrl: 'https://agrihot.com',
    },
  },
  routeRules: {
    '/_nuxt/**': { headers: { 'cache-control': 'public, max-age=31536000, immutable' } },
    '/logo.svg': { headers: { 'cache-control': 'public, max-age=86400, stale-while-revalidate=604800' } },
    '/favicon.svg': { headers: { 'cache-control': 'public, max-age=86400, stale-while-revalidate=604800' } },
    '/apple-touch-icon.png': { headers: { 'cache-control': 'public, max-age=86400, stale-while-revalidate=604800' } },
    '/': { swr: 60 },
    '/feed': { swr: 60 },
    '/dailies': { swr: 60 },
    '/dailies/**': { swr: 300 },
    '/items/**': { swr: 300 },
    '/n/**': { swr: 300 },
    '/tags': { swr: 300 },
    '/topic': { swr: 60 },
    '/topic/**': { swr: 60 },
    '/tags/**': { swr: 300 },
    '/about': { swr: 3600 },
    '/agent': { swr: 3600 },
    '/admin/**': { ssr: false },
  },
  postcss: {
    plugins: {
      tailwindcss: {},
      autoprefixer: {},
    },
  },
})
