export default defineNuxtPlugin(() => {
  const existing = document.getElementById('LA_COLLECT')
  if (existing) return
  const s = document.createElement('script')
  s.charset = 'UTF-8'
  s.id = 'LA_COLLECT'
  s.src = '//sdk.51.la/js-sdk-pro.min.js'
  s.onload = () => {
    window.LA?.init({ id: '3R3wMa3Yh8VZcLyF', ck: '3R3wMa3Yh8VZcLyF' })
  }
  document.head.appendChild(s)
})
