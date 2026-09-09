<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  active: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  phase: { type: String, default: "" }, // model | tool | subagent | stream | retry | send | stop
  label: { type: String, default: "" },
  detail: { type: String, default: "" },
  startedAt: { type: Number, default: 0 },
});

const now = ref(Date.now());
let timer = null;

watch(
  () => props.active,
  (on) => {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    if (on) {
      now.value = Date.now();
      timer = setInterval(() => {
        now.value = Date.now();
      }, 250);
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});

const elapsedSec = computed(() => {
  if (!props.active || !props.startedAt) return 0;
  return Math.max(0, (now.value - props.startedAt) / 1000);
});

const elapsedText = computed(() => {
  const s = elapsedSec.value;
  if (s < 1) return "";
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return `${m}:${String(rem).padStart(2, "0")}`;
});

const phaseIcon = computed(() => {
  switch (props.phase) {
    case "tool":
      return "tool";
    case "subagent":
      return "sub";
    case "stream":
      return "stream";
    case "retry":
      return "retry";
    case "stop":
      return "stop";
    case "send":
      return "send";
    default:
      return "model";
  }
});
</script>

<template>
  <div
    v-if="active && label"
    class="activity-hint"
    :class="{ embedded }"
    role="status"
    aria-live="polite"
  >
    <span class="ah-spin" :class="phaseIcon" aria-hidden="true" />
    <span class="ah-text">
      <span class="ah-label">{{ label }}</span>
      <span v-if="detail" class="ah-detail">{{ detail }}</span>
    </span>
    <span v-if="elapsedText" class="ah-elapsed" :title="'已进行 ' + elapsedText">{{ elapsedText }}</span>
  </div>
</template>

<style scoped>
.activity-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px 2px;
  min-height: 28px;
  color: var(--muted);
  font-size: var(--fs-xs);
  animation: fade 160ms ease both;
}

.activity-hint.embedded {
  padding: 2px 0 0;
  min-height: 22px;
  margin-top: 2px;
}

.ah-spin {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 1.5px solid rgba(127, 147, 168, 0.25);
  border-top-color: var(--accent);
  animation: ah-rotate 0.75s linear infinite;
}

.ah-spin.tool {
  border-top-color: var(--tool);
}

.ah-spin.sub {
  border-top-color: #a78bfa;
}

.ah-spin.stream {
  border-top-color: var(--teal);
}

.ah-spin.retry {
  border-top-color: #f0a060;
}

.ah-spin.stop {
  border-top-color: var(--danger);
  animation-duration: 1.1s;
}

.ah-text {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.ah-label {
  color: var(--ink);
  opacity: 0.85;
  white-space: nowrap;
}

.ah-detail {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.ah-elapsed {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  opacity: 0.85;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

@keyframes ah-rotate {
  to {
    transform: rotate(360deg);
  }
}
</style>
