<template>
  <div class="bg-white rounded-2xl border border-leaf-100 p-6 sm:p-8 space-y-5">
    <h1 class="text-2xl font-bold text-stone-900">关于 AgriHot</h1>
    <p class="text-sm text-stone-600 leading-7">
      AgriHot 是一个农业信息化资讯聚合站：聚合农业农村政策、行业报道与农业信息化学术论文，
      每日生成《农业农村日报》。内容主要由爬虫 Agent 通过
      <router-link to="/agent" class="text-leaf-700 hover:underline">开放推送接口</router-link>
      提交，服务层自动去重（URL 精确 + 标题相似），多信源报道自动合并。
    </p>
    <div class="grid sm:grid-cols-3 gap-3 text-center">
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-2xl">🌱</div>
        <div class="text-sm font-bold text-leaf-800 mt-1">政策与报道</div>
        <div class="text-xs text-stone-500 mt-1">部委文件、地方实践、行业动态</div>
      </div>
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-2xl">📄</div>
        <div class="text-sm font-bold text-leaf-800 mt-1">学术论文</div>
        <div class="text-xs text-stone-500 mt-1">智慧农业 / 数字乡村研究，外文已译为中文</div>
      </div>
      <div class="rounded-xl bg-leaf-50 border border-leaf-100 p-4">
        <div class="text-2xl">🤖</div>
        <div class="text-sm font-bold text-leaf-800 mt-1">Agent 友好</div>
        <div class="text-xs text-stone-500 mt-1">开放推送 API，去重后自动上线</div>
      </div>
    </div>
    <p class="text-xs text-stone-400 leading-5 border-t border-leaf-100 pt-4">
      免责声明：本站内容整理自公开来源，摘要与翻译由 AI 生成，仅供参考；引用与决策请以官方原文与正式出版物为准。
      如涉及来源方权益问题，请联系站点管理员更正或下线。
    </p>
  </div>
</template>
