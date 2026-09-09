<script setup>
defineProps({
  modelValue: { type: String, required: true },
  tabs: { type: Array, required: true }, // [{id, label}]
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <div class="nlm-tabs" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      class="nlm-tab"
      role="tab"
      :class="{ active: modelValue === tab.id }"
      :aria-selected="modelValue === tab.id"
      @click="emit('update:modelValue', tab.id)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>

<style scoped>
.nlm-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 8px 0;
  border-bottom: 1px solid var(--line);
}
.nlm-tab {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  padding: 7px 6px;
  border-radius: 7px 7px 0 0;
  cursor: pointer;
}
.nlm-tab:hover {
  color: var(--ink);
}
.nlm-tab.active {
  color: var(--ink);
  background: rgba(58, 156, 240, 0.12);
  box-shadow: inset 0 -2px 0 var(--accent);
}
</style>
