export function usePageSeo(source) {
  const config = useRuntimeConfig()
  const origin = computed(() => String(config.public.siteUrl || FALLBACK_ORIGIN).replace(/\/$/, ''))

  const state = computed(() => {
    const raw = typeof source === 'function' ? source() : toValue(source)
    if (!raw) return null
    const s = raw
    const o = origin.value
    const fullTitle = s.title || DEFAULT_TITLE
    const desc = clip(s.description || DEFAULT_DESC)
    const url = absUrl(s.path || '/', o)
    const img = absUrl(s.image || defaultImage(o), o)
    const shareImg = absUrl(s.shareImage || s.image || defaultShareImage(o), o)
    const kw = uniqueKeywords(s.keywords?.length ? s.keywords : DEFAULT_KEYWORDS).join(',')
    const robots = s.noindex ? 'noindex, nofollow' : 'index, follow'
    const extra = []
    if (s.type === 'article') {
      if (s.section) extra.push({ property: 'article:section', content: s.section })
      if (s.publishedTime) extra.push({ property: 'article:published_time', content: s.publishedTime })
      for (const tag of uniqueKeywords(s.tags || [], 8)) {
        extra.push({ property: 'article:tag', content: tag })
      }
    }
    const jsonLd = typeof s.jsonLd === 'function' ? s.jsonLd(o) : (s.jsonLd || null)
    return {
      fullTitle,
      desc,
      url,
      img,
      shareImg,
      defaultImg: !s.image,
      kw,
      robots,
      extra,
      jsonLd,
      type: s.type || 'website',
    }
  })

  // The SDK reads the same reactive page data as SEO, including after SPA navigation.
  const share = useState('page-share', () => null)
  watch(state, (s) => {
    share.value = s
      ? { title: s.fullTitle, desc: s.desc, link: s.url, imgUrl: s.shareImg }
      : null
  }, { immediate: true })

  const field = (key) => () => state.value?.[key]

  useSeoMeta({
    title: field('fullTitle'),
    description: field('desc'),
    keywords: field('kw'),
    robots: field('robots'),
    ogTitle: field('fullTitle'),
    ogDescription: field('desc'),
    ogUrl: field('url'),
    ogType: field('type'),
    ogImage: field('img'),
    ogImageAlt: field('fullTitle'),
    ogImageWidth: () => state.value?.defaultImg ? 1200 : undefined,
    ogImageHeight: () => state.value?.defaultImg ? 630 : undefined,
    ogSiteName: SITE_NAME,
    ogLocale: 'zh_CN',
    twitterCard: 'summary_large_image',
    twitterTitle: field('fullTitle'),
    twitterImage: field('img'),
    twitterDescription: field('desc'),
  })

  useHead(() => {
    const s = state.value
    if (!s) return {}
    return {
      link: [
        { rel: 'canonical', href: s.url },
        { rel: 'image_src', href: s.shareImg },
      ],
      meta: s.extra,
      script: s.jsonLd
        ? [{
            type: 'application/ld+json',
            innerHTML: JSON.stringify(s.jsonLd).replace(/</g, '\\u003c'),
            tagPriority: 20,
          }]
        : [],
    }
  })
}
