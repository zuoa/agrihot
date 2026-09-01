<template>
  <div class="bg-white rounded-2xl border border-leaf-100 p-6 sm:p-8 space-y-6">
    <h1 class="text-2xl font-bold text-stone-900">关于 AgriHot</h1>
    <p class="text-sm text-stone-600 leading-7">
      AgriHot 是一个农业信息化资讯聚合站：聚合农业农村政策、行业报道与农业信息化学术论文，
      每日生成《农业农村日报》。内容主要由爬虫 Agent 通过
      <router-link to="/agent" class="text-leaf-700 hover:underline">开放推送接口</router-link>
      提交，服务层自动去重（URL 精确 + 标题相似），多信源报道自动合并。
    </p>
    <section class="rounded-xl bg-leaf-50 border border-leaf-100 p-4 sm:p-5">
      <div class="flex items-baseline justify-between gap-3 mb-3">
        <h2 class="text-sm font-bold text-leaf-800">汇聚数据</h2>
        <p v-if="sinceLabel" class="text-xs text-stone-400">自 {{ sinceLabel }} 起</p>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <component
          v-for="c in cards"
          :key="c.label"
          :is="c.to ? 'router-link' : 'div'"
          :to="c.to"
          :aria-label="c.to ? `查看${c.aria}` : undefined"
          class="rounded-xl bg-white border border-leaf-100 px-3 py-3.5 text-center"
          :class="c.to ? 'hover:border-leaf-300 hover:bg-leaf-50/80 transition-colors' : ''"
        >
          <div class="text-2xl font-bold tabular-nums text-leaf-800 leading-none">{{ fmtNum(c.value) }}</div>
          <div class="text-xs text-stone-500 mt-1.5">{{ c.label }}</div>
        </component>
      </div>
    </section>
    <div class="grid sm:grid-cols-3 gap-3">
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-sm font-bold text-leaf-800">政策与报道</div>
        <div class="text-xs text-stone-500 mt-1.5 leading-5">部委文件、地方实践、行业动态</div>
      </div>
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-sm font-bold text-leaf-800">学术论文</div>
        <div class="text-xs text-stone-500 mt-1.5 leading-5">OpenAlex 日更订阅核心期刊与方向；外文摘要译为中文卡片</div>
      </div>
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-sm font-bold text-leaf-800">Agent 友好</div>
        <div class="text-xs text-stone-500 mt-1.5 leading-5">开放推送 API，去重后自动上线</div>
      </div>
    </div>
    <section class="border-t border-leaf-100 pt-5 space-y-4">
      <h2 class="text-base font-bold text-stone-900">联系我们</h2>
      <p class="text-sm text-stone-600 leading-7">
        内容纠错、来源下线、合作或建议，欢迎邮件或微信联系。
      </p>
      <div class="flex flex-col sm:flex-row sm:items-start gap-5">
        <div class="flex-1 space-y-4">
          <div>
            <div class="text-xs text-stone-400">邮箱</div>
            <a href="mailto:ijedyu@gmail.com" class="mt-1 inline-block text-sm font-medium text-leaf-700 hover:underline break-all">ijedyu@gmail.com</a>
          </div>
          <div>
            <div class="text-xs text-stone-400">微信</div>
            <p class="mt-1 text-sm text-stone-600">扫码添加 ZUOAJ，备注来意即可</p>
          </div>
        </div>
        <figure class="shrink-0 mx-auto sm:mx-0">
          <a :href="wechatQr" target="_blank" rel="noopener" class="block" title="查看大图">
            <img
              :src="wechatQr"
              alt="微信二维码，扫码添加 ZUOAJ"
              width="958"
              height="1415"
              class="w-52 sm:w-56 rounded-xl border border-leaf-100 bg-white hover:border-leaf-300 transition-colors"
            />
          </a>
        </figure>
      </div>
    </section>
    <p class="text-xs text-stone-400 leading-5 border-t border-leaf-100 pt-4">
      免责声明：本站内容整理自公开来源，学术论文元数据来自
      <a href="https://openalex.org/" class="text-leaf-600 hover:underline" target="_blank" rel="noopener">OpenAlex</a>
      等开放接口，摘要与翻译由 AI 生成，仅供参考；引用与决策请以官方原文与正式出版物为准。
      如涉及来源方权益问题，请邮件联系
      <a href="mailto:ijedyu@gmail.com" class="text-leaf-600 hover:underline">ijedyu@gmail.com</a>
      更正或下线。
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import wechatQr from '../assets/wechat-qr.png'

const stats = ref(null)

onMounted(async () => {
  try {
    stats.value = await api.stats()
  } catch {
    stats.value = null
  }
})

function cat(name) {
  return stats.value?.by_category?.[name] ?? 0
}

function fmtNum(n) {
  if (n == null || !stats.value) return '—'
  return Number(n).toLocaleString('zh-CN')
}

const sinceLabel = computed(() => {
  if (!stats.value?.since) return ''
  const d = new Date(stats.value.since)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}年${d.getMonth() + 1}月`
})

const cards = computed(() => {
  const s = stats.value
  return [
    { label: '条资讯', aria: '全部资讯', value: s?.items, to: '/feed' },
    { label: '份政策', aria: '政策', value: cat('政策'), to: { path: '/feed', query: { category: '政策' } } },
    { label: '条报道', aria: '报道', value: cat('报道'), to: { path: '/feed', query: { category: '报道' } } },
    { label: '篇论文', aria: '论文', value: cat('论文'), to: { path: '/feed', query: { category: '论文' } } },
    { label: '条行业', aria: '行业动态', value: cat('行业'), to: { path: '/feed', query: { category: '行业' } } },
    { label: '期日报', aria: '农业日报', value: s?.dailies, to: '/dailies' },
    { label: '家信源', aria: '信源', value: s?.sources, to: null },
    { label: '个主题', aria: '主题', value: s?.tags, to: '/tags' },
  ]
})
</script>
