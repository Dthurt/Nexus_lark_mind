<script setup>
defineProps({
  modelValue: { type: String, default: "chat" },
  views: {
    type: Array,
    default: () => [
      { id: "chat", label: "Chat" },
      { id: "trajectory", label: "Trajectory" },
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
      @click="emit('update:modelValue', v.id)"
    >
      {{ v.label }}
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
  background: rgba(255, 255, 255, 0.03);
}
.view-ring-btn {
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
}
.view-ring-btn.active {
  color: var(--ink);
  background: rgba(58, 156, 240, 0.16);
}
</style>
