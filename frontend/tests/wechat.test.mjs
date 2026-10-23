import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { createWechatSigner, validateWechatUrl, wechatSignature } from '../server/utils/wechat.js'

const origin = 'https://agrihot.com'

test('only public same-origin URLs are signed, preserving encoded query bytes', () => {
  const url = `${origin}/tags/%E6%B0%B4%E7%A8%BB?q=a%20b&from=timeline&x=%26#section`
  assert.equal(validateWechatUrl(url, origin), url.split('#')[0])
  for (const value of [
    undefined, ['https://agrihot.com/'], '/', 'javascript:alert(1)',
    'https://example.org/', 'https://agrihot.com.evil.org/', 'http://agrihot.com/',
    'https://agrihot.com:444/', 'https://user:password@agrihot.com/',
    `${origin}/admin`, `${origin}/admin/login`, `${origin}/wechat/signature`,
    `${origin}/${'x'.repeat(4096)}`,
  ]) assert.equal(validateWechatUrl(value, origin), null)
})

test('signature uses sorted lowercase fields and exact URL bytes', () => {
  const url = `${origin}/?q=a%20b&x=%26`
  const expected = createHash('sha1').update([
    ['url', url], ['timestamp', 1414587457], ['noncestr', 'nonce'], ['jsapi_ticket', 'ticket'],
  ].sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${value}`).join('&')).digest('hex')
  assert.equal(wechatSignature('ticket', 'nonce', 1414587457, url), expected)
  assert.notEqual(wechatSignature('ticket', 'nonce', 1414587457, url.replace('%20', '+')), expected)
})

test('concurrent requests share credential refresh and expose only signing fields', async () => {
  const calls = []
  const sign = createWechatSigner({
    appId: 'app', appSecret: 'secret',
    request: async (url, options) => {
      calls.push({ url, options })
      return url.endsWith('stable_token')
        ? { access_token: 'private-token', expires_in: 7200 }
        : { errcode: 0, ticket: 'private-ticket', expires_in: 7200 }
    },
    now: () => 1_700_000_000_000,
  })
  const results = await Promise.all(Array.from({ length: 20 }, () => sign(`${origin}/`)))
  assert.equal(calls.length, 2)
  assert.equal(calls[0].options.body.force_refresh, false)
  assert.equal(calls[1].options.query.access_token, 'private-token')
  for (const result of results) {
    assert.deepEqual(Object.keys(result).sort(), ['appId', 'nonceStr', 'signature', 'timestamp'])
    assert.equal(result.signature, wechatSignature('private-ticket', result.nonceStr, result.timestamp, `${origin}/`))
    assert.doesNotMatch(JSON.stringify(result), /private-token|private-ticket|secret/)
  }
  assert.equal(new Set(results.map(r => r.nonceStr)).size, 20)
  await sign(`${origin}/items/1`)
  assert.equal(calls.length, 2)
})

test('ticket refresh reuses a still-valid token, then refreshes both at expiry', async () => {
  let clock = 0
  const calls = []
  const sign = createWechatSigner({
    appId: 'app', appSecret: 'secret', now: () => clock,
    request: async (url) => {
      calls.push(url)
      return url.endsWith('stable_token')
        ? { access_token: 'token', expires_in: 7200 }
        : { errcode: 0, ticket: 'ticket', expires_in: 3600 }
    },
  })
  await sign(`${origin}/`)
  clock = 3_301_000
  await sign(`${origin}/`)
  assert.equal(calls.length, 3)
  assert.ok(calls[2].endsWith('ticket/getticket'))
  clock = 6_901_000
  await sign(`${origin}/`)
  assert.equal(calls.length, 5)
  assert.ok(calls[3].endsWith('stable_token'))
})

test('upstream failures cool down and never forward credential-bearing errors', async () => {
  let clock = 0
  let calls = 0
  const sign = createWechatSigner({
    appId: 'app', appSecret: 'secret', now: () => clock,
    request: async () => { calls++; throw new Error('secret&access_token=private-token') },
  })
  await assert.rejects(sign(`${origin}/`), { message: 'WeChat temporarily unavailable' })
  await assert.rejects(sign(`${origin}/`), { message: 'WeChat temporarily unavailable' })
  assert.equal(calls, 1)
  clock = 60_001
  await assert.rejects(sign(`${origin}/`))
  assert.equal(calls, 2)
})

test('invalid tokens are discarded before retrying after cooldown', async () => {
  let clock = 0
  const calls = []
  const sign = createWechatSigner({
    appId: 'app', appSecret: 'secret', now: () => clock,
    request: async (url) => {
      calls.push(url)
      return url.endsWith('stable_token')
        ? { access_token: 'token', expires_in: 7200 }
        : { errcode: 40001, errmsg: 'invalid credential' }
    },
  })
  await assert.rejects(sign(`${origin}/`))
  clock = 60_001
  await assert.rejects(sign(`${origin}/`))
  assert.equal(calls.filter(url => url.endsWith('stable_token')).length, 2)
})

test('incomplete upstream credentials are rejected', async () => {
  for (const response of [{}, { access_token: 'token' }, { access_token: 'token', expires_in: -1 }]) {
    const sign = createWechatSigner({ appId: 'app', appSecret: 'secret', request: async () => response })
    await assert.rejects(sign(`${origin}/`), { message: 'WeChat temporarily unavailable' })
  }
})
