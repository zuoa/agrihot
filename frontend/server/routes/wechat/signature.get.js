import { createWechatSigner, validateWechatUrl } from '../../utils/wechat.js'

let signer = null
let credentials = ''

export default defineEventHandler(async (event) => {
  setResponseHeader(event, 'Cache-Control', 'no-store')
  const config = useRuntimeConfig(event)
  const { wechatAppId: appId, wechatAppSecret: appSecret } = config
  if (!appId || !appSecret) return { enabled: false }

  const url = validateWechatUrl(getQuery(event).url, config.public.siteUrl)
  if (!url) throw createError({ statusCode: 400, statusMessage: 'Invalid share URL' })

  if (!signer || credentials !== `${appId}:${appSecret}`) {
    signer = createWechatSigner({ appId, appSecret, request: $fetch })
    credentials = `${appId}:${appSecret}`
  }
  try {
    return { enabled: true, ...await signer(url) }
  } catch {
    throw createError({ statusCode: 503, statusMessage: 'WeChat sharing temporarily unavailable' })
  }
})
