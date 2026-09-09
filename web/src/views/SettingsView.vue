<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useModelSettings } from "@/composables/useModelSettings";
import { useChannelSettings } from "@/composables/useChannelSettings";

const emit = defineEmits(["back", "changed"]);

const tab = ref("models");

const { doc, loading, saving, error, load, saveProvider, removeProvider, setDefault, discoverModels, testConnectivity } =
  useModelSettings();

const {
  doc: channelDoc,
  loading: channelLoading,
  saving: channelSaving,
  testing: channelTesting,
  error: channelError,
  testHint: feishuTestHint,
  load: loadChannels,
  saveFeishu,
  testFeishu,
  reloadFeishu,
  feishuChannel,
} = useChannelSettings();

const editingId = ref(null);
const discovering = ref(false);
const testingModel = ref(false);
const discoverHint = ref("");
const modelTestHint = ref("");
let discoverTimer = null;

const form = reactive({
  id: "",
  label: "",
  api: "openai-completions",
  base_url: "",
  api_key: "",
  default_model: "",
  models: "",
  enabled: true,
});

const feishuForm = reactive({
  enabled: true,
  display_name: "飞书",
  app_id: "",
  app_secret: "",
  verification_token: "",
  encrypt_key: "",
  use_long_connection: true,
});

const feishu = computed(() => feishuChannel());

function syncFeishuForm() {
  const c = feishuChannel();
  if (!c) return;
  feishuForm.enabled = c.enabled !== false;
  feishuForm.display_name = c.display_name || "飞书";
  feishuForm.app_id = c.app_id || "";
  feishuForm.app_secret = "";
  feishuForm.verification_token = "";
  feishuForm.encrypt_key = "";
  feishuForm.use_long_connection = c.use_long_connection !== false;
}

function resetForm() {
  editingId.value = null;
  discoverHint.value = "";
  modelTestHint.value = "";
  form.id = "";
  form.label = "";
  form.api = "openai-completions";
  form.base_url = "";
  form.api_key = "";
  form.default_model = "";
  form.models = "";
  form.enabled = true;
}

function startCreate() {
  resetForm();
  editingId.value = "__new__";
}

function startEdit(p) {
  editingId.value = p.id;
  discoverHint.value = "";
  modelTestHint.value = "";
  form.id = p.id;
  form.label = p.label || "";
  form.api = p.api || "openai-completions";
  form.base_url = p.base_url || "";
  form.api_key = "";
  form.default_model = p.default_model || "";
  form.models = (p.models || []).join(", ");
  form.enabled = p.enabled !== false;
}

function scheduleDiscover() {
  if (discoverTimer) clearTimeout(discoverTimer);
  discoverTimer = setTimeout(() => {
    fetchAvailableModels({ silent: true });
  }, 600);
}

async function fetchAvailableModels({ silent = false } = {}) {
  if (!form.base_url.trim()) {
    if (!silent) discoverHint.value = "请先填写 Base URL";
    return;
  }
  if (editingId.value === "__new__" && !form.api_key.trim()) {
    if (!silent) discoverHint.value = "请先填写 API Key";
    return;
  }
  discovering.value = true;
  discoverHint.value = silent ? "正在拉取模型列表…" : "正在请求 /models …";
  try {
    const data = await discoverModels({
      base_url: form.base_url.trim(),
      api_key: form.api_key,
      provider_id: editingId.value !== "__new__" ? editingId.value : undefined,
    });
    const models = data.models || [];
    form.models = models.join(", ");
    if (!form.default_model || !models.includes(form.default_model)) {
      form.default_model = data.default_model || models[0] || "";
    }
    discoverHint.value = `已拉取 ${models.length} 个模型`;
  } catch (err) {
    discoverHint.value = String(err.message || err);
    if (!silent) throw err;
  } finally {
    discovering.value = false;
  }
}

async function runModelTest(providerId) {
  testingModel.value = true;
  modelTestHint.value = "正在测试连通性…";
  try {
    const payload = providerId
      ? { provider_id: providerId }
      : {
          base_url: form.base_url.trim(),
          api_key: form.api_key,
          model: form.default_model.trim(),
          provider_id: editingId.value !== "__new__" ? editingId.value : undefined,
        };
    const data = await testConnectivity(payload);
    const chat = data.chat_ok ? "对话探测成功" : data.chat_error ? `对话：${data.chat_error}` : "仅验证 /models";
    modelTestHint.value = `连通成功 · ${data.models_count || 0} 个模型 · ${chat}`;
  } catch (err) {
    modelTestHint.value = String(err.message || err);
  } finally {
    testingModel.value = false;
  }
}

async function onSave() {
  const payload = {
    id: form.id.trim(),
    label: form.label.trim() || form.id.trim(),
    api: form.api,
    base_url: form.base_url.trim(),
    api_key: form.api_key,
    default_model: form.default_model.trim(),
    models: form.models
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    enabled: !!form.enabled,
  };
  await saveProvider(payload);
  resetForm();
  emit("changed");
}

async function onDelete(id) {
  if (!confirm(`删除自定义 Provider「${id}」？`)) return;
  await removeProvider(id);
  if (editingId.value === id) resetForm();
  emit("changed");
}

async function onDefault(id) {
  await setDefault(id);
  emit("changed");
}

async function onSaveFeishu() {
  await saveFeishu({
    enabled: !!feishuForm.enabled,
    display_name: feishuForm.display_name.trim() || "飞书",
    app_id: feishuForm.app_id.trim(),
    app_secret: feishuForm.app_secret,
    verification_token: feishuForm.verification_token,
    encrypt_key: feishuForm.encrypt_key,
    use_long_connection: !!feishuForm.use_long_connection,
  });
  syncFeishuForm();
}

async function onTestFeishu() {
  await testFeishu({
    app_id: feishuForm.app_id.trim(),
    app_secret: feishuForm.app_secret,
  });
}

async function switchTab(next) {
  tab.value = next;
  if (next === "channels") {
    await loadChannels();
    syncFeishuForm();
  }
}

onMounted(async () => {
  await load();
});
</script>

<template>
  <div class="settings-page">
    <header class="settings-top">
      <NlmButton variant="ghost" @click="emit('back')">← 返回对话</NlmButton>
      <div class="settings-brand">
        <h1>Nexus Lark Mind</h1>
        <p>设置 · 模型与通道</p>
      </div>
    </header>

    <div class="settings-body">
      <nav class="settings-nav">
        <button type="button" class="nav-item" :class="{ active: tab === 'models' }" @click="switchTab('models')">
          模型
        </button>
        <button
          type="button"
          class="nav-item"
          :class="{ active: tab === 'channels' }"
          @click="switchTab('channels')"
        >
          通道
        </button>
      </nav>

      <section v-if="tab === 'models'" class="settings-main">
        <div v-if="error" class="settings-error">{{ error }}</div>
        <div v-if="loading" class="rail-hint">加载中…</div>

        <div class="settings-block">
          <h2>默认 Provider</h2>
          <p class="rail-hint">新对话优先使用；也可在 Composer 临时切换。</p>
          <div class="default-row">
            <NlmSelect
              :model-value="doc.default_provider"
              :options="[
                ...doc.builtins.map((p) => ({ value: p.id, label: `${p.label} (env)` })),
                ...doc.customs.map((p) => ({ value: p.id, label: p.label || p.id })),
              ]"
              @update:model-value="onDefault"
            />
          </div>
        </div>

        <div class="settings-block">
          <h2>内置 Provider（.env）</h2>
          <p class="rail-hint">只读。改 Key / 模型列表请编辑 `.env` 后重启。</p>
          <div class="provider-grid">
            <div v-for="p in doc.builtins" :key="p.id" class="provider-card">
              <div class="pc-head">
                <strong>{{ p.label }}</strong>
                <span class="chip" :class="{ on: p.configured }">{{ p.configured ? "已配置" : "未配置" }}</span>
              </div>
              <div class="pc-meta">{{ p.id }} · {{ p.api }}</div>
              <div class="pc-meta mono">{{ p.base_url }}</div>
              <div class="pc-models">
                <NlmChip v-for="m in p.models || []" :key="m" :active="m === p.default_model">{{ m }}</NlmChip>
              </div>
              <div class="pc-actions">
                <NlmButton
                  variant="ghost"
                  :disabled="testingModel || !p.configured || p.api === 'anthropic-messages'"
                  @click="runModelTest(p.id)"
                >
                  测试连通性
                </NlmButton>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-block">
          <div class="block-head">
            <div>
              <h2>自定义 Provider</h2>
              <p class="rail-hint">填 Base URL + API Key 后可自动拉取 `/models`；保存前可测连通性。</p>
            </div>
            <NlmButton variant="new" @click="startCreate">＋ 新增</NlmButton>
          </div>

          <div class="provider-grid">
            <div v-for="p in doc.customs" :key="p.id" class="provider-card custom">
              <div class="pc-head">
                <strong>{{ p.label || p.id }}</strong>
                <span class="chip" :class="{ on: p.configured }">{{ p.configured ? "可用" : "缺 Key/模型" }}</span>
              </div>
              <div class="pc-meta">{{ p.id }} · {{ p.api }}</div>
              <div class="pc-meta mono">{{ p.base_url }}</div>
              <div class="pc-meta">Key: {{ p.api_key_set ? p.api_key_preview : "未设置" }}</div>
              <div class="pc-models">
                <NlmChip v-for="m in p.models || []" :key="m" :active="m === p.default_model">{{ m }}</NlmChip>
              </div>
              <div class="pc-actions">
                <NlmButton variant="ghost" @click="startEdit(p)">编辑</NlmButton>
                <NlmButton variant="ghost" :disabled="testingModel" @click="runModelTest(p.id)">测试连通性</NlmButton>
                <NlmButton variant="ghost" @click="onDelete(p.id)">删除</NlmButton>
                <NlmButton variant="ghost" @click="onDefault(p.id)">设为默认</NlmButton>
              </div>
            </div>
            <div v-if="!doc.customs.length" class="rail-hint">还没有自定义 Provider。</div>
          </div>
          <p v-if="modelTestHint && !editingId" class="discover-hint">{{ modelTestHint }}</p>
        </div>

        <div v-if="editingId" class="settings-block editor">
          <h2>{{ editingId === "__new__" ? "新增自定义 Provider" : `编辑 ${editingId}` }}</h2>
          <div class="form-grid">
            <label>
              <span>ID（小写短横线）</span>
              <input v-model="form.id" :disabled="editingId !== '__new__'" placeholder="my-proxy" />
            </label>
            <label>
              <span>显示名</span>
              <input v-model="form.label" placeholder="My Proxy" />
            </label>
            <label>
              <span>协议</span>
              <select v-model="form.api">
                <option value="openai-completions">openai-completions</option>
              </select>
            </label>
            <label class="span2">
              <span>Base URL</span>
              <input
                v-model="form.base_url"
                placeholder="https://api.example.com/v1"
                @change="scheduleDiscover"
              />
            </label>
            <label class="span2">
              <span>API Key{{ editingId !== "__new__" ? "（留空则保留原值）" : "" }}</span>
              <input
                v-model="form.api_key"
                type="password"
                placeholder="sk-..."
                autocomplete="off"
                @change="scheduleDiscover"
              />
            </label>
            <label>
              <span>默认模型</span>
              <input v-model="form.default_model" placeholder="gpt-4o-mini" list="discovered-models" />
            </label>
            <label>
              <span>模型列表（自动拉取 / 可改）</span>
              <input v-model="form.models" placeholder="拉取后自动填入，也可手改" />
            </label>
            <datalist id="discovered-models">
              <option
                v-for="m in form.models.split(',').map((x) => x.trim()).filter(Boolean)"
                :key="m"
                :value="m"
              />
            </datalist>
            <label class="check">
              <input v-model="form.enabled" type="checkbox" />
              启用
            </label>
          </div>
          <p v-if="discoverHint" class="discover-hint">{{ discoverHint }}</p>
          <p v-if="modelTestHint" class="discover-hint">{{ modelTestHint }}</p>
          <div class="form-actions">
            <NlmButton variant="ghost" :disabled="discovering || saving" @click="fetchAvailableModels()">
              {{ discovering ? "拉取中…" : "拉取可用模型" }}
            </NlmButton>
            <NlmButton variant="ghost" :disabled="testingModel || saving" @click="runModelTest()">
              {{ testingModel ? "测试中…" : "测试连通性" }}
            </NlmButton>
            <NlmButton variant="primary" :disabled="saving" @click="onSave">保存</NlmButton>
            <NlmButton variant="ghost" @click="resetForm">取消</NlmButton>
          </div>
        </div>
      </section>

      <section v-else class="settings-main">
        <div v-if="channelError" class="settings-error">{{ channelError }}</div>
        <div v-if="channelLoading" class="rail-hint">加载中…</div>

        <div class="settings-block">
          <h2>通道概览</h2>
          <p class="rail-hint">{{ channelDoc.product }} 可接入多个外部应用通道；凭证保存在本机 `data/channels.json`。</p>
          <div class="provider-grid">
            <div v-for="c in channelDoc.channels || []" :key="c.id" class="provider-card" :class="{ custom: c.id === 'feishu' }">
              <div class="pc-head">
                <strong>{{ c.display_name }}</strong>
                <span class="chip" :class="{ on: c.configured && c.enabled }">
                  {{ c.configured ? (c.enabled ? "已接入" : "已配置未启用") : "未配置" }}
                </span>
              </div>
              <div class="pc-meta">{{ c.id }} · {{ c.hint }}</div>
              <div v-if="c.source" class="pc-meta">来源: {{ c.source }}</div>
            </div>
          </div>
        </div>

        <div class="settings-block editor">
          <h2>飞书 Channel</h2>
          <p class="rail-hint">
            在飞书开放平台创建企业自建应用，把 App ID / App Secret 填入下方，即可将该应用加入 Nexus Lark Mind。
            推荐开启「长连接」接收事件（无需公网回调）。
          </p>
          <div class="form-grid">
            <label>
              <span>显示名</span>
              <input v-model="feishuForm.display_name" placeholder="飞书" />
            </label>
            <label>
              <span>App ID</span>
              <input v-model="feishuForm.app_id" placeholder="cli_xxxxxxxx" autocomplete="off" />
            </label>
            <label class="span2">
              <span>App Secret{{ feishu?.app_secret_set ? "（留空则保留原值）" : "" }}</span>
              <input
                v-model="feishuForm.app_secret"
                type="password"
                placeholder="填写飞书应用 Secret"
                autocomplete="off"
              />
            </label>
            <label>
              <span>Verification Token（可选）</span>
              <input v-model="feishuForm.verification_token" type="password" autocomplete="off" />
            </label>
            <label>
              <span>Encrypt Key（可选）</span>
              <input v-model="feishuForm.encrypt_key" type="password" autocomplete="off" />
            </label>
            <label class="check">
              <input v-model="feishuForm.enabled" type="checkbox" />
              启用飞书通道
            </label>
            <label class="check">
              <input v-model="feishuForm.use_long_connection" type="checkbox" />
              使用长连接收事件
            </label>
          </div>
          <p v-if="feishu" class="discover-hint">
            当前有效 App ID: {{ feishu.app_id_effective || "—" }}
            <template v-if="feishu.app_secret_preview"> · Secret {{ feishu.app_secret_preview }}</template>
          </p>
          <p v-if="feishuTestHint" class="discover-hint">{{ feishuTestHint }}</p>
          <div class="form-actions">
            <NlmButton variant="ghost" :disabled="channelTesting || channelSaving" @click="onTestFeishu">
              {{ channelTesting ? "测试中…" : "测试连通性" }}
            </NlmButton>
            <NlmButton variant="primary" :disabled="channelSaving" @click="onSaveFeishu">保存并接入</NlmButton>
            <NlmButton variant="ghost" :disabled="channelSaving" @click="reloadFeishu">重载长连接</NlmButton>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  color: var(--ink);
}
.settings-top {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 16, 24, 0.72);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}
.settings-brand h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: -0.03em;
}
.settings-brand p {
  margin: 2px 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.settings-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 0;
  max-width: 1100px;
  width: 100%;
  margin: 0 auto;
  overflow: hidden;
}
.settings-nav {
  padding: 16px 12px;
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  overscroll-behavior: contain;
  min-height: 0;
}
.nav-item {
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}
.nav-item.active {
  background: rgba(58, 156, 240, 0.12);
  color: var(--ink);
}
.settings-main {
  padding: 18px 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  overflow-y: auto;
  overscroll-behavior: contain;
  min-height: 0;
}
.settings-block h2 {
  margin: 0 0 6px;
  font-size: 15px;
}
.block-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
.provider-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
}
.provider-card.custom {
  border-color: rgba(58, 156, 240, 0.25);
}
.pc-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.pc-meta {
  margin-top: 4px;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.pc-meta.mono {
  font-family: var(--mono);
  word-break: break-all;
}
.pc-models {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.pc-actions {
  margin-top: 10px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--muted);
}
.chip.on {
  color: var(--teal);
  border-color: rgba(43, 184, 160, 0.4);
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.form-grid .span2 {
  grid-column: 1 / -1;
}
.form-grid input,
.form-grid select {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ink);
  border-radius: 7px;
  padding: 8px 10px;
  font: inherit;
  font-size: var(--fs-sm);
}
.form-grid .check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.form-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.discover-hint {
  margin: 8px 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.settings-error {
  color: var(--danger);
  font-size: var(--fs-sm);
}
.default-row {
  max-width: 320px;
}
.default-row :deep(select) {
  max-width: none;
  width: 100%;
}
@media (max-width: 820px) {
  .settings-body {
    grid-template-columns: 1fr;
  }
  .settings-nav {
    border-right: 0;
    border-bottom: 1px solid var(--line);
    flex-direction: row;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
