<template>
  <div class="agent-page site-reading-page space-y-8 pb-6">
    <header class="agent-hero overflow-hidden rounded-2xl border border-leaf-200 bg-white">
      <div class="px-6 py-8 sm:p-10">
        <p class="page-eyebrow">AGRIHOT · AGENT 接入</p>
        <h1 class="agent-title">让你的 Agent<br />读懂农业正在发生什么</h1>
        <p class="mt-4 max-w-xl text-sm leading-7 text-stone-600">政策、行业动态、学术论文与每日要点。接入 AgriHot，用自然语言查找资料，沿着来源阅读全文。</p>
        <div class="mt-6 flex flex-wrap gap-3 text-sm">
          <a href="#apply" class="site-button">申请读取 Key</a>
          <a href="#connect" class="site-button site-button-secondary">查看接入方式<ArticleIcon name="chevron" class="rotate-90" /></a>
        </div>
      </div>
      <div class="grid sm:grid-cols-3 border-t border-leaf-100 bg-leaf-50/60 text-sm">
        <div v-for="(step, i) in steps" :key="step.title" class="flex items-start gap-3 px-6 py-4 sm:border-r border-leaf-100 last:border-r-0">
          <span class="font-mono text-leaf-500 mt-0.5">0{{ i + 1 }}</span>
          <div><p class="font-medium text-leaf-900">{{ step.title }}</p><p class="mt-1 text-xs text-stone-500 leading-5">{{ step.detail }}</p></div>
        </div>
      </div>
    </header>

    <section id="connect" class="scroll-mt-6">
      <div class="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div><h2 class="text-xl font-bold text-stone-900">选择你的接入方式</h2><p class="mt-1 text-sm text-stone-500">同一份内容，适配不同的 Agent。</p></div>
        <span class="rounded-full bg-leaf-100 px-3 py-1 text-xs text-leaf-800">只读接入 · 需要读取 Key</span>
      </div>
      <div role="tablist" aria-label="接入方式" class="flex gap-2 border-b border-leaf-200">
        <button v-for="option in tabs" :id="`tab-${option.id}`" :key="option.id" type="button" role="tab" :aria-selected="tab === option.id" aria-controls="connect-panel" :tabindex="tab === option.id ? 0 : -1"
          class="px-5 py-3 text-sm border-b-2 -mb-px rounded-t-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-leaf-600"
          :class="tab === option.id ? 'border-leaf-700 text-leaf-800 font-bold bg-white' : 'border-transparent text-stone-500 hover:text-leaf-700'"
          @click="tab = option.id" @keydown="tabKeydown">{{ option.label }}</button>
      </div>
      <div id="connect-panel" role="tabpanel" :aria-labelledby="`tab-${tab}`" class="rounded-b-xl border border-t-0 border-leaf-200 bg-white p-5 sm:p-7">
        <template v-if="tab === 'skill'">
          <h3 class="text-lg font-bold text-leaf-900">把安装提示词发给你的 Agent</h3>
          <p class="mt-2 text-sm text-stone-600 leading-6">适用于 Claude Code、Codex 等支持 Agent Skills 的工具。先申请读取 Key，再让 Agent 安装 Skill。</p>
          <AgentCodeBlock lang="提示词" :code="installPrompt" />
          <button class="mt-3 text-sm font-medium text-leaf-700 hover:underline" @click="copy(installPrompt, 'skill')">{{ copied === 'skill' ? '已复制' : '复制安装提示词' }}</button>
          <ol class="mt-5 space-y-2 list-decimal pl-5 text-sm leading-6 text-stone-600">
            <li>将读取 Key 配置为 Agent 运行环境的 <AgentCode>AGRIHOT_API_KEY</AgentCode>，不要写进 Skill 文件。</li>
            <li>安装后开启新会话，确保工具能发现 AgriHot Skill。</li>
            <li>试着问：“过去一周，农业遥感领域有哪些值得关注的进展？”</li>
          </ol>
          <a :href="`${base}/agrihot-skill/README.md`" class="mt-4 inline-block text-xs text-leaf-700 underline underline-offset-4">完整安装说明 ↗</a>
        </template>
        <template v-else>
          <h3 class="text-lg font-bold text-leaf-900">为 MCP 客户端配置地址与认证头</h3>
          <p class="mt-2 text-sm text-stone-600 leading-6">使用 Streamable HTTP，适用于支持自定义认证头的远程 MCP 客户端。将下面的 Key 占位符替换为管理员交付的读取 Key。</p>
          <AgentCodeBlock lang="JSON" :code="mcpConfig" />
          <button class="mt-3 text-sm font-medium text-leaf-700 hover:underline" @click="copy(mcpConfig, 'mcp')">{{ copied === 'mcp' ? '已复制' : '复制 MCP 配置' }}</button>
          <p class="mt-4 text-xs text-stone-500 leading-6">连接后可使用内容检索、最新与精选列表、单篇详情、日报列表和完整日报五个工具。不同客户端的配置文件格式可能不同，服务地址和认证头保持一致即可。</p>
        </template>
        <p v-if="copyError" role="status" class="mt-2 text-xs text-amber-800">{{ copyError }}</p>
      </div>
    </section>

    <section class="grid sm:grid-cols-2 gap-5">
      <div class="rounded-xl border border-leaf-100 bg-white p-6">
        <h2 class="font-bold text-stone-900">从一个问题开始</h2>
        <div class="mt-4 divide-y divide-leaf-100">
          <button v-for="prompt in prompts" :key="prompt" class="flex w-full items-start justify-between gap-4 py-3 text-left text-sm leading-6 text-stone-600 hover:text-leaf-700" @click="copy(prompt, prompt)">
            <span>{{ prompt }}</span><span class="shrink-0 text-xs text-leaf-600">{{ copied === prompt ? '已复制' : '复制 ↗' }}</span>
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-leaf-100 bg-white p-6">
        <h2 class="font-bold text-stone-900">获取结果，也保留出处</h2>
        <ul class="mt-4 space-y-4 text-sm leading-6 text-stone-600">
          <li><strong class="text-leaf-800">按关键词和语义查找</strong><br />结合分类、主题、论文方向和收录时间缩小范围。</li>
          <li><strong class="text-leaf-800">从摘要继续阅读</strong><br />获取已收录全文与论文卡片，结果附站内阅读页和原文链接。</li>
          <li><strong class="text-leaf-800">明确可用范围</strong><br />全文未收录时会标记缺失；语义检索暂不可用时会提示降级。每个读取 Key 默认每分钟 60 次请求。</li>
        </ul>
      </div>
    </section>

    <section id="apply" class="scroll-mt-6 rounded-2xl border border-leaf-200 bg-white p-6 sm:p-8">
      <div class="grid md:grid-cols-[1fr_1.5fr] gap-6 sm:gap-10">
        <div><p class="page-eyebrow">接入申请</p><h2 class="mt-3 text-xl font-bold text-stone-900">申请读取 Key</h2><p class="mt-3 text-sm leading-7 text-stone-500">告诉我们你准备如何使用 AgriHot。管理员审核后，会通过你填写的联系方式交付 Key。</p><p class="mt-3 text-xs leading-6 text-stone-400">联系方式仅用于接入申请沟通。请勿在表单中提交现有密钥。</p></div>
        <form v-if="!submitted" class="space-y-4" @submit.prevent="apply">
          <label class="block text-sm text-stone-700">名称 / 项目名<input v-model="form.name" required maxlength="100" autocomplete="organization" class="agent-input" placeholder="例如：农业研究助手" /></label>
          <label class="block text-sm text-stone-700">邮箱或微信<input v-model="form.contact" required minlength="3" maxlength="200" class="agent-input" placeholder="可联系到你的邮箱或微信号" /></label>
          <label class="block text-sm text-stone-700">使用用途<textarea v-model="form.use_case" required minlength="10" maxlength="2000" rows="3" class="agent-input resize-y" placeholder="希望查询什么内容，用在哪个 Agent 或项目中？（至少 10 字）" /></label>
          <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
          <button type="submit" :disabled="busy" class="site-button">{{ busy ? '提交中…' : '提交申请' }}</button>
        </form>
        <div v-else role="status" class="self-center rounded-xl bg-leaf-50 border border-leaf-100 p-6"><h3 class="font-bold text-leaf-800">申请已提交</h3><p class="mt-2 text-sm leading-6 text-stone-600">申请编号 #{{ submitted.id }}。审核后，管理员将通过你填写的联系方式交付读取 Key。</p></div>
      </div>
    </section>
    <footer class="flex flex-wrap gap-x-6 gap-y-3 text-xs text-stone-500">
      <a href="/llms.txt" class="hover:text-leaf-700">llms.txt ↗</a><a href="/api/v1/agent" class="hover:text-leaf-700">Agent 使用说明 ↗</a><a href="/docs" class="hover:text-leaf-700">接口参考 ↗</a><NuxtLink to="/about" class="hover:text-leaf-700">接入问题与联系</NuxtLink>
    </footer>
    <span class="sr-only" role="status" aria-live="polite">{{ copied ? '已复制到剪贴板' : '' }}</span>
  </div>
</template>

<script setup>
const config = useRuntimeConfig()
const api = useApi()
const base = String(config.public.siteUrl || 'https://agrihot.com').replace(/\/$/, '')
const tab = ref('skill')
const tabs = [{ id: 'skill', label: 'Agent Skill' }, { id: 'mcp', label: 'MCP' }]
const steps = [{ title: '申请 Key', detail: '填写用途，等待管理员审核' }, { title: '连接 Agent', detail: '安装 Skill 或配置 MCP' }, { title: '提问与引用', detail: '检索内容，查看全文与来源' }]
const prompts = ['过去 24 小时，有哪些值得关注的农业政策？', '检索近一周关于作物病害智能识别的论文。', '给我最新一期农业农村日报。']
const installPrompt = `请安装 AgriHot Skill：${base}/agrihot-skill/README.md\n使用我已配置的 AGRIHOT_API_KEY 环境变量进行读取，不要将 Key 写入 Skill 文件或输出。\n安装后告诉我是否需要开启新会话。`
const mcpConfig = JSON.stringify({ mcpServers: { agrihot: { url: `${base}/api/v1/mcp`, headers: { Authorization: 'Bearer <你的读取Key>' } } } }, null, 2)
const form = reactive({ name: '', contact: '', use_case: '' })
const busy = ref(false), submitted = ref(null), error = ref(''), copied = ref(''), copyError = ref('')
async function copy(text, id) {
  try { await navigator.clipboard.writeText(text); copied.value = id; copyError.value = '' }
  catch { copyError.value = '复制失败，请手动选中内容复制。' }
}
function tabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  tab.value = event.key === 'Home' ? 'skill' : event.key === 'End' ? 'mcp' : tab.value === 'skill' ? 'mcp' : 'skill'
  nextTick(() => document.getElementById(`tab-${tab.value}`)?.focus())
}
async function apply() {
  busy.value = true; error.value = ''
  try { submitted.value = await api.agentApply(form) }
  catch (e) { error.value = e?.statusCode === 429 ? '提交过于频繁，请稍后再试。' : '提交失败，请检查填写内容或稍后重试。' }
  finally { busy.value = false }
}
usePageSeo({ title: 'Agent 接入 · AgriHot', description: '通过 Agent Skill 或 MCP 接入 AgriHot，检索农业政策、资讯、论文、已收录全文与日报。', path: '/agent' })
</script>

<style scoped>
.agent-hero { border-color: #e1e8e0; border-radius: 16px; }
.agent-title { margin-top: 18px; max-width: 650px; color: #20332a; font-size: 36px; font-weight: 700; line-height: 1.55; letter-spacing: -.04em; }
.agent-page :is(section, #connect-panel) { border-color: #e1e8e0; }
.agent-page :is(h2, h3) { color: #20332a; letter-spacing: -.02em; }
.agent-page [role='tab'] { min-height: 44px; }
.agent-input { display: block; width: 100%; margin-top: 8px; padding: 12px 14px; border: 1px solid #e1e8e0; border-radius: 7px; background: #f8faf7; color: #20332a; font-size: 13px; }
.agent-input::placeholder { color: #829080; }
.agent-input:focus { border-color: #82a678; }
@media (max-width: 767px) { .agent-title { font-size: 28px; } .agent-input { font-size: 14px; } .agent-page #connect-panel { padding: 22px 20px; } }
</style>
