<script setup>
import { computed, reactive, watch } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
});
const emit = defineEmits(["submit", "dismiss"]);

const pending = computed(() => props.item.status === "pending");
const questions = computed(() => props.item.questions || []);

const state = reactive({});
const customs = reactive({});

function ensureState() {
  for (const q of questions.value) {
    if (state[q.id] === undefined) {
      state[q.id] = q.allow_multiple ? [] : "";
    }
    if (customs[q.id] === undefined) customs[q.id] = "";
  }
}
watch(questions, ensureState, { immediate: true, deep: true });

function toggleMulti(qid, oid) {
  const cur = Array.isArray(state[qid]) ? [...state[qid]] : [];
  const i = cur.indexOf(oid);
  if (i >= 0) cur.splice(i, 1);
  else cur.push(oid);
  state[qid] = cur;
}

function onSubmit() {
  const answers = {};
  for (const q of questions.value) {
    const selected = state[q.id];
    const custom = (customs[q.id] || "").trim();
    answers[q.id] = {
      selected: q.allow_multiple ? selected || [] : selected || null,
      custom: q.allow_custom !== false ? custom || null : null,
    };
  }
  emit("submit", { answers });
}
</script>

<template>
  <div class="ask-card" :class="item.status || 'pending'">
    <div class="ask-head">
      <span class="ask-badge">询问</span>
      <span class="ask-title">{{ item.title || "需要你的确认" }}</span>
      <span v-if="!pending" class="ask-state">{{
        item.status === "answered" ? "已回答" : item.status
      }}</span>
    </div>

    <div v-for="q in questions" :key="q.id" class="ask-q">
      <div class="ask-prompt">{{ q.prompt }}</div>
      <div v-if="(q.options || []).length" class="ask-options">
        <label v-for="opt in q.options" :key="opt.id" class="ask-opt">
          <input
            v-if="q.allow_multiple"
            type="checkbox"
            :disabled="!pending"
            :checked="(state[q.id] || []).includes(opt.id)"
            @change="toggleMulti(q.id, opt.id)"
          />
          <input
            v-else
            v-model="state[q.id]"
            type="radio"
            :disabled="!pending"
            :value="opt.id"
            :name="`ask-${item.id}-${q.id}`"
          />
          <span>{{ opt.label }}</span>
        </label>
      </div>
      <input
        v-if="q.allow_custom !== false"
        v-model="customs[q.id]"
        class="ask-custom"
        type="text"
        :disabled="!pending"
        placeholder="自定义答案（可选）"
      />
    </div>

    <div v-if="pending" class="ask-actions">
      <button type="button" class="btn primary" @click="onSubmit">提交</button>
      <button type="button" class="btn" @click="emit('dismiss')">跳过</button>
    </div>
    <pre v-else-if="item.answers" class="ask-result">{{ JSON.stringify(item.answers, null, 2) }}</pre>
  </div>
</template>

<style scoped>
.ask-card {
  border: 1px solid rgba(58, 156, 240, 0.35);
  border-radius: 10px;
  background: rgba(58, 156, 240, 0.08);
  padding: 10px 12px;
  max-width: min(100%, 720px);
  display: grid;
  gap: 10px;
}
.ask-card.answered {
  opacity: 0.85;
}
.ask-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-sm);
}
.ask-badge {
  font-weight: 700;
  color: var(--accent);
  font-size: var(--fs-xs);
}
.ask-title {
  color: var(--ink);
  font-weight: 600;
}
.ask-state {
  margin-left: auto;
  color: var(--muted);
  font-size: var(--fs-xs);
}
.ask-q {
  display: grid;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.ask-prompt {
  color: var(--ink);
  font-size: var(--fs-sm);
}
.ask-options {
  display: grid;
  gap: 4px;
}
.ask-opt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--fs-xs);
  color: var(--muted);
  cursor: pointer;
}
.ask-opt span {
  color: var(--ink);
}
.ask-custom {
  height: 30px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: rgba(0, 0, 0, 0.28);
  color: var(--ink);
  padding: 0 8px;
  font: inherit;
  font-size: var(--fs-xs);
}
.ask-actions {
  display: flex;
  gap: 6px;
}
.btn {
  height: 28px;
  padding: 0 12px;
  border-radius: 6px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ink);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}
.btn.primary {
  border-color: rgba(58, 156, 240, 0.55);
  color: var(--accent);
}
.ask-result {
  margin: 0;
  font-family: var(--mono);
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: pre-wrap;
}
</style>
