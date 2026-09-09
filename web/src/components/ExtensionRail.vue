<script setup>
import { pretty } from "@/utils/pretty";
import { computed, ref, watch } from "vue";

const props = defineProps({
  plugins: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  activity: { type: Array, default: () => [] },
  usage: { type: Object, default: () => ({}) },
  pluginError: String,
  reloading: Boolean,
  highlightActivityId: String,
  modelValue: { type: String, default: "plugins" }, // active panel
});
const emit = defineEmits([
  "update:modelValue",
  "toggle-plugin",
  "reload",
  "reload-one",
  "retry-plugin",
  "view-schema",
]);

const panel = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const tabs = [
  { id: "plugins", label: "插件" },
  { id: "activity", label: "本回合" },
  { id: "usage", label: "用量" },
];

const expanded = ref({});
const schemaTool = ref(null);
const toggling = ref({});
const activityRefs = ref({});

watch(
  () => props.highlightActivityId,
  async (id) => {
    if (!id) return;
    panel.value = "activity";
  }
);

function stateClass(p) {
  return `st-${p.state || "unknown"}`;
}

function onToggle(plugin, enabled) {
  toggling.value[plugin.plugin_id] = true;
  emit("toggle-plugin", plugin.plugin_id, enabled);
  setTimeout(() => {
    toggling.value[plugin.plugin_id] = false;
  }, 500);
}

function toggleExpand(id) {
  expanded.value[id] = !expanded.value[id];
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
</script>

<template>
  <aside class="rail" aria-label="扩展面板">
    <div class="rail-head">
      <NlmTabs v-model="panel" :tabs="tabs" />
      <NlmButton
        v-if="panel === 'plugins'"
        variant="ghost"
        class="rail-reload"
        title="从磁盘重载全部插件"
        :disabled="reloading"
        @click="emit('reload')"
      >
        {{ reloading ? "…" : "↻" }}
      </NlmButton>
    </div>
    <div class="rail-body">
      <div v-show="panel === 'plugins'" class="rail-panel active">
        <div class="rail-hint">启停写入 prefs；仅 ready 的工具会进入下一轮模型调用</div>
        <div class="plugin-list">
          <div v-if="pluginError" class="rail-hint">{{ pluginError }}</div>
          <div v-else-if="!plugins.length" class="rail-hint">暂无插件</div>
          <div
            v-for="p in plugins"
            :key="p.plugin_id"
            class="plugin-card"
            :class="[stateClass(p), { 'is-error': p.state === 'error' }]"
          >
            <div class="plugin-card-head">
              <button type="button" class="meta-btn" @click="toggleExpand(p.plugin_id)">
                <div class="meta">
                  <div class="name-row">
                    <span class="name">{{ p.name || p.plugin_id }}</span>
                    <span class="state-badge" :class="stateClass(p)">{{ p.state }}</span>
                  </div>
                  <div class="id">
                    {{ p.plugin_id }} · {{ p.kind || "" }}
                    <template v-if="p.version"> · v{{ p.version }}</template>
                  </div>
                </div>
              </button>
              <div class="plugin-actions">
                <NlmButton
                  variant="ghost"
                  title="重载此插件"
                  :disabled="reloading"
                  @click="emit('reload-one', p.plugin_id)"
                >↻</NlmButton>
                <NlmSwitch
                  :model-value="!!p.enabled"
                  :disabled="!!toggling[p.plugin_id] || reloading"
                  title="启用/禁用"
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
              <div v-if="p.description" class="desc">{{ p.description }}</div>
              <div v-if="p.health" class="health">
                health: {{ p.health.status }}
                <template v-if="p.health.last_teardown_at">
                  · teardown {{ p.health.last_teardown_at }}
                </template>
              </div>
              <div class="tools">
                <button
                  v-for="t in p.tools || []"
                  :key="t.name"
                  type="button"
                  class="tool-chip-btn"
                  :title="t.description || t.name"
                  @click="showSchema(t)"
                >
                  <NlmChip :active="p.state === 'ready'">{{ t.name || "?" }}</NlmChip>
                </button>
                <NlmChip v-if="!(p.tools || []).length">no tools</NlmChip>
              </div>
            </div>
            <div v-else class="tools compact">
              <NlmChip
                v-for="t in (p.tools || []).slice(0, 4)"
                :key="t.name"
                :active="p.state === 'ready'"
              >{{ t.name || "?" }}</NlmChip>
              <span v-if="(p.tools || []).length > 4" class="more">+{{ p.tools.length - 4 }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-show="panel === 'activity'" class="rail-panel active">
        <div class="rail-hint">本会话最近的工具调用</div>
        <div class="activity-list">
          <div v-if="!activity.length" class="rail-hint">暂无工具活动</div>
          <div
            v-for="item in activity"
            :key="item.id || item.at"
            class="activity-item"
            :class="{ highlight: isHighlighted(item) }"
            :ref="(el) => { if (item.id) activityRefs[item.id] = el }"
          >
            <span class="kind">{{ item.kind }}</span>
            <span class="name">{{ item.name }}</span>
            <pre>{{ pretty(item.detail) }}</pre>
          </div>
        </div>
      </div>

      <div v-show="panel === 'usage'" class="rail-panel active">
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
        <div class="rail-hint">已启用工具（模型可见）</div>
        <div class="tool-list">
          <div v-if="!tools.length" class="rail-hint">当前无已启用工具</div>
          <button
            v-for="t in tools"
            :key="(t.openai_name || t.name) + (t.plugin_id || '')"
            type="button"
            class="tool-row rich"
            @click="showSchema(t)"
          >
            <div class="tmain">
              <span class="tname">{{ t.name || "?" }}</span>
              <span class="pid">{{ t.plugin_id || "" }}</span>
            </div>
            <div v-if="t.description" class="tdesc">{{ t.description }}</div>
            <div v-if="t.openai_name" class="toname">{{ t.openai_name }}</div>
          </button>
        </div>
      </div>
    </div>

    <div v-if="schemaTool" class="schema-modal" @click.self="closeSchema">
      <div class="schema-card">
        <div class="schema-head">
          <strong>{{ schemaTool.name }}</strong>
          <NlmButton variant="ghost" @click="closeSchema">关闭</NlmButton>
        </div>
        <p v-if="schemaTool.description" class="schema-desc">{{ schemaTool.description }}</p>
        <p v-if="schemaTool.openai_name" class="schema-meta">openai: {{ schemaTool.openai_name }}</p>
        <pre>{{ pretty(schemaTool.inputSchema || schemaTool.parameters || {}) }}</pre>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.rail-head {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  border-bottom: 1px solid var(--line);
}
.rail-head :deep(.nlm-tabs) {
  border-bottom: 0;
  padding-right: 0;
}
.rail-reload {
  margin: 0 8px 6px 0;
  min-width: 28px;
}
.rail-panel.active {
  display: flex;
}
.meta-btn {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  padding: 0;
  cursor: pointer;
  font: inherit;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 6px;
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
  border-color: rgba(224, 112, 112, 0.45);
}
.state-badge.st-disabled {
  color: var(--muted);
}
.plugin-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.plugin-card.is-error {
  border-color: rgba(224, 112, 112, 0.35);
  background: rgba(224, 112, 112, 0.06);
}
.err {
  margin-top: 6px;
  font-size: var(--fs-xs);
  color: var(--danger);
  word-break: break-word;
}
.retry-row {
  margin-top: 6px;
}
.hints {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hint {
  font-size: var(--fs-xs);
  color: #c9a227;
  line-height: 1.35;
}
.health {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  margin-bottom: 6px;
}
.plugin-detail {
  margin-top: 6px;
}
.tools.compact {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.more {
  font-size: 10px;
  color: var(--muted);
}
.tool-chip-btn {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
}
.activity-item.highlight {
  outline: 1px solid rgba(58, 156, 240, 0.55);
  background: rgba(58, 156, 240, 0.12);
}
.tool-row.rich {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  text-align: left;
  width: 100%;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.02);
  color: inherit;
  font: inherit;
}
.tool-row.rich:hover {
  border-color: rgba(58, 156, 240, 0.35);
}
.tmain {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.tdesc {
  color: var(--muted);
  font-size: var(--fs-xs);
  line-height: 1.35;
}
.toname {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  opacity: 0.85;
}
.schema-modal {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 10px;
  z-index: 5;
}
.rail {
  position: relative;
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
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.schema-desc {
  margin: 0 0 6px;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.schema-meta {
  margin: 0 0 6px;
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: var(--muted);
}
.schema-card pre {
  margin: 0;
  padding: 8px;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid var(--line);
  font-family: var(--mono);
  font-size: var(--fs-xs);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow: auto;
}
</style>
