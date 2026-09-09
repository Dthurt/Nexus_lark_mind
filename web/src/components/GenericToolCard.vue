<script setup>
import { pretty } from "@/utils/pretty";

const props = defineProps({
  item: { type: Object, required: true },
  nested: { type: Boolean, default: false },
});
const emit = defineEmits(["inspect"]);

function metaLabel() {
  if (props.item.durationMs != null) {
    const n = Number(props.item.durationMs);
    return `${Number.isFinite(n) ? n.toFixed(1) : props.item.durationMs} ms`;
  }
  return props.item.callId || "";
}
</script>

<template>
  <details
    class="tool-card"
    :class="[item.status, { nested }]"
    :open="!!item.open"
    @toggle="item.open = $event.target.open"
  >
    <summary>
      <span class="tool-chevron" aria-hidden="true" />
      <span class="tool-badge">{{ item.badge || "CALL" }}</span>
      <span class="tool-name">{{ item.name }}</span>
      <span class="tool-meta">{{ metaLabel() }}</span>
    </summary>
    <div class="tool-body">
      <div v-if="item.arguments != null" class="tool-block">
        <label>Arguments</label>
        <pre>{{ pretty(item.arguments) }}</pre>
      </div>
      <div v-if="item.error != null" class="tool-block">
        <label>Error</label>
        <pre>{{ pretty(item.error) }}</pre>
      </div>
      <div v-else-if="item.result != null" class="tool-block">
        <label>Result</label>
        <pre>{{ pretty(item.result) }}</pre>
      </div>
      <div class="tool-actions">
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
.tool-actions {
  display: flex;
  justify-content: flex-end;
}
.tool-inspect {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  border-radius: 6px;
  padding: 3px 8px;
  cursor: pointer;
}
.tool-inspect:hover {
  color: var(--ink);
  border-color: rgba(58, 156, 240, 0.4);
}
</style>
