<script setup>
defineProps({
  modelValue: { type: [String, Number], default: "" },
  options: { type: Array, default: () => [] }, // [{value, label}]
  disabled: Boolean,
  ariaLabel: String,
  title: String,
});
const emit = defineEmits(["update:modelValue", "change"]);

function onChange(e) {
  emit("update:modelValue", e.target.value);
  emit("change", e.target.value);
}
</script>

<template>
  <select
    class="nlm-select"
    :value="modelValue"
    :disabled="disabled"
    :aria-label="ariaLabel"
    :title="title"
    @change="onChange"
  >
    <option v-for="opt in options" :key="String(opt.value)" :value="opt.value">
      {{ opt.label ?? opt.value }}
    </option>
  </select>
</template>

<style scoped>
.nlm-select {
  appearance: none;
  color-scheme: dark;
  border: 1px solid var(--line);
  background-color: var(--panel-solid, #0f1b2a);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%237f93a8' d='M3 4.5L6 8l3-3.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 6px center;
  color: var(--ink, #d7e2ef);
  border-radius: 6px;
  padding: 5px 22px 5px 8px;
  font: inherit;
  font-size: var(--fs-xs);
  outline: none;
  max-width: 28%;
  min-width: 0;
}
.nlm-select option,
.nlm-select optgroup {
  background-color: #0f1b2a;
  color: #d7e2ef;
}
.nlm-select:focus {
  border-color: rgba(58, 156, 240, 0.5);
}
.nlm-select:disabled {
  opacity: 0.5;
}
.nlm-select--grow {
  flex: 1;
  max-width: none;
}
</style>
