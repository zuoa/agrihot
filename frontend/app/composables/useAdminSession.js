const TOKEN_KEY = 'agrihot_admin_token'

export function useAdminSession() {
  const token = useState('admin-token', () => '')

  function hydrateFromStorage() {
    if (!import.meta.client) return
    token.value = localStorage.getItem(TOKEN_KEY) || ''
  }

  return {
    token,
    loggedIn: computed(() => !!token.value),
    hydrateFromStorage,
    set(value) {
      token.value = value
      if (import.meta.client) localStorage.setItem(TOKEN_KEY, value)
    },
    clear() {
      token.value = ''
      if (import.meta.client) localStorage.removeItem(TOKEN_KEY)
    },
  }
}

/** Admin chrome that would mismatch SSR HTML if read from localStorage during hydration. */
export function useClientAdmin() {
  const session = useAdminSession()
  const mounted = ref(false)
  onMounted(() => {
    session.hydrateFromStorage()
    mounted.value = true
  })
  return computed(() => mounted.value && session.loggedIn.value)
}
