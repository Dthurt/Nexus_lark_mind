<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useWorkspaces } from "@/composables/useWorkspaces";

const props = defineProps({
  compact: { type: Boolean, default: false },
});
const emit = defineEmits(["pick", "created"]);

const {
  workspaces,
  loading,
  error,
  browse,
  sshHosts,
  sshConfigHosts,
  sshConfigPath,
  sshBrowse,
  load,
  loadSshHosts,
  loadSshConfigHosts,
  importSshConfig,
  create,
  createSsh,
  upsertSshHost,
  testSshHost,
  browsePath,
  browseSsh,
} = useWorkspaces();

const tab = ref("local"); // local | ssh
const sshMode = ref("config"); // config | saved | manual
const pathInput = ref("");
const busy = ref(false);
const hint = ref("");
const hintOk = ref(false);
const showBrowser = ref(false);

const selectedHostId = ref("");
const hostForm = reactive({
  id: "",
  label: "",
  host: "",
  port: 22,
  username: "",
  auth_type: "password",
  password: "",
  private_key: "",
  default_path: "~",
});

const filteredWorkspaces = computed(() =>
  workspaces.value.filter((w) => (tab.value === "ssh" ? w.kind === "ssh" : w.kind !== "ssh"))
);

const selectedHost = computed(() => sshHosts.value.find((h) => h.id === selectedHostId.value) || null);

const importedAliases = computed(() =>
  new Set(sshHosts.value.filter((h) => h.source === "ssh_config").map((h) => h.ssh_config_alias))
);

function setHint(msg, ok = false) {
  hint.value = msg;
  hintOk.value = ok;
}

async function pickExisting(ws) {
  emit("pick", ws);
}

async function addFromInput() {
  const path = pathInput.value.trim();
  if (!path) {
    setHint("请输入本机目录绝对路径");
    return;
  }
  busy.value = true;
  setHint("正在加入…");
  try {
    const ws = await create(path);
    pathInput.value = "";
    setHint(`已加入 ${ws.title}`, true);
    emit("created", ws);
    emit("pick", ws);
  } catch (err) {
    setHint(String(err.message || err));
  } finally {
    busy.value = false;
  }
}

async function openBrowser() {
  showBrowser.value = true;
  setHint("");
  try {
    await browsePath(pathInput.value.trim() || "");
  } catch (err) {
    setHint(String(err.message || err));
  }
}

async function goParent() {
  if (!browse.value?.parent) return;
  await browsePath(browse.value.parent);
}

async function enterDir(entry) {
  if (!entry.is_dir) return;
  await browsePath(entry.path);
}

async function useBrowsePath() {
  if (!browse.value?.path) return;
  pathInput.value = browse.value.path;
  await addFromInput();
  showBrowser.value = false;
}

async function switchTab(next) {
  tab.value = next;
  setHint("");
  if (next === "ssh") {
    await loadSshData();
  }
}

async function loadSshData() {
  try {
    await Promise.all([loadSshHosts(), loadSshConfigHosts()]);
  } catch (err) {
    setHint(String(err.message || err));
  }
}

async function saveHost() {
  busy.value = true;
  setHint("保存 SSH 主机…");
  try {
    const host = await upsertSshHost({ ...hostForm, port: Number(hostForm.port) || 22, source: "direct" });
    selectedHostId.value = host.id;
    sshMode.value = "saved";
    setHint(`已保存 ${host.display}`, true);
    hostForm.password = "";
    hostForm.private_key = "";
  } catch (err) {
    setHint(String(err.message || err));
  } finally {
    busy.value = false;
  }
}

async function importConfigEntry(entry) {
  busy.value = true;
  setHint(`导入 ${entry.alias}…`);
  try {
    const host = await importSshConfig(entry.alias);
    selectedHostId.value = host.id;
    sshMode.value = "saved";
    setHint(`已导入 ${entry.alias}`, true);
  } catch (err) {
    setHint(String(err.message || err));
  } finally {
    busy.value = false;
  }
}

function selectSavedHost(host) {
  if (!host?.id) return;
  selectedHostId.value = host.id;
  sshMode.value = "saved";
  setHint("");
}

function useImportedAlias(alias) {
  const host = sshHosts.value.find((h) => h.ssh_config_alias === alias);
  if (host) selectSavedHost(host);
}

async function onTestHost() {
  if (!selectedHostId.value) {
    setHint("请先选择一台主机");
    return;
  }
  busy.value = true;
  setHint("测试 SSH 连通性…");
  try {
    const data = await testSshHost(selectedHostId.value);
    setHint(data.message || "连通成功", true);
  } catch (err) {
    setHint(String(err.message || err));
  } finally {
    busy.value = false;
  }
}

async function openSshBrowser() {
  if (!selectedHostId.value) {
    setHint("请先选择 SSH 主机");
    return;
  }
  showBrowser.value = true;
  setHint("浏览远程目录…");
  try {
    const host = sshHosts.value.find((h) => h.id === selectedHostId.value);
    await browseSsh(selectedHostId.value, host?.default_path || "~");
    setHint("");
  } catch (err) {
    setHint(String(err.message || err));
  }
}

async function goSshParent() {
  if (!sshBrowse.value?.parent || !selectedHostId.value) return;
  await browseSsh(selectedHostId.value, sshBrowse.value.parent);
}

async function enterSshDir(entry) {
  if (!entry.is_dir || !selectedHostId.value) return;
  await browseSsh(selectedHostId.value, entry.path);
}

async function useSshBrowsePath() {
  if (!sshBrowse.value?.path || !selectedHostId.value) return;
  busy.value = true;
  setHint("正在把远程目录加入 Workspace…");
  try {
    const ws = await createSsh({
      ssh_host_id: selectedHostId.value,
      path: sshBrowse.value.path,
    });
    setHint(`已接入远程 ${ws.title}`, true);
    showBrowser.value = false;
    emit("created", ws);
    emit("pick", ws);
  } catch (err) {
    setHint(String(err.message || err));
  } finally {
    busy.value = false;
  }
}

function hostBadge(host) {
  if (host.source === "ssh_config") return "config";
  if (host.auth_type === "key") return "key";
  if (host.auth_type === "agent") return "agent";
  return "pwd";
}

onMounted(async () => {
  await load();
});
</script>

<template>
  <div class="ws-picker" :class="{ compact: props.compact }">
    <header class="ws-hero">
      <div class="hero-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M4 7h16M4 12h10M4 17h14" stroke-linecap="round" />
          <rect x="3" y="4" width="18" height="16" rx="2" />
        </svg>
      </div>
      <div>
        <h3>选择工作目录</h3>
        <p>本机文件夹，或通过 SSH 连接远程机器上的目录，作为 Coding Agent 的工作区。</p>
      </div>
    </header>

    <div class="ws-segment">
      <button type="button" :class="{ active: tab === 'local' }" @click="switchTab('local')">
        <span class="seg-icon local" />
        本机目录
      </button>
      <button type="button" :class="{ active: tab === 'ssh' }" @click="switchTab('ssh')">
        <span class="seg-icon ssh" />
        远程 SSH
      </button>
    </div>

    <div v-if="error" class="ws-alert error">{{ error }}</div>
    <div v-if="loading" class="ws-empty">加载中…</div>

    <section v-if="filteredWorkspaces.length" class="ws-section">
      <h4>{{ tab === "ssh" ? "已接入的远程工作区" : "最近使用" }}</h4>
      <div class="ws-cards">
        <button
          v-for="ws in filteredWorkspaces"
          :key="ws.id"
          type="button"
          class="ws-card"
          @click="pickExisting(ws)"
        >
          <div class="card-top">
            <span class="card-kind" :class="ws.kind === 'ssh' ? 'ssh' : 'local'">
              {{ ws.kind === "ssh" ? "SSH" : "本地" }}
            </span>
            <span class="card-status" :class="{ ok: ws.exists || ws.kind === 'ssh' }">
              {{ ws.kind === "ssh" ? "远程" : ws.exists ? "可用" : "缺失" }}
            </span>
          </div>
          <strong class="card-title">{{ ws.title }}</strong>
          <span class="card-path">{{ ws.path }}</span>
        </button>
      </div>
    </section>

    <section v-else-if="!loading" class="ws-empty-block">
      <p>{{ tab === "ssh" ? "还没有远程工作区" : "还没有本机工作区" }}</p>
      <span>{{ tab === "ssh" ? "从下方连接 SSH 并选择远程目录" : "在下方输入或浏览本机目录" }}</span>
    </section>

    <!-- Local -->
    <section v-if="tab === 'local'" class="ws-panel">
      <div class="path-row">
        <input
          v-model="pathInput"
          class="path-input"
          placeholder="例如 E:\projects\my-app 或 /home/user/proj"
          @keyup.enter="addFromInput"
        />
        <div class="path-actions">
          <NlmButton variant="ghost" :disabled="busy" @click="openBrowser">浏览</NlmButton>
          <NlmButton variant="primary" :disabled="busy" @click="addFromInput">加入并选用</NlmButton>
        </div>
      </div>
    </section>

    <!-- SSH -->
    <section v-else class="ws-panel ssh-panel">
      <div class="ssh-subnav">
        <button type="button" :class="{ active: sshMode === 'config' }" @click="sshMode = 'config'">
          本机 SSH 配置
        </button>
        <button type="button" :class="{ active: sshMode === 'saved' }" @click="sshMode = 'saved'">
          已保存主机
        </button>
        <button type="button" :class="{ active: sshMode === 'manual' }" @click="sshMode = 'manual'">
          手动添加
        </button>
      </div>

      <!-- SSH config -->
      <div v-if="sshMode === 'config'" class="ssh-config">
        <p class="config-hint">
          读取 <code>{{ sshConfigPath || "~/.ssh/config" }}</code> 中的 Host 别名，一键导入后连接。
        </p>
        <div v-if="!sshConfigHosts.length" class="ws-empty-block small">
          <p>未找到 Host 条目</p>
          <span>请确认本机已安装 OpenSSH 并配置了 ~/.ssh/config</span>
        </div>
        <div v-else class="host-grid">
          <article
            v-for="entry in sshConfigHosts"
            :key="entry.alias"
            class="host-card"
            :class="{ imported: importedAliases.has(entry.alias) }"
          >
            <div class="host-card-head">
              <strong>{{ entry.alias }}</strong>
              <span v-if="importedAliases.has(entry.alias)" class="mini-badge ok">已导入</span>
            </div>
            <p class="host-meta">{{ entry.display }}</p>
            <p v-if="entry.identity_file" class="host-key">密钥 {{ entry.identity_file }}</p>
            <div class="host-card-actions">
              <NlmButton
                v-if="!importedAliases.has(entry.alias)"
                variant="primary"
                :disabled="busy"
                @click="importConfigEntry(entry)"
              >
                导入
              </NlmButton>
              <NlmButton v-else variant="ghost" :disabled="busy" @click="useImportedAlias(entry.alias)">
                选用
              </NlmButton>
            </div>
          </article>
        </div>
      </div>

      <!-- Saved hosts -->
      <div v-else-if="sshMode === 'saved'" class="ssh-saved">
        <div v-if="!sshHosts.length" class="ws-empty-block small">
          <p>还没有保存的主机</p>
          <span>从「本机 SSH 配置」导入，或在「手动添加」里填写连接信息</span>
        </div>
        <div v-else class="host-grid">
          <article
            v-for="host in sshHosts"
            :key="host.id"
            class="host-card selectable"
            :class="{ selected: selectedHostId === host.id }"
            @click="selectSavedHost(host)"
          >
            <div class="host-card-head">
              <strong>{{ host.label }}</strong>
              <span class="mini-badge" :class="hostBadge(host)">{{ hostBadge(host) }}</span>
            </div>
            <p class="host-meta">{{ host.display }}</p>
            <p v-if="host.source === 'ssh_config'" class="host-key">来自 ~/.ssh/config · {{ host.ssh_config_alias }}</p>
          </article>
        </div>
        <div v-if="selectedHost" class="selected-bar">
          <span>已选 <strong>{{ selectedHost.label }}</strong></span>
          <div class="selected-actions">
            <NlmButton variant="ghost" :disabled="busy" @click="onTestHost">测试连接</NlmButton>
            <NlmButton variant="primary" :disabled="busy" @click="openSshBrowser">浏览远程目录</NlmButton>
          </div>
        </div>
      </div>

      <!-- Manual form -->
      <div v-else class="host-form">
        <div class="form-grid">
          <label>
            <span>显示名</span>
            <input v-model="hostForm.label" placeholder="prod-box" />
          </label>
          <label>
            <span>Host</span>
            <input v-model="hostForm.host" placeholder="192.168.1.10" />
          </label>
          <label>
            <span>Port</span>
            <input v-model.number="hostForm.port" type="number" />
          </label>
          <label>
            <span>Username</span>
            <input v-model="hostForm.username" placeholder="ubuntu" />
          </label>
          <label class="span2">
            <span>认证方式</span>
            <div class="auth-pills">
              <button type="button" :class="{ active: hostForm.auth_type === 'password' }" @click="hostForm.auth_type = 'password'">密码</button>
              <button type="button" :class="{ active: hostForm.auth_type === 'key' }" @click="hostForm.auth_type = 'key'">私钥</button>
            </div>
          </label>
          <label v-if="hostForm.auth_type === 'password'" class="span2">
            <span>Password</span>
            <input v-model="hostForm.password" type="password" autocomplete="off" />
          </label>
          <label v-else class="span2">
            <span>Private Key（PEM 或本机路径）</span>
            <textarea v-model="hostForm.private_key" rows="3" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
          </label>
          <label class="span2">
            <span>默认远程路径</span>
            <input v-model="hostForm.default_path" placeholder="~ 或 /home/ubuntu/proj" />
          </label>
        </div>
        <div class="form-actions">
          <NlmButton variant="primary" :disabled="busy" @click="saveHost">保存并选用</NlmButton>
        </div>
      </div>
    </section>

    <p v-if="hint" class="ws-hint" :class="{ ok: hintOk }">{{ hint }}</p>

    <!-- File browser overlay -->
    <Teleport to="body">
      <div v-if="showBrowser" class="browser-overlay" @click.self="showBrowser = false">
        <div class="browser-modal">
          <header class="browser-head">
            <h4>{{ tab === "ssh" ? "选择远程目录" : "选择本机目录" }}</h4>
            <button type="button" class="close-btn" aria-label="关闭" @click="showBrowser = false">×</button>
          </header>
          <div v-if="tab === 'local' && browse" class="browser-body">
            <div class="browser-bar">
              <NlmButton variant="ghost" :disabled="!browse.parent" @click="goParent">上级</NlmButton>
              <code>{{ browse.path }}</code>
            </div>
            <div class="browser-list">
              <button
                v-for="e in browse.entries"
                :key="e.path"
                type="button"
                class="browser-row"
                @click="enterDir(e)"
              >
                <span class="kind" :class="{ dir: e.is_dir }">{{ e.is_dir ? "目录" : "文件" }}</span>
                <span>{{ e.name }}</span>
              </button>
            </div>
            <footer class="browser-foot">
              <NlmButton variant="primary" @click="useBrowsePath">选用此目录</NlmButton>
            </footer>
          </div>
          <div v-else-if="tab === 'ssh' && sshBrowse" class="browser-body">
            <div class="browser-bar">
              <NlmButton variant="ghost" :disabled="!sshBrowse.parent" @click="goSshParent">上级</NlmButton>
              <code>{{ sshBrowse.path }}</code>
            </div>
            <div class="browser-list">
              <button
                v-for="e in sshBrowse.entries"
                :key="e.path"
                type="button"
                class="browser-row"
                @click="enterSshDir(e)"
              >
                <span class="kind" :class="{ dir: e.is_dir }">{{ e.is_dir ? "目录" : "文件" }}</span>
                <span>{{ e.name }}</span>
              </button>
            </div>
            <footer class="browser-foot">
              <NlmButton variant="primary" @click="useSshBrowsePath">选用远程目录</NlmButton>
            </footer>
          </div>
          <div v-else class="browser-body loading">加载目录…</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.ws-picker {
  width: min(720px, 100%);
  margin: 0 auto;
  text-align: left;
}

.ws-hero {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(43, 184, 160, 0.08), rgba(58, 156, 240, 0.06));
  border: 1px solid rgba(43, 184, 160, 0.18);
}

.hero-icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  color: var(--teal);
  padding: 8px;
  border-radius: 10px;
  background: rgba(43, 184, 160, 0.12);
}

.hero-icon svg {
  width: 100%;
  height: 100%;
}

.ws-hero h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}

.ws-hero p {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--muted);
  line-height: 1.5;
}

.ws-segment {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 4px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--line);
}

.ws-segment button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--muted);
  border-radius: 9px;
  padding: 10px 12px;
  font: inherit;
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.ws-segment button.active {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.08);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.06);
}

.seg-icon {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.seg-icon.local {
  background: #6ea8fe;
}

.seg-icon.ssh {
  background: var(--teal);
}

.ws-section h4 {
  margin: 0 0 10px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  font-weight: 600;
}

.ws-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
  margin-bottom: 16px;
  max-height: 200px;
  overflow: auto;
  padding-right: 2px;
}

.ws-card {
  text-align: left;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  padding: 12px;
  cursor: pointer;
  font: inherit;
  color: var(--ink);
  transition: border-color 0.15s, transform 0.1s;
}

.ws-card:hover {
  border-color: rgba(43, 184, 160, 0.45);
  transform: translateY(-1px);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.card-kind {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.card-kind.local {
  color: #6ea8fe;
  background: rgba(110, 168, 254, 0.12);
}

.card-kind.ssh {
  color: var(--teal);
  background: rgba(43, 184, 160, 0.12);
}

.card-status {
  font-size: 10px;
  color: var(--muted);
}

.card-status.ok {
  color: var(--teal);
}

.card-title {
  display: block;
  font-size: var(--fs-sm);
  margin-bottom: 4px;
}

.card-path {
  display: block;
  font-size: 10px;
  color: var(--muted);
  font-family: var(--mono);
  word-break: break-all;
  line-height: 1.4;
}

.ws-panel {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px;
  background: rgba(0, 0, 0, 0.15);
}

.path-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.path-input {
  width: 100%;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ink);
  border-radius: 10px;
  padding: 10px 12px;
  font: inherit;
  font-family: var(--mono);
  font-size: var(--fs-sm);
}

.path-input:focus {
  outline: none;
  border-color: rgba(43, 184, 160, 0.5);
}

.path-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.ssh-subnav {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.ssh-subnav button {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  border-radius: 999px;
  padding: 6px 12px;
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}

.ssh-subnav button.active {
  color: var(--ink);
  border-color: rgba(43, 184, 160, 0.45);
  background: rgba(43, 184, 160, 0.1);
}

.config-hint {
  margin: 0 0 12px;
  font-size: var(--fs-xs);
  color: var(--muted);
  line-height: 1.5;
}

.config-hint code {
  font-size: 10px;
  color: var(--teal);
}

.host-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.host-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
}

.host-card.imported {
  border-color: rgba(43, 184, 160, 0.25);
}

.host-card.selectable {
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.host-card.selectable:hover {
  border-color: rgba(58, 156, 240, 0.35);
}

.host-card.selected {
  border-color: rgba(43, 184, 160, 0.55);
  background: rgba(43, 184, 160, 0.08);
}

.host-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.host-card-head strong {
  font-size: var(--fs-sm);
}

.host-meta {
  margin: 0 0 4px;
  font-size: 11px;
  color: var(--muted);
  font-family: var(--mono);
}

.host-key {
  margin: 0 0 8px;
  font-size: 10px;
  color: var(--muted);
  opacity: 0.85;
  word-break: break-all;
}

.host-card-actions {
  margin-top: 8px;
}

.mini-badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--muted);
}

.mini-badge.ok {
  color: var(--teal);
  border-color: rgba(43, 184, 160, 0.35);
}

.mini-badge.config {
  color: #a78bfa;
  border-color: rgba(167, 139, 250, 0.35);
}

.mini-badge.key,
.mini-badge.agent {
  color: #6ea8fe;
  border-color: rgba(110, 168, 254, 0.35);
}

.selected-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(43, 184, 160, 0.06);
  border: 1px solid rgba(43, 184, 160, 0.2);
  font-size: var(--fs-sm);
}

.selected-actions {
  display: flex;
  gap: 8px;
}

.host-form input,
.host-form textarea {
  width: 100%;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ink);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}

.host-form input:focus,
.host-form textarea:focus {
  outline: none;
  border-color: rgba(43, 184, 160, 0.45);
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

.auth-pills {
  display: flex;
  gap: 6px;
}

.auth-pills button {
  flex: 1;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  border-radius: 8px;
  padding: 8px;
  font: inherit;
  cursor: pointer;
}

.auth-pills button.active {
  color: var(--ink);
  border-color: rgba(43, 184, 160, 0.45);
  background: rgba(43, 184, 160, 0.1);
}

.form-actions {
  margin-top: 12px;
}

.ws-empty-block {
  text-align: center;
  padding: 20px 12px;
  margin-bottom: 14px;
  border: 1px dashed var(--line);
  border-radius: 12px;
  color: var(--muted);
}

.ws-empty-block.small {
  padding: 16px;
}

.ws-empty-block p {
  margin: 0 0 4px;
  color: var(--ink);
  font-size: var(--fs-sm);
}

.ws-empty-block span {
  font-size: var(--fs-xs);
}

.ws-alert.error {
  color: var(--danger);
  font-size: var(--fs-sm);
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 80, 80, 0.08);
  border: 1px solid rgba(255, 80, 80, 0.2);
}

.ws-empty {
  font-size: var(--fs-xs);
  color: var(--muted);
  margin-bottom: 10px;
}

.ws-hint {
  margin: 12px 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}

.ws-hint.ok {
  color: var(--teal);
}

.compact .ws-cards {
  max-height: 120px;
}

/* Browser modal */
.browser-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.browser-modal {
  width: min(560px, 100%);
  max-height: min(70vh, 520px);
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--panel, #1a1d24);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
  overflow: hidden;
}

.browser-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
}

.browser-head h4 {
  margin: 0;
  font-size: var(--fs-sm);
}

.close-btn {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}

.browser-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.browser-body.loading {
  padding: 24px;
  text-align: center;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.browser-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  background: rgba(0, 0, 0, 0.2);
}

.browser-bar code {
  flex: 1;
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
}

.browser-list {
  flex: 1;
  overflow: auto;
  min-height: 180px;
  max-height: 320px;
}

.browser-row {
  width: 100%;
  display: flex;
  gap: 10px;
  text-align: left;
  border: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  background: transparent;
  color: var(--ink);
  padding: 9px 12px;
  font: inherit;
  cursor: pointer;
}

.browser-row:hover {
  background: rgba(43, 184, 160, 0.08);
}

.browser-row .kind {
  flex-shrink: 0;
  width: 2.4em;
  font-size: 10px;
  color: var(--muted);
}

.browser-row .kind.dir {
  color: var(--teal);
}

.browser-foot {
  padding: 10px 12px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .ws-segment {
    grid-template-columns: 1fr;
  }

  .selected-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .selected-actions {
    justify-content: stretch;
  }
}
</style>
