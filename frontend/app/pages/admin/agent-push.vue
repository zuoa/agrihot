<template>
  <section class="rounded-xl border border-stone-200 bg-white p-5 sm:p-7">
    <div class="mb-5 flex items-center justify-between gap-3"><h1 class="text-xl font-bold text-stone-900">Agent 推送接入</h1><NuxtLink to="/admin/keys" class="text-xs text-leaf-700 hover:underline">管理推送 Key ↗</NuxtLink></div>
    <p v-if="loading" class="py-6 text-sm text-stone-400">正在加载接入说明…</p>
    <p v-else-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <!-- Server-authenticated documentation; Markdown parser disables raw HTML. -->
    <div v-else class="prose-body min-w-0 overflow-x-auto text-sm" v-html="html" />
  </section>
</template>

<script setup>
definePageMeta({ layout: 'admin', title: 'Agent 推送接入', middleware: 'admin-auth' })
useHead({ meta: [{ name: 'robots', content: 'noindex, nofollow' }] })
const api = useApi()
const content = ref(''), loading = ref(true), error = ref('')
const html = computed(() => renderMarkdown(content.value))
onMounted(async () => {
  try { content.value = (await api.adminPushGuide()).content }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
})
</script>
