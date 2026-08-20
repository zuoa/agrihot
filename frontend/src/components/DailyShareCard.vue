<template>
  <!-- 分享卡片：固定 750px 宽，离屏渲染后经 html-to-image 转成 PNG。
       设计宽度即 2x 稿，导出时 pixelRatio=2 得到 1500px 宽高清图。 -->
  <div class="w-[750px] bg-white text-stone-800" style="font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif">
    <!-- 报头 -->
    <div class="bg-gradient-to-br from-leaf-700 to-leaf-900 px-12 pt-10 pb-8 text-white">
      <div class="flex items-center gap-3 text-leaf-200 text-xl tracking-wide">
        <span class="text-2xl">🌾</span><span>AgriHot · 农业信息化动态聚合</span>
      </div>
      <h1 class="mt-4 text-[44px] leading-tight font-bold">农业农村日报</h1>
      <div class="mt-2 text-2xl text-leaf-100">{{ dateLabel }}</div>
    </div>

    <!-- 今日要点 -->
    <div class="px-12 py-8">
      <div class="flex items-center gap-3 mb-6">
        <span class="w-9 h-9 rounded-lg bg-leaf-600 text-white grid place-items-center text-lg font-bold">要</span>
        <span class="text-[28px] font-bold text-leaf-800">今日要点</span>
        <span class="flex-1 border-t-2 border-leaf-100"></span>
      </div>
      <ol class="space-y-5">
        <li v-for="(h, i) in points" :key="i" class="flex gap-4">
          <span class="w-9 h-9 rounded-full bg-leaf-100 text-leaf-700 text-xl font-bold grid place-items-center shrink-0">{{ i + 1 }}</span>
          <p class="text-[24px] leading-[1.6] text-stone-700">{{ h }}</p>
        </li>
      </ol>
    </div>

    <!-- 底部：二维码 -->
    <div class="mx-12 mb-10 rounded-2xl bg-leaf-50 border border-leaf-100 px-8 py-6 flex items-center gap-6">
      <img :src="qr" alt="二维码" class="w-[132px] h-[132px] rounded-lg" />
      <div class="min-w-0">
        <div class="text-[26px] font-bold text-leaf-800">扫码阅读完整日报</div>
        <div class="mt-2 text-xl text-stone-500">政策 · 报道 · 论文 · 行业动态，每日更新</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  daily: { type: Object, required: true }, // { date, title, highlights }
  qr: { type: String, required: true },    // 二维码 dataURL
})

const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const dateLabel = computed(() => {
  const d = new Date(props.daily.date)
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · ${WEEK[d.getDay()]}`
})

// 控制图片高度：最多 5 条，每条截断到 64 字
const points = computed(() =>
  (props.daily.highlights || [])
    .slice(0, 5)
    .map((h) => (h.length > 64 ? `${h.slice(0, 64)}…` : h)),
)
</script>
