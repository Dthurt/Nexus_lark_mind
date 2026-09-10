<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  modelProvider: { type: String, default: "" },
  modelName: { type: String, default: "" },
});
const emit = defineEmits(["resolve"]);

const pending = computed(() => props.item.status === "pending");
const feedback = ref("");

function approve() {
  emit("resolve", { action: "approve" });
}
function keepPlanning() {
  emit("resolve", {
    action: "keep_planning",
    feedback: (feedback.value || "").trim(),
  });
}
function dismiss() {
  emit("resolve", { action: "deny" });
}
</script>

<template>
  <div class="plan-review-card" :class="item.status || 'pending'">
    <div class="plan-review-head">
      <span class="plan-badge">计划审阅</span>
      <span class="plan-title">{{ item.title || "Approve this plan and leave plan mode?" }}</span>
      <span v-if="!pending" class="plan-state">{{
        item.status === "approved"
          ? "已批准"
          : item.status === "keep_planning"
            ? "继续规划"
            : item.status
      }}</span>
    </div>

    <div class="plan-body">
      <MarkdownBody
        v-if="item.plan"
        :content="item.plan"
        :streaming="false"
        :plain="false"
        :model-provider="modelProvider"
        :model-name="modelName"
      />
    </div>

    <div v-if="pending" class="plan-actions">
      <textarea
        v-model="feedback"
        class="plan-feedback"
        rows="2"
        placeholder="可选：留下修改意见（点「继续规划」时带回给模型）"
      />
      <div class="plan-btns">
        <button type="button" class="btn-approve" @click="approve">批准并执行</button>
        <button type="button" class="btn-keep" @click="keepPlanning">继续规划</button>
        <button type="button" class="btn-dismiss" @click="dismiss">稍后自己说</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-review-card {
  margin: 10px 0 12px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--teal, #2bb8a0) 35%, var(--line));
  border-radius: 12px;
  background: color-mix(in srgb, var(--teal, #2bb8a0) 6%, var(--panel, #14202c));
  max-width: 48rem;
}
.plan-review-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.plan-badge {
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--teal, #2bb8a0);
  border: 1px solid color-mix(in srgb, var(--teal, #2bb8a0) 40%, transparent);
  border-radius: 999px;
  padding: 2px 8px;
}
.plan-title {
  font-size: 13px;
  color: var(--ink);
  font-weight: 560;
}
.plan-state {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
}
.plan-body {
  max-height: 320px;
  overflow: auto;
  padding: 6px 2px 10px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  margin-bottom: 10px;
}
.plan-feedback {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 52px;
  margin-bottom: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--surface-soft, transparent);
  color: var(--ink);
  font: inherit;
  font-size: 13px;
}
.plan-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.plan-btns button {
  border-radius: 8px;
  border: 1px solid var(--line);
  padding: 7px 12px;
  font-size: 13px;
  cursor: pointer;
  background: transparent;
  color: var(--ink);
}
.btn-approve {
  background: color-mix(in srgb, var(--teal, #2bb8a0) 22%, transparent) !important;
  border-color: color-mix(in srgb, var(--teal, #2bb8a0) 45%, transparent) !important;
  color: var(--ink) !important;
  font-weight: 600;
}
.btn-keep:hover,
.btn-dismiss:hover,
.btn-approve:hover {
  border-color: color-mix(in srgb, var(--ink) 28%, transparent);
}
.plan-review-card.approved {
  opacity: 0.92;
}
.plan-review-card.keep_planning,
.plan-review-card.dismissed {
  opacity: 0.85;
}
</style>
