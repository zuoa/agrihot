const SHANGHAI = 'Asia/Shanghai'

export function shanghaiDateKey(iso) {
  if (!iso) return ''
  const s = String(iso)
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const dateOnly = s.match(/^(\d{4}-\d{2}-\d{2})/)
  if (dateOnly && !s.includes('T') && !s.includes(' ')) return dateOnly[1]
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: SHANGHAI,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso))
}

function dateParts(iso) {
  const key = shanghaiDateKey(iso)
  const [y, m, d] = key.split('-').map(Number)
  return { y, m, d }
}

export function fmtDay(iso) {
  if (!iso) return ''
  const { m, d } = dateParts(iso)
  const key = shanghaiDateKey(iso)
  const [y, month, day] = key.split('-').map(Number)
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][
    new Date(Date.UTC(y, month - 1, day)).getUTCDay()
  ]
  return `${m}月${d}日 · ${week}`
}

export function fmtDateKey(iso) {
  return shanghaiDateKey(iso || new Date())
}

export function fmtTime(iso) {
  if (!iso) return ''
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: SHANGHAI,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date(iso))
  const get = (type) => parts.find((p) => p.type === type)?.value
  return `${get('hour')}:${get('minute')}`
}

export function groupByDay(items) {
  const groups = []
  const map = new Map()
  for (const it of items) {
    const key = shanghaiDateKey(it.created_at || it.published_at)
    if (!map.has(key)) {
      const g = { key, label: fmtDay(it.created_at || it.published_at), items: [] }
      map.set(key, g)
      groups.push(g)
    }
    map.get(key).items.push(it)
  }
  return groups
}
