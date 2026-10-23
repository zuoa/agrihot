import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'

const source = (await readFile(new URL('../app/plugins/wechat-share.client.js', import.meta.url), 'utf8'))
  .replace('export default defineNuxtPlugin', 'defineNuxtPlugin')
const origin = 'https://agrihot.com'
const drain = () => new Promise(resolve => setImmediate(resolve))

function client(userAgent, { enabled = true, request } = {}) {
  const entryUrl = `${origin}/?from=timeline#intro`
  const share = { value: { title: '首页', desc: '简介', link: `${origin}/`, imgUrl: `${origin}/share-icon.png` } }
  const route = { value: { path: '/', fullPath: '/' } }
  const requests = []
  const configs = []
  const messages = []
  const timelines = []
  let watcher
  let mount
  let ready = false
  let onReady
  const wx = {
    error() {},
    config(value) {
      ready = false
      configs.push(value)
      queueMicrotask(() => { ready = true; onReady?.() })
    },
    ready(fn) { onReady = fn; if (ready) fn() },
    updateAppMessageShareData(value) {
      assert.ok(ready, 'share data must wait for the current config to be ready')
      messages.push(value)
    },
    updateTimelineShareData(value) { assert.ok(ready); timelines.push(value) },
  }
  const window = { wx, location: { href: entryUrl } }
  vm.runInNewContext(source, {
    window, navigator: { userAgent }, setTimeout, clearTimeout,
    console: { warn() {} },
    useRouter: () => ({ currentRoute: route }),
    useState: () => share,
    watch: (_, callback) => { watcher = callback; callback() },
    defineNuxtPlugin: fn => fn({ hook: (_, callback) => { mount = callback } }),
    $fetch: async (_, options) => {
      requests.push(options.query.url)
      if (request) await request()
      return { enabled, appId: 'app', nonceStr: 'nonce', timestamp: 1, signature: 'signature' }
    },
  })
  mount?.()
  return {
    requests, configs, messages, timelines,
    navigate(id) {
      route.value = { path: `/items/${id}`, fullPath: `/items/${id}` }
      window.location.href = `${origin}/items/${id}`
      share.value = { title: `文章 ${id}`, desc: '摘要', link: window.location.href, imgUrl: `${origin}/cover-${id}.png` }
      watcher?.()
    },
  }
}

test('ordinary browsers never request WeChat configuration', async () => {
  const c = client('Chrome')
  await drain()
  assert.equal(c.requests.length, 0)
})

test('disabled accounts never configure the SDK', async () => {
  const c = client('MicroMessenger Android', { enabled: false })
  await drain()
  assert.equal(c.requests.length, 1)
  assert.equal(c.configs.length, 0)
  assert.equal(c.timelines.length, 0)
})

test('iOS keeps the entry URL signature while updating article title, link and image', async () => {
  const c = client('iPhone MicroMessenger')
  await drain()
  c.navigate(1)
  await drain()
  assert.deepEqual(c.requests, [`${origin}/?from=timeline`])
  assert.equal(c.configs.length, 1)
  assert.equal(c.messages.at(-1).desc, '摘要')
  assert.equal(c.timelines.at(-1).title, '文章 1')
  assert.equal(c.timelines.at(-1).link, `${origin}/items/1`)
  assert.equal(c.timelines.at(-1).imgUrl, `${origin}/cover-1.png`)
})

test('Android signs each current URL and waits for reconfiguration before sharing', async () => {
  const c = client('Android MicroMessenger')
  await drain()
  c.navigate(2)
  await drain()
  assert.deepEqual(c.requests, [`${origin}/?from=timeline`, `${origin}/items/2`])
  assert.equal(c.configs.length, 2)
  assert.equal(c.timelines.at(-1).title, '文章 2')
})

test('a slow previous page cannot replace the latest page share data', async () => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const c = client('Android MicroMessenger', { request: () => pending })
  await drain()
  c.navigate(3)
  release()
  await drain()
  assert.equal(c.configs.length, 1)
  assert.equal(c.timelines.length, 1)
  assert.equal(c.timelines[0].title, '文章 3')
  assert.equal(c.timelines[0].link, `${origin}/items/3`)
})
