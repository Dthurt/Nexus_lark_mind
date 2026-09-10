<script setup>
import { pretty } from "@/utils/pretty";
import { computed, ref } from "vue";

const props = defineProps({
  dock: { type: Object, required: true },
  plugins: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  activity: { type: Array, default: () => [] },
  usage: { type: Object, default: () => ({}) },
  pluginError: String,
  reloading: Boolean,
  highlightActivityId: String,
  inspectorPayload: { type: Object, default: null },
});

const emit = defineEmits([
  "toggle-plugin",
  "reload",
  "reload-one",
  "retry-plugin",
  "view-schema",
  "save-plugin-config",
]);

const schemaTool = ref(null);
const expanded = ref({});
const toggling = ref({});
const dragging = ref(false);
const configDraft = ref({});
const configSaving = ref({});
const configHint = ref({});

function openPlugin(id) {
  expanded.value[id] = !expanded.value[id];
  if (!expanded.value[id]) return;
  const p = props.plugins.find((x) => x.plugin_id === id);
  if (!p?.config_schema?.fields?.length || configDraft.value[id]) return;
  const draft = {};
  for (const f of p.config_schema.fields) draft[f.key] = f.secret ? "" : f.value || "";
  configDraft.value[id] = draft;
}

async function onSaveConfig(plugin) {
  const id = plugin.plugin_id;
  configSaving.value[id] = true;
  configHint.value[id] = "";
  try {
    emit("save-plugin-config", id, { ...(configDraft.value[id] || {}) });
    configHint.value[id] = "已保存";
  } catch (err) {
    configHint.value[id] = String(err.message || err);
  } finally {
    configSaving.value[id] = false;
  }
}

const state = computed(() => props.dock.state);
const panes = computed(() => {
  const raw = props.dock.visiblePanes;
  if (Array.isArray(raw)) return raw;
  if (raw && Array.isArray(raw.value)) return raw.value;
  return props.dock.state?.panes?.[0] ? [props.dock.state.panes[0]] : [];
});

function paneTabs(pane) {
  return pane.tabs || [];
}

function activeKind(pane) {
  const tab = pane.tabs.find((t) => t.id === pane.activeId);
  return tab?.kind || null;
}

function onToggle(plugin, enabled) {
  toggling.value[plugin.plugin_id] = true;
  emit("toggle-plugin", plugin.plugin_id, enabled);
  setTimeout(() => {
    toggling.value[plugin.plugin_id] = false;
  }, 500);
}

function showSchema(tool) {
  schemaTool.value = tool;
  emit("view-schema", tool);
}

function closeSchema() {
  schemaTool.value = null;
}

function isHighlighted(item) {
  return item.id && item.id === props.highlightActivityId;
}

function startDrag(e) {
  dragging.value = true;
  const startY = e.clientY;
  const startRatio = state.value.ratio;
  const host = e.currentTarget.parentElement;
  function onMove(ev) {
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const y = (ev.clientY - rect.top) / rect.height;
    props.dock.setRatio(y || startRatio);
  }
  function onUp() {
    dragging.value = false;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  }
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}
</script>

<template>
  <aside class="rail dock" aria-label="扩展停靠栏">
    <div class="dock-toolbar">
      <span class="dock-title">Dock</span>
      <div class="dock-actions">
        <NlmButton
          variant="ghost"
          :title="state.split ? '合并面板' : '拆分检查器'"
          @click="state.split ? dock.disableSplit() : dock.enableSplit('inspector')"
        >
          {{ state.split ? "合并" : "拆分" }}
        </NlmButton>
        <NlmButton variant="ghost" title="重载插件" :disabled="reloading" @click="emit('reload')">
          {{ reloading ? "…" : "↻" }}
        </NlmButton>
      </div>
    </div>

    <div class="dock-panes" :class="{ split: state.split }">
      <div
        v-for="(pane, pi) in panes"
        :key="pane.id"
        class="dock-pane"
        :style="
          state.split && pi === 0
            ? { flex: `0 0 ${state.ratio * 100}%` }
            : state.split
              ? { flex: '1 1 auto' }
              : {}
        "
      >
        <div class="dock-tabs">
          <button
            v-for="tab in paneTabs(pane)"
            :key="tab.id"
            type="button"
            class="dock-tab"
            :class="{ active: pane.activeId === tab.id }"
            @click="dock.focusTab(pane.id, tab.id)"
          >
            {{ tab.title }}
            <span
              v-if="pane.id === 'aux' || tab.kind === 'inspector'"
              class="tab-x"
              @click.stop="dock.closeTab(pane.id, tab.id)"
            >×</span>
          </button>
        </div>

        <div class="dock-body">
          <!-- plugins -->
          <div v-show="activeKind(pane) === 'plugins'" class="rail-panel active">
            <div class="rail-hint">启停写入 prefs；仅 ready 进入模型工具列表</div>
            <div class="plugin-list">
              <div v-if="pluginError" class="rail-hint">{{ pluginError }}</div>
              <div v-else-if="!plugins.length" class="rail-hint">暂无插件</div>
              <div
                v-for="p in plugins"
                :key="p.plugin_id"
                class="plugin-card"
                :class="{ 'is-error': p.state === 'error' }"
              >
                <div class="plugin-card-head">
                  <button type="button" class="meta-btn" @click="openPlugin(p.plugin_id)">
                    <div class="meta">
                      <div class="name-row">
                        <span class="name">{{ p.name || p.plugin_id }}</span>
                        <span class="state-badge" :class="'st-' + p.state">{{ p.state }}</span>
                      </div>
                      <div class="id">{{ p.plugin_id }} · {{ p.kind }}</div>
                    </div>
                  </button>
                  <div class="plugin-actions">
                    <NlmButton variant="ghost" @click="emit('reload-one', p.plugin_id)">↻</NlmButton>
                    <NlmSwitch
                      :model-value="!!p.enabled"
                      :disabled="!!toggling[p.plugin_id]"
                      @change="(v) => onToggle(p, v)"
                    />
                  </div>
                </div>
                <div v-if="p.last_error && p.state === 'error'" class="err">{{ p.last_error }}</div>
                <div v-if="p.state === 'error'" class="retry-row">
                  <NlmButton variant="ghost" @click="emit('retry-plugin', p.plugin_id)">重试启用</NlmButton>
                </div>
                <div v-if="(p.config_hints || []).length" class="hints">
                  <div v-for="(h, i) in p.config_hints" :key="i" class="hint">{{ h }}</div>
                </div>
                <div v-if="expanded[p.plugin_id]" class="plugin-detail">
                  <div v-if="p.config_schema?.has_schema" class="plugin-config">
                    <div class="config-title">插件配置</div>
                    <label v-for="f in p.config_schema.fields" :key="f.key" class="config-field">
                      <span>{{ f.label }}<template v-if="f.set && f.secret"> · 已设置 {{ f.preview }}</template></span>
                      <select v-if="f.type === 'select'" v-model="configDraft[p.plugin_id][f.key]">
                        <option v-for="opt in f.options || []" :key="opt" :value="opt">{{ opt }}</option>
                      </select>
                      <input
                        v-else
                        v-model="configDraft[p.plugin_id][f.key]"
                        :type="f.secret || f.type === 'password' ? 'password' : 'text'"
                        :placeholder="f.secret ? (f.set ? '留空则保留原值' : '填写 API Key') : ''"
                        autocomplete="off"
                      />
                      <small v-if="f.hint">{{ f.hint }}</small>
                    </label>
                    <div class="config-actions">
                      <NlmButton variant="primary" :disabled="!!configSaving[p.plugin_id]" @click="onSaveConfig(p)">
                        {{ configSaving[p.plugin_id] ? '保存中…' : '保存配置' }}
                      </NlmButton>
                      <span v-if="configHint[p.plugin_id]" class="hint">{{ configHint[p.plugin_id] }}</span>
                    </div>
                  </div>
                  <div class="tools">
                    <button
                      v-for="t in p.tools || []"
                      :key="t.name"
                      type="button"
                      class="tool-chip-btn"
                      @click="showSchema(t)"
                    >
                      <NlmChip :active="p.state === 'ready'">{{ t.name }}</NlmChip>
                    </button>
                    <NlmChip v-if="!(p.tools || []).length">{{ p.enabled ? 'no tools' : '已禁用' }}</NlmChip>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- activity -->
          <div v-show="activeKind(pane) === 'activity'" class="rail-panel active">
            <div class="rail-hint">本会话工具活动</div>
            <div class="activity-list">
              <div v-if="!activity.length" class="rail-hint">暂无工具活动</div>
              <div
                v-for="item in activity"
                :key="item.id || item.at"
                class="activity-item"
                :class="{ highlight: isHighlighted(item) }"
                @click="dock.openInspector(item)"
              >
                <span class="kind">{{ item.kind }}</span>
                <span class="name">{{ item.name }}</span>
                <pre>{{ pretty(item.detail) }}</pre>
              </div>
            </div>
          </div>

          <!-- usage -->
          <div v-show="activeKind(pane) === 'usage'" class="rail-panel active">
            <div class="usage-card">
              <div class="usage-label">会话累计</div>
              <div class="usage-row"><span>输入</span><strong>{{ Number(usage.prompt_tokens || 0) }}</strong></div>
              <div class="usage-row"><span>输出</span><strong>{{ Number(usage.completion_tokens || 0) }}</strong></div>
              <div class="usage-row">
                <span>合计</span>
                <strong>{{ Number(usage.total_tokens || (usage.prompt_tokens || 0) + (usage.completion_tokens || 0)) }}</strong>
              </div>
              <div class="usage-row">
                <span>缓存命中</span>
                <strong>{{ Number(usage.cached_tokens || 0) }}</strong>
              </div>
              <div class="usage-row">
                <span>命中率</span>
                <strong>
                  {{
                    Number(usage.prompt_tokens || 0) > 0 && Number(usage.cached_tokens || 0) > 0
                      ? ((Number(usage.cached_tokens) / Number(usage.prompt_tokens)) * 100).toFixed(1) + "%"
                      : "0%"
                  }}
                </strong>
              </div>
              <p class="rail-hint">
                {{
                  usage.estimated
                    ? "含估算值（接口未返回 usage 时按约 4 字/token）。"
                    : "优先使用接口返回的 usage；费用估算见输入栏。"
                }}
              </p>
            </div>
            <div class="rail-hint">已启用工具</div>
            <div class="tool-list">
              <button
                v-for="t in tools"
                :key="(t.openai_name || t.name) + (t.plugin_id || '')"
                type="button"
                class="tool-row rich"
                @click="showSchema(t)"
              >
                <div class="tmain">
                  <span class="tname">{{ t.name }}</span>
                  <span class="pid">{{ t.plugin_id }}</span>
                </div>
                <div v-if="t.description" class="tdesc">{{ t.description }}</div>
              </button>
              <div v-if="!tools.length" class="rail-hint">当前无已启用工具</div>
            </div>
          </div>

          <!-- inspector -->
          <div v-show="activeKind(pane) === 'inspector'" class="rail-panel active">
            <div class="rail-hint">检查器 · Trajectory / 活动详情</div>
            <pre class="inspector-pre">{{ pretty(inspectorPayload || pane.tabs.find((t) => t.id === pane.activeId)?.params || { tip: "从 Trajectory 或活动点击一行" }) }}</pre>
          </div>
        </div>

        <div
          v-if="state.split && pi === 0"
          class="dock-splitter"
          :class="{ dragging }"
          @mousedown.prevent="startDrag"
        />
      </div>
    </div>

    <div v-if="schemaTool" class="schema-modal" @click.self="closeSchema">
      <div class="schema-card">
        <div class="schema-head">
          <strong>{{ schemaTool.name }}</strong>
          <NlmButton variant="ghost" @click="closeSchema">关闭</NlmButton>
        </div>
        <pre>{{ pretty(schemaTool.inputSchema || schemaTool.parameters || {}) }}</pre>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.dock {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.dock-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.dock-title {
  font-size: var(--fs-xs);
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.dock-actions {
  display: flex;
  gap: 4px;
}
.dock-panes {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dock-pane {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}
.dock-panes.split .dock-pane {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}
.dock-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 6px 8px 0;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.dock-tab {
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  padding: 6px 8px;
  border-radius: 7px 7px 0 0;
  cursor: pointer;
}
.dock-tab.active {
  color: var(--ink);
  background: rgba(58, 156, 240, 0.12);
  box-shadow: inset 0 -2px 0 var(--accent);
}
.tab-x {
  margin-left: 4px;
  opacity: 0.6;
}
.dock-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.rail-panel.active {
  display: flex;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 10px;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.dock-splitter {
  height: 5px;
  cursor: row-resize;
  background: rgba(255, 255, 255, 0.04);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.dock-splitter.dragging,
.dock-splitter:hover {
  background: rgba(58, 156, 240, 0.2);
}
.meta-btn {
  flex: 1;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  padding: 0;
  cursor: pointer;
  font: inherit;
  min-width: 0;
}
.name-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.state-badge {
  font-family: var(--mono);
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--muted);
  text-transform: uppercase;
}
.state-badge.st-ready {
  color: var(--teal);
  border-color: rgba(43, 184, 160, 0.4);
}
.state-badge.st-error {
  color: var(--danger);
}
.plugin-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.err {
  color: var(--danger);
  font-size: var(--fs-xs);
  margin-top: 6px;
}
.hints .hint {
  font-size: var(--fs-xs);
  color: #c9a227;
}
.tool-chip-btn {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
}
.activity-item {
  cursor: pointer;
}
.activity-item.highlight {
  outline: 1px solid rgba(58, 156, 240, 0.55);
  background: rgba(58, 156, 240, 0.12);
}
.tool-row.rich {
  display: flex;
  flex-direction: column;
  width: 100%;
  text-align: left;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.02);
  color: inherit;
  font: inherit;
}
.tmain {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.tdesc {
  color: var(--muted);
  font-size: var(--fs-xs);
}
.inspector-pre {
  margin: 0;
  padding: 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid var(--line);
  font-family: var(--mono);
  font-size: var(--fs-xs);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 100%;
  overflow: auto;
}
.schema-modal {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: flex-end;
  padding: 10px;
  z-index: 5;
}
.schema-card {
  width: 100%;
  max-height: 70%;
  overflow: auto;
  background: var(--panel-solid);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px;
}
.schema-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.schema-card pre {
  margin: 0;
  font-family: var(--mono);
  font-size: var(--fs-xs);
  white-space: pre-wrap;
}

.plugin-config {
  margin: 8px 0 10px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-soft, rgba(255,255,255,0.03));
}
.config-title { font-size: var(--fs-xs); color: var(--muted); margin-bottom: 6px; }
.config-field { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; font-size: var(--fs-xs); color: var(--muted); }
.config-field input, .config-field select {
  border: 1px solid var(--line);
  background: var(--panel-solid);
  color: var(--ink);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
}
.config-actions { display: flex; gap: 8px; align-items: center; }
</style>
