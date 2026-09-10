import MarkdownIt from 'markdown-it'

const IMAGE_PROXY = 'https://wsrv.nl/?url='

function proxyImageSrc(src) {
  if (!src || src.startsWith('data:') || src.startsWith(IMAGE_PROXY)) return src
  if (!/^https?:\/\//i.test(src)) return src
  return IMAGE_PROXY + encodeURIComponent(src)
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const defaultImageRule =
  md.renderer.rules.image ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const src = tokens[idx].attrGet('src')
  const proxied = proxyImageSrc(src)
  if (proxied !== src) tokens[idx].attrSet('src', proxied)
  tokens[idx].attrSet('loading', 'lazy')
  return defaultImageRule(tokens, idx, options, env, self)
}

const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(text) {
  if (!text) return ''
  return md.render(text)
}
