export const SITE_NAME = 'AgriHot'
export const DEFAULT_TITLE = 'AgriHot · 农业信息化动态聚合'
export const DEFAULT_DESC =
  '农业信息化资讯聚合：政策、报道、学术论文每日精选与农业农村日报。覆盖智慧农业、数字乡村与农业农村政策。'
export const DEFAULT_KEYWORDS = ['农业信息化', '智慧农业', '数字乡村', '农业农村日报', '农业政策', '农业论文']
export const FALLBACK_ORIGIN = 'https://agrihot.com'

export function siteOrigin(origin) {
  return String(origin || FALLBACK_ORIGIN).replace(/\/$/, '')
}

export function absUrl(path = '/', origin) {
  const base = siteOrigin(origin)
  if (!path || path === '/') return `${base}/`
  if (/^https?:\/\//.test(path)) return path
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

export function defaultImage(origin) {
  return `${siteOrigin(origin)}/og-image.png`
}

export function clip(text, n = 160) {
  const t = String(text || '').replace(/\s+/g, ' ').trim()
  if (t.length <= n) return t
  return `${t.slice(0, n - 1)}…`
}

export function uniqueKeywords(parts, limit = 10) {
  const seen = new Set()
  const out = []
  const walk = (value) => {
    if (out.length >= limit || value == null || value === false) return
    if (Array.isArray(value)) {
      value.forEach(walk)
      return
    }
    const k = String(value).trim()
    if (!k) return
    const key = k.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    out.push(k)
  }
  walk(parts)
  return out
}

function tagNames(item) {
  return (item?.tags || []).map((t) => (typeof t === 'string' ? t : t?.name)).filter(Boolean)
}

export function itemKeywords(item) {
  return uniqueKeywords([
    item?.search_phrases,
    tagNames(item),
    item?.category,
    item?.paper?.direction,
    item?.category === '论文' || item?.paper ? '农业论文' : '',
    '农业信息化',
  ])
}

export function tagPath(name) {
  return `/tags/${encodeURIComponent(name)}`
}

export function decodeTagName(raw) {
  let s = String(raw ?? '').replace(/\+/g, ' ')
  for (let i = 0; i < 4; i++) {
    if (!/%[0-9A-Fa-f]{2}/.test(s)) break
    try {
      const next = decodeURIComponent(s)
      if (next === s) break
      s = next
    } catch {
      break
    }
  }
  return s.trim()
}

export function topicJsonLd(topic, origin) {
  const path = tagPath(topic.name)
  const tokens = topic.tokens || []
  const desc = topic.kind === 'phrase'
    ? `与「${tokens.join('、')}」同时相关的农业资讯，共 ${topic.total} 条。`
    : `农业信息化主题「${topic.name}」相关资讯与论文，共 ${topic.total} 条。`
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: topic.name,
    description: clip(desc, 300),
    url: absUrl(path, origin),
    isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: absUrl('/', origin) },
    keywords: uniqueKeywords([topic.name, tokens, '农业信息化']).join(','),
    hasPart: (topic.items || []).slice(0, 20).map((it) => ({
      '@type': 'Article',
      name: it.title,
      url: absUrl(`/items/${it.id}`, origin),
    })),
  }
}

export function dailyKeywords(daily) {
  const items = daily?.items || []
  return uniqueKeywords([
    '农业农村日报',
    items.flatMap(tagNames),
    items.map((it) => it.category),
    '农业信息化',
  ])
}

export function websiteJsonLd(origin) {
  const root = absUrl('/', origin)
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${root}#org`,
        name: SITE_NAME,
        url: root,
        logo: absUrl('/apple-touch-icon.png', origin),
      },
      {
        '@type': 'WebSite',
        '@id': `${root}#website`,
        url: root,
        name: SITE_NAME,
        description: DEFAULT_DESC,
        inLanguage: 'zh-CN',
        publisher: { '@id': `${root}#org` },
        potentialAction: {
          '@type': 'SearchAction',
          target: `${absUrl('/feed', origin)}?q={search_term_string}`,
          'query-input': 'required name=search_term_string',
        },
      },
    ],
  }
}

export function itemJsonLd(item, origin) {
  const path = `/items/${item.id}`
  const isPaper = item.category === '论文' || item.paper
  const authors = (item.paper?.authors || [])
    .filter((a) => a?.name)
    .map((a) => ({ '@type': 'Person', name: a.name }))
  const article = {
    '@type': isPaper ? 'ScholarlyArticle' : 'NewsArticle',
    headline: item.title,
    description: clip(item.summary_zh || item.summary, 300),
    url: absUrl(path, origin),
    mainEntityOfPage: absUrl(path, origin),
    image: item.cover_url || defaultImage(origin),
    datePublished: item.published_at || item.created_at,
    dateModified: item.created_at,
    inLanguage: 'zh-CN',
    isAccessibleForFree: true,
    publisher: {
      '@type': 'Organization',
      name: SITE_NAME,
      url: absUrl('/', origin),
      logo: { '@type': 'ImageObject', url: absUrl('/apple-touch-icon.png', origin) },
    },
    author: authors.length ? authors : { '@type': 'Organization', name: item.source_name || SITE_NAME },
    keywords: itemKeywords(item).join(','),
    articleSection: item.category || undefined,
    about: tagNames(item).map((name) => ({ '@type': 'Thing', name })),
  }
  if (item.doi) {
    article.identifier = `https://doi.org/${item.doi}`
    article.sameAs = `https://doi.org/${item.doi}`
  }
  if (item.paper?.venue) {
    article.isPartOf = { '@type': 'Periodical', name: item.paper.venue }
  }
  return {
    '@context': 'https://schema.org',
    '@graph': [
      article,
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: '首页', item: absUrl('/', origin) },
          {
            '@type': 'ListItem',
            position: 2,
            name: item.category || '资讯',
            item: item.category ? `${absUrl('/feed', origin)}?category=${encodeURIComponent(item.category)}` : absUrl('/feed', origin),
          },
          { '@type': 'ListItem', position: 3, name: item.title, item: absUrl(path, origin) },
        ],
      },
    ],
  }
}

export function dailyJsonLd(daily, origin) {
  const path = `/dailies/${daily.date}`
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: daily.title,
    description: clip((daily.highlights || []).join(' ') || daily.content || daily.title, 300),
    url: absUrl(path, origin),
    datePublished: daily.date,
    isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: absUrl('/', origin) },
    hasPart: (daily.items || []).slice(0, 20).map((it) => ({
      '@type': 'Article',
      name: it.title,
      url: absUrl(`/items/${it.id}`, origin),
    })),
    keywords: dailyKeywords(daily).join(','),
  }
}
