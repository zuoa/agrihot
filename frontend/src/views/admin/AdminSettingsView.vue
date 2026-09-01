<template>
  <div v-if="loading" class="text-sm text-stone-400 py-16 text-center">加载中…</div>
  <form v-else-if="form" class="space-y-6 max-w-xl" @submit.prevent="save">
    <p class="text-sm text-stone-500">密钥仍走环境变量，这里只改运营旋钮。保存后立即生效，调度时刻最多一分钟内对齐。</p>

    <section class="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
      <h2 class="text-sm font-bold">精选</h2>
      <label class="block text-sm">
        <span class="text-xs text-stone-500">入选阈值（0–100）{{ source('selection_threshold') }}</span>
        <input v-model.number="form.selection_threshold" type="number" min="0" max="100"
          class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
      </label>
      <label class="block text-sm">
        <span class="text-xs text-stone-500">每日精选名额 {{ source('daily_top_n') }}</span>
        <input v-model.number="form.daily_top_n" type="number" min="1" max="50"
          class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
      </label>
    </section>

    <section class="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
      <h2 class="text-sm font-bold">日报</h2>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.daily_generate_enabled" type="checkbox" class="accent-leaf-700" />
        定时生成开启 {{ source('daily_generate_enabled') }}
      </label>
      <label class="block text-sm">
        <span class="text-xs text-stone-500">生成时刻 HH:MM {{ source('daily_generate_time') }}</span>
        <input v-model="form.daily_generate_time" type="time"
          class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
      </label>
    </section>

    <section class="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
      <h2 class="text-sm font-bold">文献雷达</h2>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.literature_fetch_enabled" type="checkbox" class="accent-leaf-700" />
        定时拉取开启 {{ source('literature_fetch_enabled') }}
      </label>
      <label class="block text-sm">
        <span class="text-xs text-stone-500">拉取时刻 HH:MM {{ source('literature_fetch_time') }}</span>
        <input v-model="form.literature_fetch_time" type="time"
          class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
      </label>
      <div class="grid grid-cols-3 gap-2">
        <label class="block text-sm">
          <span class="text-xs text-stone-500">回看重叠天</span>
          <input v-model.number="form.literature_lookback_days" type="number" min="0" max="30"
            class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
        </label>
        <label class="block text-sm">
          <span class="text-xs text-stone-500">首次回看天</span>
          <input v-model.number="form.literature_bootstrap_days" type="number" min="1" max="90"
            class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
        </label>
        <label class="block text-sm">
          <span class="text-xs text-stone-500">单次最多新建</span>
          <input v-model.number="form.literature_max_new_per_run" type="number" min="1" max="500"
            class="mt-1 w-full px-3 py-1.5 rounded-md border border-stone-200" />
        </label>
      </div>
    </section>

    <section class="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
      <h2 class="text-sm font-bold">抓取</h2>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="form.content_fetch_enabled" type="checkbox" class="accent-leaf-700" />
        启用 Jina 全文抓取 {{ source('content_fetch_enabled') }}
      </label>
    </section>

    <section v-if="readonly" class="bg-stone-50 border border-stone-200 rounded-lg p-4 text-sm">
      <h2 class="text-sm font-bold mb-2">环境（只读）</h2>
      <ul class="text-xs text-stone-600 space-y-1">
        <li>DeepSeek {{ readonly.deepseek_configured ? '已配置' : '未配置' }} · {{ readonly.deepseek_model }}</li>
        <li>Jina {{ readonly.jina_configured ? '已配置' : '匿名额度' }}</li>
        <li>OpenAlex {{ readonly.openalex_configured ? '已配置 Key' : '无 Key' }} · {{ readonly.openalex_mailto }}</li>
        <li>业务时区 {{ readonly.daily_timezone }} · 推送限流 {{ readonly.ingest_rate_limit }}</li>
      </ul>
    </section>

    <p v-if="msg" class="text-xs" :class="ok ? 'text-leaf-700' : 'text-red-600'">{{ msg }}</p>
    <button type="submit" :disabled="saving"
      class="px-4 py-2 text-sm rounded-lg bg-leaf-700 text-white hover:bg-leaf-800 disabled:opacity-50">
      {{ saving ? '保存中…' : '保存配置' }}
    </button>
  </form>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../api'

const loading = ref(true)
const saving = ref(false)
const msg = ref('')
const ok = ref(false)
const form = reactive({})
const sources = ref({})
const readonly = ref(null)

function source(key) {
  return sources.value[key] === 'override' ? '· 已覆盖' : '· 环境默认'
}

function apply(data) {
  readonly.value = data.readonly
  for (const [k, v] of Object.entries(data.writable)) {
    form[k] = v.value
    sources.value[k] = v.source
  }
}

onMounted(async () => {
  try {
    apply(await api.adminSettings())
  } catch (e) {
    msg.value = e.message
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  msg.value = ''
  try {
    const patch = { ...form }
    apply(await api.adminPatchSettings(patch))
    ok.value = true
    msg.value = '已保存'
  } catch (e) {
    ok.value = false
    msg.value = e.message
  } finally {
    saving.value = false
  }
}
</script>
