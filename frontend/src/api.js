const BASE = '/api/v1'

import { reactive } from 'vue'

async function get(path, params = {}) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v)
  }
  const url = qs.size ? `${BASE}${path}?${qs}` : `${BASE}${path}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ---------- admin session (token persisted in localStorage) ----------

const TOKEN_KEY = 'agrihot_admin_token'

export const adminSession = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  get loggedIn() { return !!this.token },
  set(token) { this.token = token; localStorage.setItem(TOKEN_KEY, token) },
  clear() { this.token = ''; localStorage.removeItem(TOKEN_KEY) },
})

async function adminFetch(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminSession.token,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    adminSession.clear()
    throw new Error('登录已失效，请重新登录')
  }
  if (!res.ok) {
    let detail = `API ${res.status}`
    try { detail = (await res.json()).detail?.detail || detail } catch { /* keep default */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  items: (params) => get('/items', params),
  item: (id) => get(`/items/${id}`),
  tags: () => get('/tags'),
  dailies: (params) => get('/dailies', params),
  latestDaily: () => get('/dailies/latest'),
  daily: (date) => get(`/dailies/${date}`),
  // admin
  adminLogin: async (password) => {
    const res = await fetch(`${BASE}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    if (!res.ok) {
      let detail = '密码错误'
      try { detail = (await res.json()).detail?.detail || detail } catch { /* keep default */ }
      throw new Error(detail)
    }
    const data = await res.json()
    adminSession.set(data.token)
    return data
  },
  adminUpdateItem: (id, patch) => adminFetch(`/admin/items/${id}`, { method: 'PATCH', body: patch }),
  adminDeleteItem: (id) => adminFetch(`/admin/items/${id}`, { method: 'DELETE' }),
}

export function fmtDay(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
  return `${d.getMonth() + 1}月${d.getDate()}日 · ${week}`
}

export function fmtDateKey(iso) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** group items by calendar day, newest first (by ingest time, not original publish date) */
export function groupByDay(items) {
  const groups = []
  const map = new Map()
  for (const it of items) {
    const key = fmtDateKey(it.created_at || it.published_at)
    if (!map.has(key)) {
      const g = { key, label: fmtDay(it.created_at || it.published_at), items: [] }
      map.set(key, g)
      groups.push(g)
    }
    map.get(key).items.push(it)
  }
  return groups
}
