export default defineNuxtPlugin(() => {
  const inject = () => {
    if (document.getElementById('LA_COLLECT')) return
    const s = document.createElement('script')
    s.charset = 'UTF-8'
    s.id = 'LA_COLLECT'
    s.async = true
    s.src = '//sdk.51.la/js-sdk-pro.min.js'
    s.onload = () => {
      window.LA?.init({ id: '3R3wMa3Yh8VZcLyF', ck: '3R3wMa3Yh8VZcLyF' })
    }
    document.head.appendChild(s)
  }

  const schedule = () => {
    if (typeof window.requestIdleCallback === 'function') {
      window.requestIdleCallback(inject, { timeout: 3000 })
    } else {
      window.setTimeout(inject, 1200)
    }
  }

  if (document.readyState === 'complete') schedule()
  else window.addEventListener('load', schedule, { once: true })
})
