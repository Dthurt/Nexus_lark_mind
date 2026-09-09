<script setup>
import { computed } from "vue";
import { pretty } from "@/utils/pretty";
import { lineDiff, writeFileAsDiff } from "@/utils/lineDiff";
import FileDiffBlock from "./FileDiffBlock.vue";
import GenericToolCard from "./GenericToolCard.vue";

const props = defineProps({
  item: { type: Object, required: true },
  nested: { type: Boolean, default: false },
});
defineEmits(["inspect"]);

const result = computed(() => {
  let raw = props.item.result;
  if (raw == null) return null;
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return raw && typeof raw === "object" ? raw : null;
});

const toolKey = computed(() => {
  const n = String(props.item.name || "").toLowerCase();
  if (n.includes("grep")) return "grep";
  if (n.includes("glob")) return "glob";
  if (n.includes("list_dir")) return "list_dir";
  if (n.includes("read_file")) return "read_file";
  if (n.includes("write_file")) return "write_file";
  if (n.includes("edit_file")) return "edit_file";
  if (n.includes("run_shell")) return "run_shell";
  return "other";
});

const badge = computed(() => {
  const map = {
    grep: "GREP",
    glob: "GLOB",
    list_dir: "LS",
    read_file: "READ",
    write_file: "WRITE",
    edit_file: "EDIT",
    run_shell: "SHELL",
  };
  return map[toolKey.value] || props.item.badge || "TOOL";
});

const fileChange = computed(() => {
  const args = props.item.arguments || {};
  const path = args.path || result.value?.path || "";
  if (toolKey.value === "edit_file" && (args.old_string != null || args.new_string != null)) {
    const diff = lineDiff(args.old_string ?? "", args.new_string ?? "");
    return { path, ...diff, kind: "edit" };
  }
  if (toolKey.value === "write_file" && args.content != null) {
    const diff = writeFileAsDiff(args.content);
    return { path, ...diff, kind: "write" };
  }
  return null;
});

const summary = computed(() => {
  const r = result.value;
  const args = props.item.arguments || {};
  if (props.item.error) return String(props.item.error).slice(0, 120);
  if (!r && props.item.status === "running") return "运行中…";
  switch (toolKey.value) {
    case "grep":
      return `${args.pattern || ""} · ${r?.match_count ?? (r?.matches || []).length} 处`;
    case "glob":
      return `${args.pattern || ""} · ${(r?.files || []).length} 个文件`;
    case "list_dir":
      return `${args.path || r?.path || "."} · ${(r?.entries || []).length} 项`;
    case "read_file":
      return `${args.path || r?.path || ""} · L${r?.offset || 1}+`;
    case "write_file":
    case "edit_file": {
      // Path only — +/− counts render as colored spans in the template.
      return args.path || r?.path || "";
    }
    case "run_shell":
      return `exit ${r?.exit_code ?? "?"} · ${(args.command || "").slice(0, 60)}`;
    default:
      return "";
  }
});

const previewLines = computed(() => {
  const r = result.value;
  if (!r) return [];
  if (toolKey.value === "grep") {
    return (r.matches || []).slice(0, 12).map((m) => `${m.path}:${m.line}: ${m.text}`);
  }
  if (toolKey.value === "glob") {
    return (r.files || []).slice(0, 20);
  }
  if (toolKey.value === "list_dir") {
    return (r.entries || []).slice(0, 20).map((e) => `${e.is_dir ? "📁" : "📄"} ${e.name}`);
  }
  if (toolKey.value === "read_file" && r.content) {
    return String(r.content).split("\n").slice(0, 16);
  }
  if (toolKey.value === "run_shell") {
    const out = [r.stdout, r.stderr].filter(Boolean).join("\n").trim();
    return out ? out.split("\n").slice(0, 16) : [];
  }
  return [];
});

const useRich = computed(() => toolKey.value !== "other" && (result.value || props.item.arguments));
const isFileMutation = computed(() => toolKey.value === "write_file" || toolKey.value === "edit_file");
const mutationStats = computed(() => {
  if (!isFileMutation.value || props.item.error) return null;
  const s = fileChange.value?.stats;
  if (!s) return null;
  return { adds: Number(s.adds || 0), dels: Number(s.dels || 0) };
});
</script>

<template>
  <GenericToolCard
    v-if="!useRich"
    :item="item"
    :nested="nested"
    @inspect="$emit('inspect', $event)"
  />
  <details
    v-else
    class="tool-card"
    :class="[
      item.status || (item.error ? 'fail' : 'ok'),
      { nested, 'has-diff': !!fileChange },
    ]"
    :open="!!item.open"
    @toggle="item.open = $event.target.open"
  >
    <summary>
      <span class="tool-chevron" aria-hidden="true" />
      <span class="tool-badge" :class="toolKey">{{ badge }}</span>
      <span class="tool-name">{{ item.name }}</span>
      <span class="tool-meta">
        <span class="tool-meta-path">{{ summary }}</span>
        <span v-if="mutationStats" class="tool-diff-stats" aria-label="行变更统计">
          <span v-if="mutationStats.adds" class="stat-add">+{{ mutationStats.adds }}</span>
          <span v-if="mutationStats.dels" class="stat-del">−{{ mutationStats.dels }}</span>
          <span v-if="!mutationStats.adds && !mutationStats.dels" class="stat-none">无变更</span>
        </span>
      </span>
    </summary>
    <div class="tool-body">
      <div v-if="toolKey === 'run_shell' && item.arguments?.command" class="tool-block">
        <label>Command</label>
        <pre>{{ item.arguments.command }}</pre>
      </div>

      <FileDiffBlock
        v-if="fileChange && !item.error"
        class="file-diff-slot"
        :path="fileChange.path"
        :rows="fileChange.rows"
        :stats="fileChange.stats"
        :default-open="true"
      />

      <div
        v-else-if="item.arguments && !isFileMutation && !['grep', 'glob', 'list_dir', 'read_file'].includes(toolKey)"
        class="tool-block"
      >
        <label>Arguments</label>
        <pre>{{ pretty(item.arguments) }}</pre>
      </div>

      <div v-if="item.error" class="tool-block">
        <label>Error</label>
        <pre>{{ pretty(item.error) }}</pre>
      </div>
      <div v-else-if="previewLines.length" class="tool-block">
        <label>Preview</label>
        <pre class="preview">{{ previewLines.join("\n") }}</pre>
      </div>
      <div v-else-if="result && !fileChange" class="tool-block">
        <label>Result</label>
        <pre>{{ pretty(result) }}</pre>
      </div>

      <div class="tool-actions">
        <button
          v-if="item.activityId"
          type="button"
          class="tool-inspect"
          @click.stop.prevent="$emit('inspect', item.activityId)"
        >
          查看活动
        </button>
      </div>
    </div>
  </details>
</template>

<style scoped>
.preview {
  max-height: 220px;
  overflow: auto;
}
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
.file-diff-slot {
  margin-top: 2px;
}
.tool-card.has-diff {
  max-width: min(100%, 720px);
  width: 100%;
}
.tool-badge.write_file,
.tool-badge.edit_file {
  color: #6ee7b7;
  border-color: rgba(110, 231, 183, 0.35);
  background: rgba(46, 160, 67, 0.12);
}

.tool-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tool-meta-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-diff-stats {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}

.tool-diff-stats .stat-add {
  color: #3fb950;
  font-weight: 600;
}

.tool-diff-stats .stat-del {
  color: #f85149;
  font-weight: 600;
}

.tool-diff-stats .stat-none {
  color: var(--muted);
}
</style>
