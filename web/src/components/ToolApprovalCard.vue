<script setup>
import { computed } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
});
const emit = defineEmits(["resolve"]);

const args = computed(() => props.item.arguments || {});
const base = computed(() => props.item.base || props.item.name || "");
const summary = computed(() => {
  if (base.value === "run_shell") return args.value.command || "";
  if (base.value === "write_file" || base.value === "edit_file") return args.value.path || "";
  return JSON.stringify(args.value).slice(0, 200);
});
const pending = computed(() => props.item.status === "pending");
</script>

<template>
  <div class="approval-card" :class="item.status || 'pending'">
    <div class="approval-head">
      <span class="approval-badge">审批</span>
      <span class="approval-name">{{ item.name }}</span>
      <span v-if="!pending" class="approval-state">{{
        item.status === "allowed" ? "已允许" : item.status === "denied" ? "已拒绝" : item.status
      }}</span>
    </div>
    <pre class="approval-cmd">{{ summary }}</pre>
    <div v-if="pending" class="approval-actions">
      <button type="button" class="btn allow" @click="emit('resolve', { action: 'allow' })">允许</button>
      <button
        type="button"
        class="btn allow-session"
        @click="emit('resolve', { action: 'allow_session' })"
      >
        允许并自动接受
      </button>
      <button type="button" class="btn deny" @click="emit('resolve', { action: 'deny' })">拒绝</button>
    </div>
  </div>
</template>

<style scoped>
.approval-card {
  border: 1px solid rgba(248, 81, 73, 0.35);
  border-radius: 10px;
  background: rgba(248, 81, 73, 0.08);
  padding: 10px 12px;
  max-width: min(100%, 720px);
  display: grid;
  gap: 8px;
}
.approval-card.allowed {
  border-color: rgba(63, 185, 80, 0.4);
  background: rgba(63, 185, 80, 0.08);
}
.approval-card.denied {
  opacity: 0.75;
}
.approval-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-xs);
}
.approval-badge {
  font-weight: 700;
  color: #f85149;
  letter-spacing: 0.04em;
}
.approval-name {
  font-family: var(--mono);
  color: var(--ink);
}
.approval-state {
  margin-left: auto;
  color: var(--muted);
}
.approval-cmd {
  margin: 0;
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--line);
  font-family: var(--mono);
  font-size: var(--fs-xs);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow: auto;
}
.approval-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.btn {
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ink);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}
.btn.allow {
  border-color: rgba(63, 185, 80, 0.5);
  color: #3fb950;
}
.btn.allow-session {
  border-color: rgba(58, 156, 240, 0.5);
  color: var(--accent);
}
.btn.deny {
  border-color: rgba(248, 81, 73, 0.45);
  color: #f85149;
}
.btn:hover {
  filter: brightness(1.1);
}
</style>
