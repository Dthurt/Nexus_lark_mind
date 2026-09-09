<script setup>
import { nextTick, ref, watch } from "vue";

const props = defineProps({
  rows: { type: Array, default: () => [] },
  followTail: { type: Boolean, default: true },
  selectedId: String,
});
const emit = defineEmits(["select", "inspect", "update:followTail"]);

const scroller = ref(null);
const userPinned = ref(false);

watch(
  () => props.rows.length,
  async () => {
    if (!props.followTail || userPinned.value) return;
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  }
);

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  userPinned.value = !nearBottom;
  emit("update:followTail", nearBottom);
}

function kindClass(row) {
  return `tr-${row.kind}${row.error ? " tr-error" : ""}${row.phase ? ` tr-${row.phase}` : ""}`;
}
</script>

<template>
  <div class="trajectory">
    <div class="traj-toolbar">
      <span class="traj-label">Trajectory · 事件账本</span>
      <label class="traj-follow">
        <input
          type="checkbox"
          :checked="followTail && !userPinned"
          @change="emit('update:followTail', $event.target.checked); userPinned = !$event.target.checked"
        />
        跟随尾部
      </label>
    </div>
    <div ref="scroller" class="traj-list" @scroll="onScroll">
      <div v-if="!rows.length" class="traj-empty">发送消息后，此处按回合记录工具与回复。</div>
      <button
        v-for="row in rows"
        :key="row.id"
        type="button"
        class="traj-row"
        :class="[kindClass(row), { selected: selectedId === row.id }]"
        @click="emit('select', row.id); emit('inspect', row)"
      >
        <span class="traj-idx">#{{ row.seq }}</span>
        <span class="traj-kind">{{ row.kind }}</span>
        <span class="traj-sum">{{ row.summary || row.title }}</span>
        <span v-if="row.durationMs != null" class="traj-meta">{{ Number(row.durationMs).toFixed?.(0) }}ms</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.trajectory {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.traj-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 2px;
}
.traj-label {
  font-size: var(--fs-xs);
  color: var(--muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.traj-follow {
  font-size: var(--fs-xs);
  color: var(--muted);
  display: inline-flex;
  gap: 4px;
  align-items: center;
  cursor: pointer;
}
.traj-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 4px 0 8px;
}
.traj-empty {
  margin: auto;
  color: var(--muted);
  font-size: var(--fs-sm);
  padding: 40px 16px;
  text-align: center;
}
.traj-row {
  display: grid;
  grid-template-columns: 40px 72px 1fr auto;
  gap: 8px;
  align-items: center;
  text-align: left;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.02);
  color: inherit;
  border-radius: 7px;
  padding: 6px 8px;
  font: inherit;
  cursor: pointer;
}
.traj-row:hover {
  background: rgba(255, 255, 255, 0.04);
}
.traj-row.selected {
  border-color: rgba(58, 156, 240, 0.4);
  background: rgba(58, 156, 240, 0.1);
}
.traj-idx {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
}
.traj-kind {
  font-family: var(--mono);
  font-size: 10px;
  text-transform: uppercase;
  color: var(--accent);
}
.tr-tool .traj-kind { color: var(--tool); }
.tr-user .traj-kind { color: var(--teal); }
.tr-system .traj-kind { color: var(--muted); }
.tr-error .traj-kind { color: var(--danger); }
.tr-turn .traj-sum { font-weight: 600; }
.traj-sum {
  font-size: var(--fs-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.traj-meta {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
}
</style>
