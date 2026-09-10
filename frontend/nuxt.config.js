const apiBase = process.env.NUXT_API_BASE || 'http://localhost:8100'

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
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
      ],
      meta: [
        { name: 'theme-color', content: '#327a2d' },
        { name: 'author', content: 'AgriHot' },
      ],
    },
  },
  runtimeConfig: {
    apiBase,
    public: {
      siteUrl: 'https://agrihot.com',
    },
  },
  routeRules: {
    '/': { swr: 60 },
    '/feed': { swr: 60 },
    '/dailies': { swr: 60 },
    '/dailies/**': { swr: 300 },
    '/items/**': { swr: 300 },
    '/tags': { swr: 300 },
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
