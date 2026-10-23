export function usePageSeo(source) {
  const config = useRuntimeConfig()
  const origin = computed(() => String(config.public.siteUrl || FALLBACK_ORIGIN).replace(/\/$/, ''))

  const state = computed(() => {
    const s = (typeof source === 'function' ? source() : toValue(source)) || {}
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
    share.value = { title: s.fullTitle, desc: s.desc, link: s.url, imgUrl: s.shareImg }
  }, { immediate: true })

  useSeoMeta({
    title: () => state.value.fullTitle,
    description: () => state.value.desc,
    keywords: () => state.value.kw,
    robots: () => state.value.robots,
    ogTitle: () => state.value.fullTitle,
    ogDescription: () => state.value.desc,
    ogUrl: () => state.value.url,
    ogType: () => state.value.type,
    ogImage: () => state.value.img,
    ogImageAlt: () => state.value.fullTitle,
    ogImageWidth: () => state.value.defaultImg ? 1200 : undefined,
    ogImageHeight: () => state.value.defaultImg ? 630 : undefined,
    ogSiteName: SITE_NAME,
    ogLocale: 'zh_CN',
    twitterCard: 'summary_large_image',
    twitterTitle: () => state.value.fullTitle,
    twitterImage: () => state.value.img,
    twitterDescription: () => state.value.desc,
  })

  useHead(() => ({
    link: [
      { rel: 'canonical', href: state.value.url },
      { rel: 'image_src', href: state.value.shareImg },
    ],
    meta: state.value.extra,
    script: state.value.jsonLd
      ? [{
          type: 'application/ld+json',
          innerHTML: JSON.stringify(state.value.jsonLd).replace(/</g, '\\u003c'),
          tagPriority: 20,
        }]
      : [],
  }))
}
