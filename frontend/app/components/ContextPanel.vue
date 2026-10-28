<template>
  <section class="rounded-xl border border-leaf-100 bg-white p-4 space-y-4 text-sm">
    <div v-if="item.primary_topic || item.secondary_topics?.length">
      <div class="text-xs font-bold text-stone-500 mb-2">主题</div>
      <div class="flex flex-wrap gap-x-3 gap-y-1">
        <NuxtLink v-if="item.primary_topic" :to="item.primary_topic.path" class="text-leaf-800 font-medium hover:underline">{{ item.primary_topic.name }}</NuxtLink>
        <NuxtLink v-for="topic in item.secondary_topics || []" :key="topic.code" :to="topic.path" class="text-leaf-700 hover:underline">{{ topic.name }}</NuxtLink>
      </div>
    </div>
    <div>
      <div class="text-xs font-bold text-stone-500 mb-2">信源（{{ item.sources?.length || 1 }}）</div>
      <ul class="space-y-1.5">
        <li v-for="(source, index) in sources" :key="index">
          <a :href="source.url || item.url" target="_blank" rel="noopener" class="text-leaf-700 hover:underline [overflow-wrap:anywhere]">{{ source.name || '原文链接' }}</a>
        </li>
      </ul>
    </div>
    <div class="flex items-center justify-between gap-3 pt-1">
      <button type="button" class="text-xs text-leaf-700 hover:underline" @click="copyLink">复制本页链接</button>
      <EmbeddingBadge v-if="showAdmin && item.embedding_ready" />
    </div>
    <p v-if="copied" class="text-xs text-leaf-700" role="status">链接已复制</p>
  </section>
</template>

<script setup>
const props = defineProps({
  item: { type: Object, required: true },
})

const showAdmin = useClientAdmin()
const copied = ref(false)

const sources = computed(() => (
  props.item.sources?.length
    ? props.item.sources
    : [{ name: props.item.source_name, url: props.item.url }]
))

watch(() => props.item?.id, () => { copied.value = false })

async function copyLink() {
  const url = window.location.href
  try {
    await navigator.clipboard.writeText(url)
  } catch {
    const input = document.createElement('input')
    input.value = url
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    input.remove()
  }
  copied.value = true
}
</script>
