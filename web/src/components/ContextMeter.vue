<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { estimateContextOccupancy, formatCompactTokens } from "@/utils/contextEstimate";

const props = defineProps({
  items: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  modelName: { type: String, default: "" },
  cwd: { type: String, default: "" },
  workspaceTitle: { type: String, default: "" },
  /** Last turn prompt_tokens from provider usage when available */
  lastPromptTokens: { type: Number, default: 0 },
  draft: { type: String, default: "" },
});

const open = ref(false);
const rootRef = ref(null);

const RADIUS = 5.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const occupancy = computed(() =>
  estimateContextOccupancy({
    items: props.items,
    tools: props.tools,
    modelName: props.modelName,
    cwd: props.cwd,
    workspaceTitle: props.workspaceTitle,
    lastPromptTokens: props.lastPromptTokens,
    draft: props.draft,
  })
);

const percent = computed(() => occupancy.value.percent);
const dash = computed(() => (CIRCUMFERENCE * percent.value) / 100);

const fillClass = computed(() => {
  const p = percent.value;
  if (p >= 90) return "fill danger";
  if (p >= 75) return "fill warn";
  return "fill";
});

const barSegments = computed(() => {
  const occ = occupancy.value;
  const b = occ.breakdown;
  const total = occ.contextWindow || 1;
  const rows = [
    { key: "system", label: "系统提示", tokens: b.systemTokens, color: "seg-system" },
    { key: "tools", label: "工具定义", tokens: b.toolsTokens, color: "seg-tools" },
    { key: "messages", label: "对话消息", tokens: b.messageTokens, color: "seg-messages" },
    { key: "free", label: "剩余可用", tokens: b.freeTokens, color: "seg-free" },
  ];
  return rows
    .map((r) => ({
      ...r,
      width: Math.max(0, (r.tokens / total) * 100),
      display: formatCompactTokens(r.tokens),
    }))
    .filter((r) => r.tokens > 0 || r.key === "free");
});

function toggle() {
  open.value = !open.value;
}

function onDocPointer(e) {
  if (!open.value) return;
  if (rootRef.value && e.target instanceof Node && rootRef.value.contains(e.target)) return;
  open.value = false;
}

function onKey(e) {
  if (e.key === "Escape") open.value = false;
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointer);
  document.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocPointer);
  document.removeEventListener("keydown", onKey);
});

watch(
  () => props.modelName,
  () => {
    /* capacity may change; keep panel if still valid */
  }
);
</script>

<template>
  <span ref="rootRef" class="ctx-meter">
    <button
      type="button"
      class="ctx-trigger"
      :title="`上下文已用 ${percent}%（点击查看构成）`"
      :aria-label="`上下文已用 ${percent}%`"
      :aria-expanded="open"
      aria-haspopup="dialog"
      @click="toggle"
    >
      <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">
        <circle class="track" cx="7" cy="7" :r="RADIUS" />
        <circle
          :class="fillClass"
          cx="7"
          cy="7"
          :r="RADIUS"
          :stroke-dasharray="`${dash} ${CIRCUMFERENCE}`"
          transform="rotate(-90 7 7)"
        />
      </svg>
    </button>

    <div v-if="open" class="ctx-panel" role="dialog" aria-label="上下文用量">
      <div class="ctx-header">
        <span class="ctx-headline">上下文已用</span>
        <span class="ctx-percent">{{ percent }}%</span>
        <span class="ctx-figures">
          ~{{ formatCompactTokens(occupancy.usedTokens) }} /
          {{ formatCompactTokens(occupancy.contextWindow) }}
        </span>
      </div>

      <div class="ctx-bar" aria-hidden="true">
        <div
          v-for="seg in barSegments"
          :key="seg.key"
          class="ctx-seg"
          :class="seg.color"
          :style="{ width: `${Math.max(seg.width, seg.tokens ? 0.4 : 0)}%` }"
        />
      </div>

      <dl class="ctx-rows">
        <div v-for="seg in barSegments" :key="seg.key" class="ctx-row">
          <dt>
            <span class="swatch" :class="seg.color" aria-hidden="true" />
            {{ seg.label }}
          </dt>
          <dd>~{{ seg.display }}</dd>
        </div>
      </dl>
      <p class="ctx-note">估算值；按字符约 4∶1 换算，并结合模型窗口容量。</p>
    </div>
  </span>
</template>

<style scoped>
.ctx-meter {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.ctx-trigger {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
}
.ctx-trigger:hover {
  background: rgba(255, 255, 255, 0.06);
}
.track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.14);
  stroke-width: 2;
}
.fill {
  fill: none;
  stroke: rgba(160, 176, 196, 0.85);
  stroke-width: 2;
  stroke-linecap: round;
  transition: stroke-dasharray 180ms ease, stroke 180ms ease;
}
.fill.warn {
  stroke: rgba(232, 176, 72, 0.95);
}
.fill.danger {
  stroke: rgba(224, 112, 112, 0.95);
}
.ctx-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: 264px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(12, 18, 26, 0.96);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
  cursor: default;
}
.ctx-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ctx-headline {
  color: var(--muted);
}
.ctx-percent {
  color: var(--ink);
  font-weight: 600;
}
.ctx-figures {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  font-weight: 500;
}
.ctx-bar {
  display: flex;
  gap: 1px;
  margin: 10px 0 12px;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.ctx-seg {
  flex: none;
  min-width: 2px;
  height: 100%;
  border-radius: 1px;
}
.seg-system {
  background: #7aa2c8;
}
.seg-tools {
  background: #a78bfa;
}
.seg-messages {
  background: #3a9cf0;
}
.seg-free {
  background: rgba(255, 255, 255, 0.12);
}
.ctx-rows {
  margin: 0;
}
.ctx-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0;
}
.ctx-row dt {
  display: flex;
  align-items: center;
  gap: 0;
  color: var(--muted);
}
.ctx-row dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
}
.ctx-note {
  margin: 10px 0 0;
  font-size: 10px;
  color: var(--muted);
  opacity: 0.85;
}
</style>
