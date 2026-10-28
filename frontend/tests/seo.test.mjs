import assert from 'node:assert/strict'
import test from 'node:test'
import { itemJsonLd } from '../app/utils/seo.js'

const item = {
  id: 7,
  title: '智慧农业指导意见',
  summary: '摘要',
  category: '政策',
  tags: ['智慧农业'],
  source_name: '示例',
  published_at: '2026-09-02T00:00:00Z',
  created_at: '2026-09-01T00:00:00Z',
  primary_topic: { name: '数字农业', path: '/topic/digital' },
}

test('article schema follows the visible topic breadcrumb and skips an older modification date', () => {
  const graph = itemJsonLd(item, 'https://agrihot.com')['@graph']
  const article = graph.find((node) => node['@type'] === 'NewsArticle')
  assert.equal(article.dateModified, undefined)
  assert.equal(article.datePublished, item.published_at)
  const crumbs = graph.find((node) => node['@type'] === 'BreadcrumbList').itemListElement
  assert.deepEqual(crumbs.map((crumb) => crumb.name), ['首页', '数字农业', item.title])
  assert.equal(crumbs[1].item, 'https://agrihot.com/topic/digital')
})

test('article schema keeps a modification date only when it is later than publication', () => {
  const article = itemJsonLd({ ...item, created_at: '2026-09-03T00:00:00Z' }, 'https://agrihot.com')['@graph'][0]
  assert.equal(article.dateModified, '2026-09-03T00:00:00Z')
})
