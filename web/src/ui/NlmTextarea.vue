<script setup>
defineProps({
  modelValue: { type: String, default: "" },
  rows: { type: Number, default: 2 },
  placeholder: String,
  disabled: Boolean,
});
const emit = defineEmits(["update:modelValue", "keydown", "submit-enter"]);

function onKeydown(e) {
  emit("keydown", e);
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    emit("submit-enter");
  }
}
</script>

<template>
  <textarea
    class="nlm-textarea"
    :rows="rows"
    :placeholder="placeholder"
    :disabled="disabled"
    :value="modelValue"
    @input="emit('update:modelValue', $event.target.value)"
    @keydown="onKeydown"
  />
</template>

<style scoped>
.nlm-textarea {
  width: 100%;
  resize: vertical;
  min-height: 48px;
  max-height: 140px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ink);
  padding: 10px 12px;
  font: inherit;
  font-size: var(--fs);
  outline: none;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.nlm-textarea::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
.nlm-textarea:focus {
  border-color: rgba(58, 156, 240, 0.5);
  box-shadow: 0 0 0 2px rgba(58, 156, 240, 0.12);
}
</style>
