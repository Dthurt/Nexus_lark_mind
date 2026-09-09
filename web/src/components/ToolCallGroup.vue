<script setup>
import { computed, ref } from "vue";
import ToolCard from "./ToolCard.vue";

const props = defineProps({
  tools: { type: Array, default: () => [] },
});
const emit = defineEmits(["inspect"]);

const open = ref(false);

function shortName(name) {
  const raw = String(name || "tool");
  return raw.replace(/^builtin_workspace_/, "").replace(/^cli_/, "").split(".").pop();
}

const summaryLabel = computed(() => {
  const names = props.tools.map((t) => shortName(t.name));
  const unique = [];
  for (const n of names) {
    if (!unique.includes(n)) unique.push(n);
  }
  const preview = unique.slice(0, 4).join(" · ");
  const n = props.tools.length;
  if (n <= 1) return preview || "tool";
  return `${n} 个工具 · ${preview}${unique.length > 4 ? "…" : ""}`;
});

const hasFail = computed(() =>
  props.tools.some((t) => t.status === "fail" || t.error != null || t.success === false)
);
const pending = computed(() =>
  props.tools.some((t) => t.result == null && t.error == null && t.success == null)
);
</script>

<template>
  <details
    class="tool-group"
    :class="{ fail: hasFail, ok: !hasFail && !pending, pending }"
    :open="open"
    @toggle="open = $event.target.open"
  >
    <summary>
      <span class="tool-chevron" aria-hidden="true" />
      <span class="tool-badge">{{ pending ? "RUN" : hasFail ? "ERR" : "TOOLS" }}</span>
      <span class="tool-name">{{ summaryLabel }}</span>
      <span v-if="pending" class="tool-meta">运行中</span>
      <span v-else-if="hasFail" class="tool-meta">有失败</span>
    </summary>
    <div class="tool-group-body">
      <ToolCard
        v-for="t in tools"
        :key="t.id"
        :item="t"
        nested
        @inspect="emit('inspect', $event)"
      />
    </div>
  </details>
</template>

<style scoped>
.tool-group {
  align-self: flex-start;
  width: fit-content;
  max-width: min(100%, 560px);
  animation: fade 180ms ease both;
}

.tool-group summary {
  list-style: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  font-size: var(--fs-sm);
  font-weight: 500;
  user-select: none;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--muted);
}

.tool-group summary::-webkit-details-marker {
  display: none;
}

.tool-group summary:hover {
  color: var(--ink);
  border-color: rgba(255, 255, 255, 0.16);
}

.tool-group.ok summary {
  border-color: rgba(43, 184, 160, 0.28);
}

.tool-group.fail summary {
  border-color: rgba(224, 112, 112, 0.35);
}

.tool-group.pending summary {
  border-color: rgba(201, 162, 39, 0.35);
}

.tool-group[open] {
  width: min(100%, 560px);
  border: 1px solid rgba(201, 162, 39, 0.22);
  background: rgba(201, 162, 39, 0.04);
  border-radius: var(--radius);
}

.tool-group[open] summary {
  display: flex;
  width: 100%;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
}

.tool-group-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 2px 10px 10px;
}

.tool-badge {
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: var(--tool);
  background: rgba(201, 162, 39, 0.12);
  border-radius: 4px;
  padding: 1px 6px;
}

.tool-name {
  font-family: var(--mono);
  font-size: var(--fs-sm);
}

.tool-meta {
  margin-left: auto;
  color: var(--muted);
  font-size: var(--fs-xs);
}
</style>
