<script setup>
defineProps({
  modelValue: Boolean,
  disabled: Boolean,
  title: String,
});
const emit = defineEmits(["update:modelValue", "change"]);

function onChange(e) {
  const checked = e.target.checked;
  emit("update:modelValue", checked);
  emit("change", checked);
}
</script>

<template>
  <label class="nlm-switch" :title="title">
    <input
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      @change="onChange"
    />
    <span />
  </label>
</template>

<style scoped>
.nlm-switch {
  position: relative;
  width: 34px;
  height: 18px;
  flex-shrink: 0;
  display: inline-block;
}
.nlm-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.nlm-switch span {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  cursor: pointer;
  transition: background 120ms ease;
}
.nlm-switch span::after {
  content: "";
  position: absolute;
  width: 14px;
  height: 14px;
  left: 2px;
  top: 2px;
  background: #fff;
  border-radius: 50%;
  transition: transform 120ms ease;
}
.nlm-switch input:checked + span {
  background: rgba(58, 156, 240, 0.65);
}
.nlm-switch input:checked + span::after {
  transform: translateX(16px);
}
.nlm-switch input:disabled + span {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
