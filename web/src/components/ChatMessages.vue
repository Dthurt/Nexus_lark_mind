<script setup>
import { computed, nextTick, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";
import ToolCard from "./ToolCard.vue";
import ToolCallGroup from "./ToolCallGroup.vue";
import SubagentCard from "./SubagentCard.vue";
import ToolApprovalCard from "./ToolApprovalCard.vue";
import AskUserForm from "./AskUserForm.vue";
import PlanReviewCard from "./PlanReviewCard.vue";
import TodoListCard from "./TodoListCard.vue";
import WorkspacePicker from "./WorkspacePicker.vue";

const props = defineProps({
  items: { type: Array, default: () => [] },
  showWorkspacePicker: { type: Boolean, default: false },
  modelProvider: { type: String, default: "" },
  modelName: { type: String, default: "" },
});
const emit = defineEmits([
  "inspect-tool",
  "pick-workspace",
  "resolve-approval",
  "resolve-ask",
  "resolve-plan-review",
  "accept-plan",
]);

function onApproval(item, ev) {
  emit("resolve-approval", { item, action: ev?.action || "allow" });
}
function onAskSubmit(item, ev) {
  emit("resolve-ask", { item, action: "submit", answers: ev?.answers });
}
function onAskDismiss(item) {
  emit("resolve-ask", { item, action: "deny" });
}
function onPlanReview(item, ev) {
  emit("resolve-plan-review", {
    item,
    action: ev?.action || "deny",
    feedback: ev?.feedback || "",
  });
}

const scroller = ref(null);
/** When false, user scrolled up — do not yank them back during streaming. */
const followTail = ref(true);

/** Collapse consecutive regular tool calls; keep subagents / approval / ask as own cards. */
const blocks = computed(() => {
  const out = [];
  for (const item of props.items || []) {
    if (item.kind === "approval" || item.kind === "ask" || item.kind === "todos" || item.kind === "plan_review") {
      out.push({ kind: item.kind, id: item.id, item });
      continue;
    }
    if (item.kind === "tool") {
      const last = out[out.length - 1];
      if (last?.kind === "tools") {
        last.tools.push(item);
      } else {
        out.push({ kind: "tools", id: `tg-${item.id}`, tools: [item] });
      }
      continue;
    }
    if (item.kind === "subagent") {
      out.push({ kind: "subagent", id: item.id, item });
      continue;
    }
    // Hide ghost assistant shells: empty, not live, no activity hint
    if (
      item.kind === "msg" &&
      item.role === "assistant" &&
      !(item.content || "").trim() &&
      !item.activity &&
      !item.streaming &&
      !item.live &&
      !item.planReady
    ) {
      continue;
    }
    out.push({ kind: "msg", id: item.id, item });
  }
  return out;
});

function nearBottom(el, threshold = 80) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  followTail.value = nearBottom(el);
}

async function maybeStickBottom() {
  if (!followTail.value) return;
  await nextTick();
  const el = scroller.value;
  if (el) el.scrollTop = el.scrollHeight;
}

watch(() => props.items.length, () => {
  const last = props.items[props.items.length - 1];
  // New user turn → resume stick-to-bottom so the reply is visible.
  if (last?.kind === "msg" && last.role === "user") {
    followTail.value = true;
  }
  maybeStickBottom();
});

watch(
  () => {
    const last = props.items[props.items.length - 1];
    if (!last) return "";
    if (last.kind === "msg") return last.content;
    if (last.kind === "subagent") return `${last.streamText || ""}|${last.status || ""}`;
    if (last.kind === "tool") return `${last.status || ""}|${last.open ? 1 : 0}`;
    return last.id || "";
  },
  () => {
    maybeStickBottom();
  }
);

defineExpose({
  el: scroller,
  scrollBottom() {
    followTail.value = true;
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  },
});
</script>

<template>
  <div ref="scroller" class="messages" @scroll.passive="onScroll">
    <div v-if="!items.length" class="empty-state">
      <div class="empty-brand">Nexus Lark Mind</div>
      <p>
        先绑定工作目录，再让 Coding Agent 用 glob / grep / 读写 / shell 在项目里干活。
        Agent 会按任务自行决定是否委派 subagent；飞书、插件坞与 Trajectory 仍是工作台能力。
      </p>
      <WorkspacePicker
        v-if="showWorkspacePicker"
        class="empty-ws"
        compact
        @pick="emit('pick-workspace', $event)"
      />
    </div>
    <template v-for="block in blocks" :key="block.id">
      <MessageBubble
        v-if="block.kind === 'msg'"
        :item="block.item"
        :model-provider="modelProvider"
        :model-name="modelName"
        @accept-plan="emit('accept-plan', $event)"
      />
      <ToolApprovalCard
        v-else-if="block.kind === 'approval'"
        :item="block.item"
        @resolve="onApproval(block.item, $event)"
      />
      <AskUserForm
        v-else-if="block.kind === 'ask'"
        :item="block.item"
        @submit="onAskSubmit(block.item, $event)"
        @dismiss="onAskDismiss(block.item)"
      />
      <PlanReviewCard
        v-else-if="block.kind === 'plan_review'"
        :item="block.item"
        :model-provider="modelProvider"
        :model-name="modelName"
        @resolve="onPlanReview(block.item, $event)"
      />
      <TodoListCard
        v-else-if="block.kind === 'todos'"
        :item="block.item"
      />
      <SubagentCard
        v-else-if="block.kind === 'subagent'"
        :item="block.item"
        @inspect="emit('inspect-tool', $event)"
      />
      <ToolCallGroup
        v-else-if="block.tools.length > 1"
        :tools="block.tools"
        @inspect="emit('inspect-tool', $event)"
      />
      <ToolCard
        v-else
        :item="block.tools[0]"
        @inspect="emit('inspect-tool', $event)"
      />
    </template>
  </div>
</template>

<style scoped>
.empty-ws {
  margin-top: 18px;
}
</style>
