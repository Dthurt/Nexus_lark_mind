<script setup>
import { computed } from "vue";
import { pretty } from "@/utils/pretty";

const props = defineProps({
  item: { type: Object, required: true },
});
const emit = defineEmits(["inspect"]);

const statusLabel = computed(() => {
  if (props.item.error) return "失败";
  if (props.item.status === "running") return "运行中";
  if (props.item.status === "interrupted") return "已中断";
  if (props.item.status === "idle" || props.item.output) return "完成";
  return props.item.status || "subagent";
});

const summary = computed(() => {
  const parts = [
    props.item.label || props.item.name || "subagent",
    props.item.mode ? String(props.item.mode) : null,
    statusLabel.value,
  ].filter(Boolean);
  return parts.join(" · ");
});

const nestedTools = computed(() => props.item.childTools || []);
</script>

<template>
  <details
    class="subagent-card"
    :class="[item.status || (item.error ? 'fail' : item.output ? 'ok' : 'running')]"
    :open="!!item.open"
    @toggle="item.open = $event.target.open"
  >
    <summary>
      <span class="tool-chevron" aria-hidden="true" />
      <span class="sa-badge">SUB</span>
      <span class="sa-name">{{ summary }}</span>
      <span v-if="item.subagentId" class="sa-meta">{{ item.subagentId }}</span>
    </summary>
    <div class="sa-body">
      <div v-if="item.prompt" class="sa-block">
        <label>Input</label>
        <pre>{{ item.prompt }}</pre>
      </div>
      <div v-if="item.streamText" class="sa-block">
        <label>Output{{ item.status === 'running' ? ' (streaming)' : '' }}</label>
        <pre class="sa-stream">{{ item.streamText }}</pre>
      </div>
      <div v-if="nestedTools.length" class="sa-block">
        <label>Child tools</label>
        <div class="sa-tools">
          <div v-for="(t, i) in nestedTools" :key="t.id || i" class="sa-tool-row" :class="t.status">
            <span class="sa-tool-name">{{ t.name }}</span>
            <span class="sa-tool-meta">{{ t.success === false ? 'fail' : t.success ? 'ok' : '…' }}</span>
          </div>
        </div>
      </div>
      <div v-if="item.error" class="sa-block">
        <label>Error</label>
        <pre>{{ pretty(item.error) }}</pre>
      </div>
      <div v-else-if="item.output && item.output !== item.streamText" class="sa-block">
        <label>Final</label>
        <pre>{{ item.output }}</pre>
      </div>
      <div class="sa-actions">
        <button
          v-if="item.activityId"
          type="button"
          class="tool-inspect"
          @click.stop.prevent="emit('inspect', item.activityId)"
        >
          查看活动
        </button>
      </div>
    </div>
  </details>
</template>

<style scoped>
.subagent-card {
  align-self: flex-start;
  width: fit-content;
  max-width: min(100%, 560px);
  animation: fade 180ms ease both;
}

.subagent-card summary {
  list-style: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  font-size: var(--fs-sm);
  font-weight: 500;
  user-select: none;
  border: 1px solid rgba(167, 139, 250, 0.35);
  border-radius: 999px;
  background: rgba(167, 139, 250, 0.08);
  color: #c4b5fd;
}

.subagent-card summary::-webkit-details-marker {
  display: none;
}

.subagent-card summary:hover {
  color: #ede9fe;
  border-color: rgba(167, 139, 250, 0.55);
}

.subagent-card[open] {
  width: min(100%, 560px);
  border: 1px solid rgba(167, 139, 250, 0.35);
  background: rgba(167, 139, 250, 0.07);
  border-radius: var(--radius);
}

.subagent-card[open] summary {
  display: flex;
  width: 100%;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #ede9fe;
}

.subagent-card.running summary {
  border-color: rgba(167, 139, 250, 0.55);
}

.subagent-card.ok summary {
  border-color: rgba(167, 139, 250, 0.4);
}

.subagent-card.fail summary {
  border-color: rgba(224, 112, 112, 0.45);
  color: #f0a0a0;
}

.sa-badge {
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: #c4b5fd;
  background: rgba(167, 139, 250, 0.18);
  border-radius: 4px;
  padding: 1px 6px;
}

.sa-name {
  font-family: var(--mono);
  font-size: var(--fs-sm);
}

.sa-meta {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 10px;
  color: rgba(196, 181, 253, 0.7);
}

.sa-body {
  padding: 2px 10px 10px;
  display: grid;
  gap: 8px;
}

.sa-block label {
  display: block;
  font-size: var(--fs-xs);
  color: rgba(196, 181, 253, 0.75);
  margin-bottom: 3px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.sa-block pre,
.sa-stream {
  margin: 0;
  padding: 8px;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid rgba(167, 139, 250, 0.18);
  font-family: var(--mono);
  font-size: var(--fs-xs);
  line-height: 1.4;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  color: var(--ink);
}

.sa-tools {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sa-tool-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(167, 139, 250, 0.15);
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
}

.sa-tool-row.ok {
  border-color: rgba(43, 184, 160, 0.3);
}

.sa-tool-row.fail {
  border-color: rgba(224, 112, 112, 0.35);
}

.sa-actions {
  display: flex;
  justify-content: flex-end;
}

.tool-inspect {
  border: 1px solid rgba(167, 139, 250, 0.3);
  background: transparent;
  color: #c4b5fd;
  font: inherit;
  font-size: var(--fs-xs);
  border-radius: 6px;
  padding: 3px 8px;
  cursor: pointer;
}
</style>
