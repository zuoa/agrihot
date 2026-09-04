import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8100', changeOrigin: true },
      '/robots.txt': { target: 'http://localhost:8100', changeOrigin: true },
      '/sitemap.xml': { target: 'http://localhost:8100', changeOrigin: true },
      '/seo': { target: 'http://localhost:8100', changeOrigin: true },
    },
  },
})
