<template>
  <div class="min-h-screen flex flex-col bg-leaf-50/60">
    <header class="bg-white border-b border-leaf-100">
      <div class="max-w-3xl mx-auto px-4 py-3">
        <NuxtLink to="/" class="font-bold text-leaf-800">AgriHot</NuxtLink>
      </div>
    </header>
    <main class="flex-1 max-w-3xl mx-auto w-full px-4 py-16 text-center">
      <h1 class="text-xl font-bold text-stone-900">{{ heading }}</h1>
      <p class="mt-3 text-sm text-stone-500">{{ error?.statusMessage || '这条内容可能已下线。' }}</p>
      <div class="mt-6 flex justify-center gap-3 text-sm">
        <NuxtLink to="/" class="px-4 py-2 rounded-full bg-leaf-600 text-white">返回首页</NuxtLink>
        <NuxtLink to="/dailies" class="px-4 py-2 rounded-full border border-leaf-200 text-leaf-700">农业日报</NuxtLink>
      </div>
    </main>
  </div>
</template>

<script setup>
const props = defineProps({ error: { type: Object, default: null } })
const heading = computed(() => (props.error?.statusCode === 404 ? '页面不存在' : '出错了'))

usePageSeo(() => ({
  title: `${heading.value} · AgriHot`,
  description: DEFAULT_DESC,
  path: '/',
  noindex: true,
}))
</script>
