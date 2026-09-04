export const SITE_URL = 'https://agrihot.com'
export const SITE_NAME = 'AgriHot'
export const DEFAULT_TITLE = 'AgriHot · 农业信息化动态聚合'
export const DEFAULT_DESC = '农业信息化资讯聚合：政策、报道、学术论文每日精选与农业农村日报。覆盖智慧农业、数字乡村与农业农村政策。'
export const DEFAULT_IMAGE = `${SITE_URL}/og-image.png`

export function clip(text, n = 160) {
  const t = String(text || '').replace(/\s+/g, ' ').trim()
  if (t.length <= n) return t
  return `${t.slice(0, n - 1)}…`
}

function absUrl(path = '/') {
  if (!path || path === '/') return `${SITE_URL}/`
  if (/^https?:\/\//.test(path)) return path
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

function upsertEl(selector, tag, attrs) {
  let el = document.head.querySelector(selector)
  if (!el) {
    el = document.createElement(tag)
    document.head.appendChild(el)
  }
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  return el
}

function setName(name, content) {
  upsertEl(`meta[name="${name}"]`, 'meta', { name, content })
}

function setProp(property, content) {
  upsertEl(`meta[property="${property}"]`, 'meta', { property, content })
}

export function setPageMeta({
  title,
  description,
  path = '/',
  image,
  type = 'website',
  noindex = false,
  jsonLd = null,
} = {}) {
  const fullTitle = title || DEFAULT_TITLE
  const desc = clip(description || DEFAULT_DESC)
  const url = absUrl(path)
  const img = image || DEFAULT_IMAGE
  document.title = fullTitle
  setName('description', desc)
  setName('robots', noindex ? 'noindex, nofollow' : 'index, follow')
  setProp('og:title', fullTitle)
  setProp('og:description', desc)
  setProp('og:url', url)
  setProp('og:type', type)
  setProp('og:image', img)
  setProp('og:site_name', SITE_NAME)
  setProp('og:locale', 'zh_CN')
  setName('twitter:card', 'summary_large_image')
  setName('twitter:title', fullTitle)
  setName('twitter:description', desc)
  setName('twitter:image', img)
  upsertEl('link[rel="canonical"]', 'link', { rel: 'canonical', href: url })
  const existing = document.getElementById('ld-json')
  if (jsonLd) {
    const el = existing || document.createElement('script')
    el.type = 'application/ld+json'
    el.id = 'ld-json'
    el.textContent = JSON.stringify(jsonLd)
    if (!existing) document.head.appendChild(el)
  } else if (existing) {
    existing.remove()
  }
}

export function websiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${SITE_URL}/#org`,
        name: SITE_NAME,
        url: `${SITE_URL}/`,
        logo: `${SITE_URL}/apple-touch-icon.png`,
      },
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}/#website`,
        url: `${SITE_URL}/`,
        name: SITE_NAME,
        description: DEFAULT_DESC,
        inLanguage: 'zh-CN',
        publisher: { '@id': `${SITE_URL}/#org` },
        potentialAction: {
          '@type': 'SearchAction',
          target: `${SITE_URL}/feed?q={search_term_string}`,
          'query-input': 'required name=search_term_string',
        },
      },
    ],
  }
}

export function itemJsonLd(item) {
  const path = `/items/${item.id}`
  const isPaper = item.category === '论文' || item.paper
  const authors = (item.paper?.authors || [])
    .filter((a) => a?.name)
    .map((a) => ({ '@type': 'Person', name: a.name }))
  const article = {
    '@type': isPaper ? 'ScholarlyArticle' : 'NewsArticle',
    headline: item.title,
    description: clip(item.summary_zh || item.summary, 300),
    url: absUrl(path),
    mainEntityOfPage: absUrl(path),
    image: item.cover_url || DEFAULT_IMAGE,
    datePublished: item.published_at || item.created_at,
    dateModified: item.created_at,
    inLanguage: 'zh-CN',
    isAccessibleForFree: true,
    publisher: {
      '@type': 'Organization',
      name: SITE_NAME,
      url: `${SITE_URL}/`,
      logo: { '@type': 'ImageObject', url: `${SITE_URL}/apple-touch-icon.png` },
    },
    author: authors.length ? authors : { '@type': 'Organization', name: item.source_name || SITE_NAME },
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
          { '@type': 'ListItem', position: 1, name: '首页', item: `${SITE_URL}/` },
          {
            '@type': 'ListItem',
            position: 2,
            name: item.category || '资讯',
            item: item.category ? `${SITE_URL}/feed?category=${encodeURIComponent(item.category)}` : `${SITE_URL}/feed`,
          },
          { '@type': 'ListItem', position: 3, name: item.title, item: absUrl(path) },
        ],
      },
    ],
  }
}

export function dailyJsonLd(daily) {
  const path = `/dailies/${daily.date}`
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: daily.title,
    description: clip((daily.highlights || []).join(' ') || daily.content || daily.title, 300),
    url: absUrl(path),
    datePublished: daily.date,
    isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${SITE_URL}/` },
    hasPart: (daily.items || []).slice(0, 20).map((it) => ({
      '@type': 'Article',
      name: it.title,
      url: absUrl(`/items/${it.id}`),
    })),
  }
}
