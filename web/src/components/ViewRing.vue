<script setup>
defineProps({
  modelValue: { type: String, default: "chat" },
  views: {
    type: Array,
    default: () => [
      { id: "chat", label: "对话", icon: "chat" },
      { id: "trajectory", label: "轨迹", icon: "trajectory" },
    ],
  },
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <div class="view-ring" role="tablist" aria-label="会话视图">
    <button
      v-for="v in views"
      :key="v.id"
      type="button"
      role="tab"
      class="view-ring-btn"
      :class="{ active: modelValue === v.id }"
      :aria-selected="modelValue === v.id"
      :title="v.label"
      :aria-label="v.label"
      @click="emit('update:modelValue', v.id)"
    >
      <svg v-if="v.icon === 'trajectory' || v.id === 'trajectory'" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M4 18V6M4 18h16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
        />
        <path
          d="M7 14l3.2-3.5 2.6 2.2L17 8"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle cx="17" cy="8" r="1.4" fill="currentColor" />
      </svg>
      <svg v-else viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-3.5 3v-3H7.5A2.5 2.5 0 0 1 5 13.5v-7z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linejoin="round"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.view-ring {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-soft);
}
.view-ring-btn {
  width: 28px;
  height: 28px;
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 0;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.view-ring-btn svg {
  width: 15px;
  height: 15px;
  display: block;
}
.view-ring-btn:hover {
  color: var(--ink);
}
.view-ring-btn.active {
  color: var(--accent);
  background: var(--accent-dim);
}
</style>
