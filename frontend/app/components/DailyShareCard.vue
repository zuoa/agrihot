<template>
  <article class="daily-share-card">
    <!-- 固定 750px 排版，按 2 倍像素导出；不随预览窗口改变字号。 -->
    <header class="card-header">
      <div class="card-masthead">
        <div class="card-brand"><BrandMark /><span>AgriHot<span class="brand-dot">.</span></span></div>
        <span class="card-tagline">农业科技情报 · 每日精选</span>
      </div>
      <div class="card-edition">
        <div class="card-title">
          <p class="card-eyebrow">每日关注农业新动态</p>
          <h1>农业农村日报</h1>
          <p class="card-topics">政策 · 报道 · 学术论文 · 行业动态</p>
        </div>
        <div class="card-date">
          <span class="card-year">{{ edition.year }}</span>
          <strong>{{ edition.monthDay }}</strong>
          <span class="card-week">{{ edition.week }}</span>
        </div>
      </div>
    </header>

    <section v-if="points.length" class="card-highlights">
      <div class="card-section-heading">
        <h2>本期要点</h2>
        <span>{{ points.length }} 条速览<span v-if="itemCount"> · {{ itemCount }} 条资讯</span></span>
      </div>
      <ol class="card-points">
        <li v-for="(point, index) in points" :key="index" :class="{ 'card-point-lead': index === 0 }">
          <span class="card-point-number">{{ String(index + 1).padStart(2, '0') }}</span>
          <p>{{ point }}</p>
        </li>
      </ol>
    </section>
    <section v-else class="card-summary"><p>{{ daily.title }}</p><span>扫码查看本期完整内容</span></section>

    <footer class="card-footer">
      <div class="card-footer-copy">
        <p class="card-footer-label">把值得关注的，分享出去</p>
        <h2>扫码阅读完整日报</h2>
        <p class="card-qr-hint">长按识别二维码，查看资讯与原文</p>
        <span class="card-site">agrihot.com</span>
      </div>
      <div class="card-qr"><img :src="qr" width="132" height="132" alt="本期日报二维码" /></div>
    </footer>
    <p class="card-source-note">整理自公开来源 · 摘要仅供参考，请以原文为准</p>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  daily: { type: Object, required: true },
  qr: { type: String, required: true },
})

const edition = computed(() => {
  const [year, month, day] = shanghaiDateKey(props.daily.date).split('-')
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][
    new Date(Date.UTC(Number(year), Number(month) - 1, Number(day))).getUTCDay()
  ]
  return { year, monthDay: `${month}.${day}`, week }
})

const itemCount = computed(() => props.daily.items?.length || 0)

// 给长摘要留出更多阅读空间，同时避免分享图片过长。
const points = computed(() => {
  const highlights = (props.daily.highlights || []).filter((text) => text?.trim())
  const source = highlights.length ? highlights : (props.daily.items || []).map((item) => item.title).filter(Boolean)
  return source.slice(0, 5).map((text) => {
    const chars = Array.from(text.trim())
    return chars.length > 96 ? `${chars.slice(0, 96).join('')}…` : chars.join('')
  })
})
</script>

<style scoped>
.daily-share-card {
  --card-green: #234e22;
  --card-ink: #20332a;
  --card-muted: #637168;
  --card-line: #dce6d8;
  box-sizing: border-box;
  width: 750px;
  overflow: hidden;
  border-top: 8px solid var(--card-green);
  background: #f4f8f2;
  color: var(--card-ink);
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
}
.card-header { padding: 38px 44px 34px; }
.card-masthead { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.card-brand { display: flex; align-items: center; gap: 12px; color: var(--card-green); }
.card-brand img { width: 40px; height: 40px; }
.card-brand > span { font-family: Arial, sans-serif; font-size: 30px; font-weight: 700; letter-spacing: -1.2px; }
.brand-dot { color: #44963c; }
.card-tagline { color: var(--card-muted); font-size: 17px; }
.card-edition { display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-top: 38px; }
.card-eyebrow { color: var(--card-green); font-size: 17px; letter-spacing: 3px; }
.card-title h1 { margin-top: 10px; font-family: 'Songti SC', 'STSong', 'SimSun', serif; font-size: 50px; font-weight: 700; line-height: 1.4; letter-spacing: 1px; }
.card-topics { margin-top: 12px; color: var(--card-muted); font-size: 18px; }
.card-date { display: flex; flex: 0 0 142px; flex-direction: column; align-items: center; padding: 10px 0 10px 24px; border-left: 1px solid #c7d7c1; }
.card-year { color: var(--card-muted); font-family: 'SFMono-Regular', Consolas, monospace; font-size: 19px; letter-spacing: 3px; }
.card-date strong { margin-top: 5px; color: var(--card-green); font-family: Arial, sans-serif; font-size: 43px; font-weight: 600; line-height: 1.2; letter-spacing: -1.5px; }
.card-week { margin-top: 8px; color: var(--card-muted); font-size: 18px; letter-spacing: 4px; }
.card-highlights { margin: 0 28px; padding: 28px 28px 8px; border: 1px solid var(--card-line); border-radius: 22px; background: #fff; }
.card-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.card-section-heading h2 { display: flex; align-items: center; gap: 12px; color: var(--card-green); font-size: 24px; font-weight: 650; }
.card-section-heading h2::before { content: ''; width: 5px; height: 22px; border-radius: 2px; background: #82a678; }
.card-section-heading > span { color: var(--card-muted); font-size: 16px; }
.card-points { margin: 0; padding: 0; list-style: none; }
.card-points li { display: flex; align-items: flex-start; gap: 18px; padding: 24px 2px; }
.card-points li + li { border-top: 1px solid #e7ede4; }
.card-point-number { flex: 0 0 32px; padding-top: 5px; color: #719267; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 19px; font-weight: 500; line-height: 1.7; }
.card-points p { min-width: 0; margin: 0; color: #35483a; font-size: 25px; line-height: 1.75; overflow-wrap: anywhere; }
.card-points .card-point-lead { margin-bottom: 2px; padding: 22px 20px; border-radius: 12px; background: #edf4e8; }
.card-point-lead .card-point-number { color: var(--card-green); }
.card-point-lead p { color: var(--card-green); font-weight: 600; }
.card-points .card-point-lead + li { border-top: 0; }
.card-summary { margin: 0 28px; padding: 36px 28px; border-radius: 22px; background: #fff; }
.card-summary p { font-size: 28px; line-height: 1.7; overflow-wrap: anywhere; }
.card-summary > span { display: block; margin-top: 14px; color: var(--card-muted); font-size: 20px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 32px 44px 28px; }
.card-footer-copy { min-width: 0; }
.card-footer-label { color: var(--card-muted); font-size: 17px; }
.card-footer h2 { margin-top: 9px; color: var(--card-green); font-size: 28px; font-weight: 650; line-height: 1.5; }
.card-qr-hint { margin-top: 7px; color: var(--card-muted); font-size: 17px; }
.card-site { display: block; margin-top: 15px; color: var(--card-green); font-family: Arial, sans-serif; font-size: 18px; letter-spacing: .6px; }
.card-qr { flex-shrink: 0; padding: 8px; border: 1px solid var(--card-line); border-radius: 14px; background: #fff; }
.card-qr img { display: block; width: 132px; height: 132px; }
.card-source-note { margin: 0 44px; padding: 18px 0 24px; border-top: 1px solid var(--card-line); color: var(--card-muted); font-size: 14px; text-align: center; letter-spacing: .5px; }
</style>
