<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatUsage } from "@/utils/pretty";
import {
  cacheHitRate,
  estimateCostCny,
  formatCny,
  formatDurationMs,
  formatTokenCount,
} from "@/utils/pricing";
import ContextMeter from "./ContextMeter.vue";

const props = defineProps({
  modelValue: { type: String, default: "" },
  providerId: String,
  modelName: String,
  providerOptions: { type: Array, default: () => [] },
  modelOptions: { type: Array, default: () => [] },
  providersDisabled: Boolean,
  modelsDisabled: Boolean,
  toolsEnabled: { type: Boolean, default: true },
  agentMode: { type: String, default: "agent" },
  autoAccept: { type: Boolean, default: false },
  multitask: { type: Boolean, default: true },
  sessionUsage: { type: Object, default: () => ({}) },
  items: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  cwd: { type: String, default: "" },
  workspaceTitle: { type: String, default: "" },
  workspaceKind: { type: String, default: "local" },
  gitBranch: { type: String, default: "" },
  gitInsertions: { type: Number, default: 0 },
  gitDeletions: { type: Number, default: 0 },
  busy: Boolean,
});

const emit = defineEmits([
  "update:modelValue",
  "update:providerId",
  "update:modelName",
  "update:toolsEnabled",
  "update:agentMode",
  "update:autoAccept",
  "update:multitask",
  "provider-change",
  "model-change",
  "send",
  "stop",
]);

const menuOpen = ref(false);
const menuRoot = ref(null);
const fileInput = ref(null);
const plusBtn = ref(null);

const tokenStat = computed(() => formatUsage(props.sessionUsage));
const actionTitle = computed(() => (props.busy ? "终止" : "发送"));
const canSend = computed(() => !props.busy && !!(props.modelValue || "").trim());
const planOn = computed(() => props.agentMode === "plan");
const modelLabel = computed(() => {
  const m = (props.modelName || "").trim();
  const p = (props.providerId || "").trim();
  if (m && p) return `${p}/${m}`;
  return m || p || "选择模型";
});

const lastPromptTokens = computed(() => {
  for (let i = props.items.length - 1; i >= 0; i -= 1) {
    const it = props.items[i];
    if (it?.kind === "msg" && it.role === "assistant" && it.usage?.prompt_tokens) {
      return Number(it.usage.prompt_tokens) || 0;
    }
  }
  return 0;
});

const visibleTools = computed(() => (props.toolsEnabled ? props.tools : []));

const sessionCache = computed(() => {
  const cached = Number(props.sessionUsage?.cached_tokens || 0);
  const rate = cacheHitRate(props.sessionUsage);
  return {
    cached,
    rate,
    text:
      cached > 0
        ? `缓存 ${formatTokenCount(cached)} · ${rate >= 10 ? Math.round(rate) : rate.toFixed(1)}%`
        : "缓存 0%",
  };
});

const sessionCost = computed(() => {
  const est = estimateCostCny(props.sessionUsage, {
    modelName: props.modelName,
    providerId: props.providerId,
  });
  return formatCny(est.yuan);
});

const sessionDuration = computed(() => formatDurationMs(props.sessionUsage?.duration_ms));

const sessionStatsTitle = computed(() => {
  const parts = [
    props.sessionUsage?.estimated ? "本会话累计（含估算）" : "本会话累计",
    tokenStat.value,
    sessionCache.value.text,
    sessionCost.value,
  ];
  if (sessionDuration.value) parts.push(`耗时 ${sessionDuration.value}`);
  parts.push("费用按模型大致单价估算（人民币），仅供参考");
  return parts.join(" · ");
});

const voiceSupported =
  typeof window !== "undefined" && !!(window.SpeechRecognition || window.webkitSpeechRecognition);
const listening = ref(false);
const voiceHint = ref("");
let recognition = null;

function stopVoice() {
  try {
    recognition?.stop?.();
  } catch {
    /* ignore */
  }
  listening.value = false;
}

function toggleVoice() {
  if (!voiceSupported || props.busy) return;
  if (listening.value) {
    stopVoice();
    return;
  }
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new Ctor();
  recognition.lang = "zh-CN";
  recognition.interimResults = true;
  recognition.continuous = false;
  voiceHint.value = "";
  let finalText = "";
  recognition.onstart = () => {
    listening.value = true;
  };
  recognition.onerror = (ev) => {
    voiceHint.value =
      ev?.error === "not-allowed" ? "麦克风权限被拒绝" : `语音失败: ${ev?.error || "unknown"}`;
    listening.value = false;
  };
  recognition.onend = () => {
    listening.value = false;
    if (finalText.trim()) {
      const base = (props.modelValue || "").trim();
      const next = base ? `${base} ${finalText.trim()}` : finalText.trim();
      emit("update:modelValue", next);
    }
  };
  recognition.onresult = (ev) => {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
      const piece = ev.results[i][0]?.transcript || "";
      if (ev.results[i].isFinal) finalText += piece;
      else interim += piece;
    }
    if (interim) voiceHint.value = interim;
  };
  try {
    recognition.start();
  } catch (err) {
    voiceHint.value = String(err.message || err);
    listening.value = false;
  }
}

function onPrimary() {
  if (props.busy) emit("stop");
  else emit("send");
}

function toggleMenu() {
  if (props.busy) return;
  menuOpen.value = !menuOpen.value;
}

function closeMenu() {
  menuOpen.value = false;
}

function onDocPointer(ev) {
  if (!menuOpen.value) return;
  const root = menuRoot.value;
  if (root && !root.contains(ev.target)) closeMenu();
}

function onKey(ev) {
  if (ev.key === "Escape") closeMenu();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointer, true);
  document.addEventListener("keydown", onKey, true);
});
onBeforeUnmount(() => {
  stopVoice();
  document.removeEventListener("pointerdown", onDocPointer, true);
  document.removeEventListener("keydown", onKey, true);
});

watch(
  () => props.busy,
  (v) => {
    if (v) closeMenu();
  }
);

function pickFile() {
  fileInput.value?.click?.();
}

function onFilePicked(ev) {
  const file = ev?.target?.files?.[0];
  if (!file) return;
  const name = file.name || "file";
  const pathHint = file.path || name;
  const base = props.modelValue || "";
  const mention = `@${pathHint}`;
  const next = base.trim() ? `${base.trim()}\n${mention}` : mention;
  emit("update:modelValue", next);
  ev.target.value = "";
  closeMenu();
  nextTick(() => plusBtn.value?.focus?.());
}

function setPlan(on) {
  emit("update:agentMode", on ? "plan" : "agent");
}
</script>

<template>
  <form class="composer" @submit.prevent="onPrimary">
    <div class="composer-shell" :class="{ busy }">
      <div class="composer-input-row">
        <div ref="menuRoot" class="composer-plus-wrap">
          <button
            ref="plusBtn"
            type="button"
            class="composer-plus"
            :class="{ open: menuOpen }"
            :disabled="busy"
            title="附件 · 模式 · 模型"
            aria-label="打开附件与模式菜单"
            :aria-expanded="menuOpen"
            @click="toggleMenu"
          >
            <svg class="plus-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 5v14M5 12h14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>

          <div v-if="menuOpen" class="composer-menu" role="menu">
            <button type="button" class="menu-row" role="menuitem" @click="pickFile">
              <span class="menu-ico" aria-hidden="true">📎</span>
              <span class="menu-label">添加文件</span>
            </button>
            <input
              ref="fileInput"
              type="file"
              class="file-hidden"
              @change="onFilePicked"
            />

            <div class="menu-sep" />
            <div class="menu-section-label">模式</div>

            <button
              type="button"
              class="menu-row toggle"
              :class="{ on: planOn }"
              role="menuitemcheckbox"
              :aria-checked="planOn"
              @click="setPlan(!planOn)"
            >
              <span class="menu-label">Plan Mode</span>
              <span class="switch" :class="{ on: planOn }" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="menu-row toggle"
              :class="{ on: autoAccept }"
              role="menuitemcheckbox"
              :aria-checked="autoAccept"
              @click="emit('update:autoAccept', !autoAccept)"
            >
              <span class="menu-label">Accept</span>
              <span class="menu-hint">自动接受写/shell</span>
              <span class="switch" :class="{ on: autoAccept }" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="menu-row toggle"
              :class="{ on: multitask }"
              role="menuitemcheckbox"
              :aria-checked="multitask"
              @click="emit('update:multitask', !multitask)"
            >
              <span class="menu-label">Multi-Task</span>
              <span class="menu-hint">允许子 agent</span>
              <span class="switch" :class="{ on: multitask }" aria-hidden="true" />
            </button>

            <div class="menu-sep" />
            <div class="menu-section-label">工具</div>
            <button
              type="button"
              class="menu-row toggle"
              :class="{ on: toolsEnabled }"
              role="menuitemcheckbox"
              :aria-checked="toolsEnabled"
              @click="emit('update:toolsEnabled', !toolsEnabled)"
            >
              <span class="menu-label">启用工具</span>
              <span class="switch" :class="{ on: toolsEnabled }" aria-hidden="true" />
            </button>

            <div class="menu-sep" />
            <div class="menu-section-label">模型</div>
            <div class="menu-field">
              <label class="field-label">Provider</label>
              <NlmSelect
                class="menu-select"
                :model-value="providerId"
                :options="providerOptions"
                :disabled="providersDisabled"
                aria-label="Provider"
                @update:model-value="
                  emit('update:providerId', $event);
                  emit('provider-change', $event);
                "
              />
            </div>
            <div class="menu-field">
              <label class="field-label">Model</label>
              <NlmSelect
                class="menu-select"
                :model-value="modelName"
                :options="modelOptions"
                :disabled="modelsDisabled"
                aria-label="Model"
                @update:model-value="
                  emit('update:modelName', $event);
                  emit('model-change', $event);
                "
              />
            </div>
          </div>
        </div>

        <NlmTextarea
          class="composer-textarea"
          :model-value="modelValue"
          :disabled="busy"
          placeholder="输入消息 · Enter 发送 · Shift+Enter 换行"
          @update:model-value="emit('update:modelValue', $event)"
          @submit-enter="!busy && emit('send')"
        />
        <div class="composer-actions">
          <button
            v-if="voiceSupported"
            type="button"
            class="composer-action voice"
            :class="{ listening }"
            :disabled="busy"
            :title="listening ? '停止语音输入' : '语音输入'"
            :aria-label="listening ? '停止语音输入' : '语音输入'"
            @click="toggleVoice"
          >
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"
                fill="currentColor"
              />
              <path
                d="M5 11a7 7 0 0 0 14 0M12 18v3"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>
          <button
            type="submit"
            class="composer-action"
            :class="{ stop: busy, ready: canSend }"
            :disabled="!busy && !canSend"
            :title="actionTitle"
            :aria-label="actionTitle"
          >
            <svg v-if="busy" class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" />
            </svg>
            <svg v-else class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 19V5M12 5l-5.5 5.5M12 5l5.5 5.5"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>

      <p v-if="voiceHint" class="voice-hint">{{ voiceHint }}</p>

      <div class="composer-bar">
        <div v-if="cwd" class="composer-workspace" :title="cwd">
          <span class="ws-item path">
            <svg class="ws-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linejoin="round"
              />
            </svg>
            <span class="ws-text">{{ workspaceTitle || cwd }}</span>
          </span>
          <span v-if="gitBranch" class="ws-item branch">
            <svg class="ws-icon" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="6" cy="6" r="2.2" fill="currentColor" />
              <circle cx="6" cy="18" r="2.2" fill="currentColor" />
              <circle cx="18" cy="12" r="2.2" fill="currentColor" />
              <path
                d="M6 8v8M8 6c6 0 8 2 8 6"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
            <span class="ws-text">{{ gitBranch }}</span>
            <span
              v-if="gitInsertions || gitDeletions"
              class="git-diff"
              :title="`相对 HEAD：+${gitInsertions} / -${gitDeletions}`"
            >
              <span v-if="gitInsertions" class="git-ins">+{{ gitInsertions }}</span>
              <span v-if="gitDeletions" class="git-del">-{{ gitDeletions }}</span>
            </span>
          </span>
          <span v-if="workspaceKind === 'ssh'" class="ws-item kind">SSH</span>
        </div>

        <button
          type="button"
          class="model-chip"
          :disabled="busy"
          :title="modelLabel"
          @click="toggleMenu"
        >
          {{ modelLabel }}
        </button>

        <span class="composer-meter-slot" :title="sessionStatsTitle">
          <span class="token-stat">{{ tokenStat }}</span>
          <span class="token-stat cache-stat">{{ sessionCache.text }}</span>
          <span class="token-stat cost-stat">{{ sessionCost }}</span>
          <ContextMeter
            :items="items"
            :tools="visibleTools"
            :model-name="modelName"
            :cwd="cwd"
            :workspace-title="workspaceTitle"
            :last-prompt-tokens="lastPromptTokens"
            :draft="modelValue"
          />
        </span>
      </div>
    </div>
  </form>
</template>

<style scoped>
.composer {
  width: 100%;
  min-width: 0;
}

.composer-shell {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--composer-shell, var(--surface-soft));
  overflow: visible;
  transition: border-color 140ms ease, box-shadow 140ms ease;
}

.composer-shell:focus-within {
  border-color: rgba(58, 156, 240, 0.5);
  box-shadow: 0 0 0 2px rgba(58, 156, 240, 0.12);
}

.composer-input-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 6px;
  align-items: end;
  padding: 8px 8px 4px 8px;
  min-width: 0;
}

.composer-plus-wrap {
  position: relative;
  align-self: end;
  padding-bottom: 6px;
}

.composer-plus {
  position: relative;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--surface-btn, rgba(255, 255, 255, 0.04));
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: color 120ms ease, border-color 120ms ease, background 120ms ease;
}

.composer-plus:hover:not(:disabled),
.composer-plus.open {
  color: var(--ink);
  border-color: color-mix(in srgb, var(--ink) 22%, transparent);
  background: var(--surface-soft);
}

.composer-plus:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.plus-icon {
  width: 13px;
  height: 13px;
}

.composer-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  z-index: 40;
  width: min(300px, 78vw);
  padding: 8px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--panel, #14202c);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.menu-section-label {
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 6px 8px 2px;
}

.menu-sep {
  height: 1px;
  margin: 4px 2px;
  background: var(--line);
}

.menu-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 4px 10px;
  width: 100%;
  text-align: left;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.menu-row:hover {
  background: var(--surface-soft);
}

.menu-row.toggle {
  grid-template-columns: 1fr auto;
}

.menu-row.toggle .menu-hint {
  grid-column: 1;
  grid-row: 2;
  font-size: 11px;
  color: var(--muted);
}

.menu-row.toggle .switch {
  grid-row: 1 / span 2;
}

.menu-ico {
  margin-right: 6px;
}

.menu-label {
  font-weight: 550;
}

.switch {
  width: 34px;
  height: 20px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 35%, transparent);
  position: relative;
  flex-shrink: 0;
  transition: background 140ms ease;
}

.switch::after {
  content: "";
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 999px;
  background: #fff;
  transition: transform 140ms ease;
}

.switch.on {
  background: color-mix(in srgb, var(--teal, #2bb8a0) 75%, #1a7a68);
}

.switch.on::after {
  transform: translateX(14px);
}

.menu-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 8px 8px;
}

.field-label {
  font-size: 11px;
  color: var(--muted);
}

.menu-select {
  width: 100%;
}

.file-hidden {
  display: none;
}

.composer-input-row :deep(.nlm-textarea),
.composer-input-row :deep(.composer-textarea) {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  min-height: 52px;
  max-height: 160px;
  padding: 6px 4px 8px 2px;
  resize: none;
}

.composer-input-row :deep(.nlm-textarea:focus),
.composer-input-row :deep(.composer-textarea:focus) {
  border: 0;
  box-shadow: none;
}

.composer-actions {
  display: flex;
  gap: 6px;
  align-items: flex-end;
  padding-bottom: 6px;
}

.composer-action {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-btn, rgba(255, 255, 255, 0.04));
  color: var(--muted);
  cursor: pointer;
  transition: background 140ms ease, border-color 140ms ease, color 120ms ease, opacity 120ms ease;
}

.composer-action .icon {
  width: 16px;
  height: 16px;
}

.composer-action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.composer-action.ready:not(:disabled) {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(135deg, var(--accent), #2563eb);
}

.composer-action.ready:not(:disabled):hover {
  filter: brightness(1.06);
}

.composer-action.stop {
  color: #fff;
  border-color: rgba(224, 112, 112, 0.55);
  background: rgba(224, 112, 112, 0.85);
}

.composer-action.stop:hover {
  filter: brightness(1.08);
}

.composer-action.voice.listening {
  color: #fff;
  border-color: rgba(224, 112, 112, 0.5);
  background: rgba(224, 112, 112, 0.75);
  animation: pulse-voice 1.1s ease infinite;
}

.voice-hint {
  margin: 0;
  padding: 0 12px 4px;
  font-size: var(--fs-xs);
  color: var(--muted);
}

.composer-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
  padding: 6px 8px 8px;
  border-top: 1px solid var(--composer-divider, var(--line));
  box-sizing: border-box;
}

.composer-workspace {
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
  max-width: 48%;
  flex: 0 1 auto;
}

.ws-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  color: var(--muted);
  font-size: var(--fs-xs);
}

.ws-item.path {
  min-width: 0;
  max-width: 100%;
}

.ws-item.path .ws-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-item.branch {
  color: var(--teal);
  flex-shrink: 0;
}

.ws-item.branch .ws-text {
  max-width: 88px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.git-diff {
  display: inline-flex;
  gap: 4px;
  font-family: var(--mono);
  font-size: 10px;
  margin-left: 2px;
}

.git-ins {
  color: #3ecf8e;
}

.git-del {
  color: #e07070;
}

.ws-item.kind {
  padding: 1px 5px;
  border-radius: 4px;
  border: 1px solid var(--line);
  flex-shrink: 0;
}

.ws-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.model-chip {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-xs);
  font-family: var(--mono);
  padding: 2px 6px;
  cursor: pointer;
}

.model-chip:hover:not(:disabled) {
  color: var(--ink);
  border-color: var(--line);
  background: var(--surface-soft);
}

.model-chip:disabled {
  opacity: 0.5;
  cursor: default;
}

.composer-meter-slot {
  margin-left: auto;
  display: inline-flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 0 1 auto;
  justify-content: flex-end;
}

.token-stat {
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.cache-stat {
  color: rgba(167, 139, 250, 0.9);
}

.cost-stat {
  color: rgba(110, 231, 183, 0.9);
}

@keyframes pulse-voice {
  0%,
  100% {
    filter: brightness(1);
  }
  50% {
    filter: brightness(1.12);
  }
}
</style>
