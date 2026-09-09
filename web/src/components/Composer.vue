<script setup>
import { computed } from "vue";
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
  sessionUsage: { type: Object, default: () => ({}) },
  items: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  cwd: { type: String, default: "" },
  workspaceTitle: { type: String, default: "" },
  busy: Boolean,
});

const emit = defineEmits([
  "update:modelValue",
  "update:providerId",
  "update:modelName",
  "update:toolsEnabled",
  "update:agentMode",
  "update:autoAccept",
  "provider-change",
  "model-change",
  "send",
  "stop",
]);

const tokenStat = computed(() => formatUsage(props.sessionUsage));
const actionTitle = computed(() => (props.busy ? "终止" : "发送"));
const canSend = computed(() => !props.busy && !!(props.modelValue || "").trim());

const lastPromptTokens = computed(() => {
  for (let i = props.items.length - 1; i >= 0; i -= 1) {
    const it = props.items[i];
    if (it?.kind === "msg" && it.role === "assistant" && it.usage?.prompt_tokens) {
      return Number(it.usage.prompt_tokens) || 0;
    }
  }
  return Number(props.sessionUsage?.prompt_tokens || 0);
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

function onPrimary() {
  if (props.busy) emit("stop");
  else emit("send");
}
</script>

<template>
  <form class="composer" @submit.prevent="onPrimary">
    <div class="composer-input-row">
      <NlmTextarea
        :model-value="modelValue"
        :disabled="busy"
        placeholder="输入消息 · Enter 发送 · Shift+Enter 换行"
        @update:model-value="emit('update:modelValue', $event)"
        @submit-enter="!busy && emit('send')"
      />
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

    <div class="composer-bar">
      <NlmSelect
        class="composer-provider"
        :model-value="providerId"
        :options="providerOptions"
        :disabled="providersDisabled"
        aria-label="Provider"
        title="Provider（下次发送生效）"
        @update:model-value="emit('update:providerId', $event); emit('provider-change', $event)"
      />
      <NlmSelect
        class="composer-model"
        :model-value="modelName"
        :options="modelOptions"
        :disabled="modelsDisabled"
        aria-label="Model"
        title="Model（下次发送生效）"
        @update:model-value="emit('update:modelName', $event); emit('model-change', $event)"
      />
      <label class="tools-toggle" title="允许模型调用已启用的插件工具">
        <input
          type="checkbox"
          :checked="toolsEnabled"
          :disabled="busy"
          @change="emit('update:toolsEnabled', $event.target.checked)"
        />
        工具
      </label>
      <label
        class="tools-toggle mode-toggle"
        :class="{ on: agentMode === 'plan' }"
        title="计划模式：先列大纲，接受后再执行"
      >
        <input
          type="checkbox"
          :checked="agentMode === 'plan'"
          @change="emit('update:agentMode', $event.target.checked ? 'plan' : 'agent')"
        />
        计划
      </label>
      <label
        class="tools-toggle mode-toggle"
        :class="{ on: autoAccept }"
        title="自动接受：shell/写文件无需逐条确认"
      >
        <input
          type="checkbox"
          :checked="autoAccept"
          @change="emit('update:autoAccept', $event.target.checked)"
        />
        自动接受
      </label>
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
  </form>
</template>

<style scoped>
.composer-input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: end;
}

.composer-input-row :deep(.nlm-textarea) {
  padding-right: 12px;
}

.composer-action {
  width: 36px;
  height: 36px;
  margin-bottom: 6px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--muted);
  cursor: pointer;
  transition: background 140ms ease, border-color 140ms ease, color 120ms ease, opacity 120ms ease;
}

.composer-action .icon {
  width: 18px;
  height: 18px;
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

.composer-bar :deep(.composer-provider.nlm-select) {
  flex: 0 1 110px;
  max-width: 130px;
}

.composer-bar :deep(.composer-model.nlm-select) {
  flex: 0 1 160px;
  max-width: 180px;
}

.composer-meter-slot {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.token-stat {
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: nowrap;
}

.cache-stat {
  color: rgba(167, 139, 250, 0.9);
}

.cost-stat {
  color: rgba(110, 231, 183, 0.9);
}
</style>
