import { createHash, randomBytes } from 'node:crypto'

export function validateWechatUrl(value, siteUrl) {
  if (typeof value !== 'string' || value.length > 4096) return null
  const raw = value.split('#')[0]
  try {
    const url = new URL(raw)
    const site = new URL(siteUrl)
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== site.origin) return null
    if (url.username || url.password || /^\/(?:admin|wechat)(?:\/|$)/.test(url.pathname)) return null
    // Sign the original bytes: normalizing an encoded query can invalidate the signature.
    return raw
  } catch {
    return null
  }
}

export function wechatSignature(ticket, nonceStr, timestamp, url) {
  return createHash('sha1')
    .update(`jsapi_ticket=${ticket}&noncestr=${nonceStr}&timestamp=${timestamp}&url=${url}`)
    .digest('hex')
}

export function createWechatSigner({ appId, appSecret, request, now = Date.now }) {
  let token = null
  let ticket = null
  let pending = null
  let retryAfter = 0

  function credential(data, key) {
    if (data?.errcode || !data?.[key] || !(Number(data.expires_in) > 0)) {
      throw new Error('WeChat credential unavailable')
    }
    return { value: data[key], expiresAt: now() + Math.max(0, Number(data.expires_in) - 300) * 1000 }
  }

  async function getTicket() {
    if (ticket?.expiresAt > now()) return ticket.value
    if (retryAfter > now()) throw new Error('WeChat temporarily unavailable')
    if (!pending) {
      pending = (async () => {
        if (!token || token.expiresAt <= now()) {
          // stable_token does not invalidate tokens used by other services on this account.
          const data = await request('https://api.weixin.qq.com/cgi-bin/stable_token', {
            method: 'POST',
            body: { grant_type: 'client_credential', appid: appId, secret: appSecret, force_refresh: false },
            timeout: 8000,
            retry: 0,
          })
          token = credential(data, 'access_token')
        }
        const data = await request('https://api.weixin.qq.com/cgi-bin/ticket/getticket', {
          query: { access_token: token.value, type: 'jsapi' },
          timeout: 8000,
          retry: 0,
        })
        if ([40001, 40014, 42001].includes(Number(data?.errcode))) token = null
        ticket = credential(data, 'ticket')
        return ticket.value
      })().catch(() => {
        retryAfter = now() + 60_000
        // Upstream errors may contain credential-bearing request URLs. Never forward them.
        throw new Error('WeChat temporarily unavailable')
      }).finally(() => { pending = null })
    }
    return pending
  }

  return async (url) => {
    const value = await getTicket()
    const nonceStr = randomBytes(16).toString('hex')
    const timestamp = Math.floor(now() / 1000)
    return { appId, nonceStr, timestamp, signature: wechatSignature(value, nonceStr, timestamp, url) }
  }
}
