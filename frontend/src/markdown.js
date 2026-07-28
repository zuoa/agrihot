/** Markdown rendering for item full text: markdown-it + DOMPurify (XSS-safe). */
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false, // raw HTML is escaped, not passed through
  linkify: true,
  breaks: true, // single \n -> <br>, matches how plain-text full text is stored
})

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
