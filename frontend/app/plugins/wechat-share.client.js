const SDK_URL = 'https://res.wx.qq.com/open/js/jweixin-1.6.0.js'
const SHARE_APIS = ['updateAppMessageShareData', 'updateTimelineShareData']

function loadSdk() {
  if (window.wx) return Promise.resolve(window.wx)
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SDK_URL
    script.async = true
    const timeout = setTimeout(() => {
      script.remove()
      reject(new Error('WeChat SDK timeout'))
    }, 10_000)
    script.onload = () => {
      clearTimeout(timeout)
      window.wx ? resolve(window.wx) : reject(new Error('WeChat SDK unavailable'))
    }
    script.onerror = () => {
      clearTimeout(timeout)
      script.remove()
      reject(new Error('WeChat SDK unavailable'))
    }
    document.head.appendChild(script)
  })
}

function configureSdk(wx, signature) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('WeChat config timeout')), 10_000)
    wx.error(() => { clearTimeout(timeout); reject(new Error('WeChat config unavailable')) })
    wx.config({ ...signature, debug: false, jsApiList: SHARE_APIS })
    wx.ready(() => { clearTimeout(timeout); resolve() })
  })
}

export default defineNuxtPlugin((nuxtApp) => {
  if (!/MicroMessenger/i.test(navigator.userAgent)) return

  // iOS WeChat verifies against the initial document URL even after pushState navigation.
  const entryUrl = window.location.href.split('#')[0]
  const isIOS = /iPad|iPhone|iPod/i.test(navigator.userAgent)
  const route = useRouter().currentRoute
  const share = useState('page-share', () => null)
  let sdk = null
  let configuredUrl = ''
  let revision = 0
  let queue = Promise.resolve()

  function scheduleUpdate() {
    const current = ++revision
    queue = queue.then(async () => {
      if (current !== revision || !share.value || route.value.path.startsWith('/admin')) return
      const url = isIOS ? entryUrl : window.location.href.split('#')[0]
      if (configuredUrl !== url) {
        const { enabled, ...signature } = await $fetch('/wechat/signature', { query: { url }, retry: 0 })
        if (!enabled || current !== revision) return
        sdk = sdk || await loadSdk()
        await configureSdk(sdk, signature)
        configuredUrl = url
      }
      if (current !== revision) return
      const { title, desc, link, imgUrl } = share.value
      sdk.updateAppMessageShareData({ title, desc, link, imgUrl })
      sdk.updateTimelineShareData({ title, link, imgUrl })
    }).catch(() => {
      configuredUrl = ''
      // Sharing must never interrupt reading; SEO image metadata remains available.
      console.warn('[AgriHot] 微信分享暂不可用，请检查公众号配置。')
    })
  }

  nuxtApp.hook('app:mounted', () => {
    watch([share, () => route.value.fullPath], scheduleUpdate, { immediate: true, flush: 'post' })
  })
})
