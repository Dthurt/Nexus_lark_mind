<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { estimateContextOccupancy, formatCompactTokens } from "@/utils/contextEstimate";

const props = defineProps({
  items: { type: Array, default: () => [] },
  tools: { type: Array, default: () => [] },
  modelName: { type: String, default: "" },
  cwd: { type: String, default: "" },
  workspaceTitle: { type: String, default: "" },
  lastPromptTokens: { type: Number, default: 0 },
  draft: { type: String, default: "" },
});

const open = ref(false);
const rootRef = ref(null);
const panelRef = ref(null);
const panelStyle = ref({});

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

function placePanel() {
  const anchor = rootRef.value?.querySelector?.(".ctx-trigger") || rootRef.value;
  if (!anchor) return;
  const r = anchor.getBoundingClientRect();
  const width = 280;
  const gap = 8;
  let left = r.right - width;
  left = Math.min(Math.max(8, left), window.innerWidth - width - 8);
  const bottom = Math.max(8, window.innerHeight - r.top + gap);
  panelStyle.value = {
    position: "fixed",
    left: `${left}px`,
    bottom: `${bottom}px`,
    width: `${width}px`,
    zIndex: 1200,
  };
}

async function toggle() {
  open.value = !open.value;
  if (open.value) {
    await nextTick();
    placePanel();
  }
}

function onDocPointer(e) {
  if (!open.value) return;
  const t = e.target;
  if (!(t instanceof Node)) return;
  if (rootRef.value?.contains(t)) return;
  if (panelRef.value?.contains(t)) return;
  open.value = false;
}

function onKey(e) {
  if (e.key === "Escape") open.value = false;
}

function onReposition() {
  if (open.value) placePanel();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointer);
  document.addEventListener("keydown", onKey);
  window.addEventListener("resize", onReposition);
  window.addEventListener("scroll", onReposition, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocPointer);
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", onReposition);
  window.removeEventListener("scroll", onReposition, true);
});

watch(
  () => props.modelName,
  () => {
    /* capacity may change */
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

    <Teleport to="body">
      <div
        v-if="open"
        ref="panelRef"
        class="ctx-panel"
        role="dialog"
        aria-label="上下文用量"
        :style="panelStyle"
      >
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
    </Teleport>
  </span>
</template>

<style scoped>
.ctx-meter {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
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
  background: var(--surface-soft);
}
.track {
  fill: none;
  stroke: color-mix(in srgb, var(--ink) 18%, transparent);
  stroke-width: 2;
}
.fill {
  fill: none;
  stroke: color-mix(in srgb, var(--muted) 90%, transparent);
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
</style>

<!-- Panel is teleported; unscoped theme tokens still apply via :root -->
<style>
.ctx-panel {
  box-sizing: border-box;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--panel-solid);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
  cursor: default;
}
.ctx-panel .ctx-header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ctx-panel .ctx-headline {
  color: var(--muted);
}
.ctx-panel .ctx-percent {
  color: var(--ink);
  font-weight: 600;
}
.ctx-panel .ctx-figures {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  font-weight: 500;
}
.ctx-panel .ctx-bar {
  display: flex;
  gap: 1px;
  margin: 10px 0 12px;
  height: 4px;
  border-radius: 999px;
  background: var(--surface-soft);
  overflow: hidden;
}
.ctx-panel .ctx-seg {
  flex: none;
  min-width: 2px;
  height: 100%;
  border-radius: 1px;
}
.ctx-panel .seg-system {
  background: #7aa2c8;
}
.ctx-panel .seg-tools {
  background: #a78bfa;
}
.ctx-panel .seg-messages {
  background: #3a9cf0;
}
.ctx-panel .seg-free {
  background: color-mix(in srgb, var(--ink) 14%, transparent);
}
.ctx-panel .ctx-rows {
  margin: 0;
}
.ctx-panel .ctx-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 0;
}
.ctx-panel .ctx-row dt {
  display: flex;
  align-items: center;
  gap: 0;
  color: var(--muted);
}
.ctx-panel .ctx-row dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.ctx-panel .swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
}
.ctx-panel .ctx-note {
  margin: 10px 0 0;
  font-size: 10px;
  color: var(--muted);
  opacity: 0.85;
}
</style>
