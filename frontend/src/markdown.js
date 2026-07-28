/** Markdown rendering for item full text: markdown-it + DOMPurify (XSS-safe). */
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

// images are proxied through wsrv.nl: source sites often block hotlinking
// (Referer checks), which would break <img> loading from our domain
const IMAGE_PROXY = 'https://wsrv.nl/?url='

function proxyImageSrc(src) {
  if (!src || src.startsWith('data:') || src.startsWith(IMAGE_PROXY)) return src
  // relative URLs can't be proxied (no way to resolve the host here)
  if (!/^https?:\/\//i.test(src)) return src
  return IMAGE_PROXY + encodeURIComponent(src)
}

const md = new MarkdownIt({
  html: false, // raw HTML is escaped, not passed through
  linkify: true,
  breaks: true, // single \n -> <br>, matches how plain-text full text is stored
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

// external links open in a new tab
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(md.render(text))
}
