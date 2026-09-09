<script setup>
import { computed, ref, watch } from "vue";
import { formatDiffStats } from "@/utils/lineDiff";

const props = defineProps({
  path: { type: String, default: "" },
  rows: { type: Array, default: () => [] }, // { type, text, oldLine, newLine }
  stats: { type: Object, default: () => ({ adds: 0, dels: 0 }) },
  /** Soft cap of visible rows before "show more" */
  maxRows: { type: Number, default: 80 },
  defaultOpen: { type: Boolean, default: true },
});

const open = ref(props.defaultOpen);
const expanded = ref(false);

watch(
  () => props.defaultOpen,
  (v) => {
    open.value = v;
  }
);

const statsText = computed(() => formatDiffStats(props.stats));
const truncated = computed(() => props.rows.length > props.maxRows && !expanded.value);
const visibleRows = computed(() =>
  truncated.value ? props.rows.slice(0, props.maxRows) : props.rows
);
const hiddenCount = computed(() => Math.max(0, props.rows.length - props.maxRows));
</script>

<template>
  <details class="file-diff" :open="open" @toggle="open = $event.target.open">
    <summary class="file-diff-summary">
      <span class="tool-chevron" aria-hidden="true" />
      <span class="file-diff-path">{{ path || "file" }}</span>
      <span class="file-diff-stats">
        <span v-if="stats.adds" class="stat-add">+{{ stats.adds }}</span>
        <span v-if="stats.dels" class="stat-del">−{{ stats.dels }}</span>
        <span v-if="!stats.adds && !stats.dels">{{ statsText }}</span>
      </span>
    </summary>
    <div class="file-diff-body" role="table" aria-label="文件变更">
      <div
        v-for="(row, idx) in visibleRows"
        :key="idx"
        class="diff-row"
        :class="row.type"
        role="row"
      >
        <span class="diff-sign" aria-hidden="true">{{
          row.type === "add" ? "+" : row.type === "del" ? "−" : " "
        }}</span>
        <span class="diff-ln old">{{ row.oldLine ?? "" }}</span>
        <span class="diff-ln new">{{ row.newLine ?? "" }}</span>
        <code class="diff-code">{{ row.text }}</code>
      </div>
      <button
        v-if="truncated"
        type="button"
        class="diff-more"
        @click="expanded = true"
      >
        展开其余 {{ hiddenCount }} 行…
      </button>
      <button
        v-else-if="rows.length > maxRows"
        type="button"
        class="diff-more"
        @click="expanded = false"
      >
        收起
      </button>
    </div>
  </details>
</template>

<style scoped>
.file-diff {
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  overflow: hidden;
}

.file-diff-summary {
  list-style: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: var(--fs-xs);
  color: var(--muted);
  user-select: none;
  border-bottom: 1px solid transparent;
}

.file-diff[open] > .file-diff-summary {
  border-bottom-color: var(--line);
}

.file-diff-summary::-webkit-details-marker {
  display: none;
}

.file-diff-path {
  font-family: var(--mono);
  color: var(--ink);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-diff-stats {
  margin-left: auto;
  display: inline-flex;
  gap: 6px;
  font-family: var(--mono);
  flex-shrink: 0;
}

.stat-add {
  color: #3fb950;
  font-weight: 600;
}

.stat-del {
  color: #f85149;
  font-weight: 600;
}

.file-diff-body {
  max-height: 360px;
  overflow: auto;
  scrollbar-width: thin;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.45;
}

.diff-row {
  display: grid;
  grid-template-columns: 14px 36px 36px minmax(0, 1fr);
  gap: 0;
  padding: 0 4px 0 0;
  white-space: pre;
}

.diff-row.add {
  background: rgba(46, 160, 67, 0.18);
}

.diff-row.del {
  background: rgba(248, 81, 73, 0.18);
}

.diff-row.ctx {
  background: transparent;
}

.diff-sign {
  text-align: center;
  color: var(--muted);
  user-select: none;
}

.diff-row.add .diff-sign {
  color: #6ee7b7;
}

.diff-row.del .diff-sign {
  color: #f0a0a0;
}

.diff-ln {
  text-align: right;
  padding: 0 6px;
  color: rgba(127, 147, 168, 0.55);
  user-select: none;
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}

.diff-code {
  display: block;
  padding: 0 8px;
  color: var(--ink);
  background: transparent;
  border: 0;
  font: inherit;
  white-space: pre;
  overflow-x: auto;
  min-width: 0;
}

.diff-more {
  display: block;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
}

.diff-more:hover {
  color: var(--accent);
}
</style>
