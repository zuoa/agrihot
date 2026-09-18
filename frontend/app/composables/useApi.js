function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') search.set(k, v)
  }
  return search
}

export function useApi() {
  const config = useRuntimeConfig()
  const session = useAdminSession()
  const prefix = () => (import.meta.server ? config.apiBase : '')

  async function get(path, params = {}) {
    const query = qs(params)
    const url = query.size ? `${prefix()}/api/v1${path}?${query}` : `${prefix()}/api/v1${path}`
    return await $fetch(url)
  }

  async function post(path) {
    return await $fetch(`${prefix()}/api/v1${path}`, { method: 'POST' })
  }

  async function adminFetch(path, { method = 'GET', body, params } = {}) {
    const query = params ? qs(params) : new URLSearchParams()
    const url = query.size ? `${prefix()}/api/v1${path}?${query}` : `${prefix()}/api/v1${path}`
    try {
      return await $fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Token': session.token.value,
        },
        body,
      })
    } catch (err) {
      if (err?.statusCode === 401 || err?.status === 401) {
        session.clear()
        throw new Error('登录已失效，请重新登录')
      }
      const detail = err?.data?.detail?.detail || err?.data?.detail || err?.message || `API ${err?.statusCode || ''}`
      throw new Error(typeof detail === 'string' ? detail : '请求失败')
    }
  }

  return {
    items: (params) => get('/items', params),
    item: (id) => get(`/items/${id}`),
    related: (id) => get(`/items/${id}/related`),
    recordView: (id) => post(`/items/${id}/view`),
    tags: () => get('/tags'),
    topic: (name, params = {}) => get('/topics', { name, ...params }),
    paperDirections: () => get('/paper-directions'),
    stats: () => get('/stats'),
    dailies: (params) => get('/dailies', params),
    latestDaily: () => get('/dailies/latest'),
    daily: (date) => get(`/dailies/${date}`),
    adminLogin: async (password) => {
      try {
        const data = await $fetch(`${prefix()}/api/v1/admin/login`, {
          method: 'POST',
          body: { password },
        })
        session.set(data.token)
        return data
      } catch (err) {
        const detail = err?.data?.detail?.detail || err?.data?.detail
        throw new Error(typeof detail === 'string' ? detail : '密码错误')
      }
    },
    adminUpdateItem: (id, patch) => adminFetch(`/admin/items/${id}`, { method: 'PATCH', body: patch }),
    adminDeleteItem: (id) => adminFetch(`/admin/items/${id}`, { method: 'DELETE' }),
    adminFetchContent: (id) => adminFetch(`/admin/items/${id}/fetch-content`, { method: 'POST' }),
    adminGenerateDaily: (date) => adminFetch(`/admin/dailies/${date}/generate`, { method: 'POST' }),
    adminMe: () => adminFetch('/admin/me'),
    adminOverview: () => adminFetch('/admin/overview'),
    adminItems: (params) => adminFetch('/admin/items', { params }),
    adminRescoreItem: (id) => adminFetch(`/admin/items/${id}/rescore`, { method: 'POST' }),
    adminBatchDelete: (ids) => adminFetch('/admin/items/batch-delete', { method: 'POST', body: { ids } }),
    adminBatchFetch: (ids, force = false) =>
      adminFetch('/admin/items/batch-fetch-content', { method: 'POST', body: { ids, force } }),
    adminJobs: () => adminFetch('/admin/jobs'),
    adminRunJob: (name, body = {}) => adminFetch(`/admin/jobs/${name}/run`, { method: 'POST', body }),
    adminSettings: () => adminFetch('/admin/settings'),
    adminPatchSettings: (patch) => adminFetch('/admin/settings', { method: 'PATCH', body: patch }),
    adminWatchlist: () => adminFetch('/admin/watchlist'),
    adminPutWatchlist: (data) => adminFetch('/admin/watchlist', { method: 'PUT', body: data }),
    adminApiKeys: () => adminFetch('/admin/api-keys'),
    adminCreateApiKey: (name) => adminFetch('/admin/api-keys', { method: 'POST', body: { name } }),
    adminPatchApiKey: (id, patch) => adminFetch(`/admin/api-keys/${id}`, { method: 'PATCH', body: patch }),
  }
}
