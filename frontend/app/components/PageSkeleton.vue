<template>
  <div role="status" aria-live="polite" aria-busy="true">
    <span class="sr-only">{{ label }}</span>
    <div v-if="variant === 'article'" aria-hidden="true" class="rounded-2xl border border-leaf-100 bg-white p-6 sm:p-8">
      <div class="skeleton-block h-3 w-32 mb-5"></div>
      <div class="skeleton-block h-7 w-5/6 mb-3"></div>
      <div class="skeleton-block h-7 w-2/3 mb-8"></div>
      <div v-for="n in 3" :key="n" class="space-y-3 mb-7">
        <div class="skeleton-block h-3 w-full"></div>
        <div class="skeleton-block h-3 w-full"></div>
        <div class="skeleton-block h-3 w-4/5"></div>
      </div>
    </div>
    <div v-else-if="variant === 'tags'" aria-hidden="true" class="flex flex-wrap gap-2.5">
      <div v-for="n in 18" :key="n" class="skeleton-block h-10 rounded-full" :class="n % 3 === 0 ? 'w-32' : 'w-24'"></div>
    </div>
    <div v-else aria-hidden="true" :class="variant === 'grid' ? 'grid sm:grid-cols-2 gap-4' : 'space-y-3'">
      <div v-for="n in (variant === 'grid' ? 4 : 3)" :key="n" class="rounded-xl border border-leaf-100 bg-white p-5">
        <div class="skeleton-block h-3 w-24 mb-4"></div>
        <div class="skeleton-block h-5 w-4/5 mb-3"></div>
        <div class="skeleton-block h-3 w-full mb-2"></div>
        <div class="skeleton-block h-3 w-2/3 mb-4"></div>
        <div class="flex gap-2">
          <div class="skeleton-block h-5 w-16 rounded-full"></div>
          <div class="skeleton-block h-5 w-20 rounded-full"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'list' },
  label: { type: String, default: '正在加载内容…' },
})
</script>

<style scoped>
.skeleton-block {
  @apply rounded bg-leaf-100/70;
}

.skeleton-block.rounded-full { border-radius: 9999px; }

@media (prefers-reduced-motion: no-preference) {
  .skeleton-block { animation: skeleton-pulse 1.6s ease-in-out infinite; }
}

@keyframes skeleton-pulse {
  50% { opacity: 0.45; }
}
</style>
