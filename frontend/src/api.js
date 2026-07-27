const BASE = '/api/v1'

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

export const api = {
  items: (params) => get('/items', params),
  item: (id) => get(`/items/${id}`),
  tags: () => get('/tags'),
  dailies: (params) => get('/dailies', params),
  latestDaily: () => get('/dailies/latest'),
  daily: (date) => get(`/dailies/${date}`),
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

/** group items by calendar day, newest first */
export function groupByDay(items) {
  const groups = []
  const map = new Map()
  for (const it of items) {
    const key = fmtDateKey(it.published_at || it.created_at)
    if (!map.has(key)) {
      const g = { key, label: fmtDay(it.published_at || it.created_at), items: [] }
      map.set(key, g)
      groups.push(g)
    }
    map.get(key).items.push(it)
  }
  return groups
}
