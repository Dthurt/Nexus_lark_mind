<script setup>
defineProps({
  variant: { type: String, default: "primary" }, // primary | ghost | new
  type: { type: String, default: "button" },
  disabled: Boolean,
  block: Boolean,
  title: String,
});
</script>

<template>
  <button
    :type="type"
    class="nlm-btn"
    :class="[`nlm-btn--${variant}`, { 'nlm-btn--block': block }]"
    :disabled="disabled"
    :title="title"
  >
    <slot />
  </button>
</template>

<style scoped>
.nlm-btn {
  font: inherit;
  cursor: pointer;
  border-radius: 7px;
  transition: filter 120ms ease, background 140ms ease, border-color 140ms ease, color 120ms ease;
}
.nlm-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.nlm-btn--block {
  width: 100%;
}
.nlm-btn--primary {
  border: 0;
  padding: 5px 12px;
  background: linear-gradient(135deg, var(--accent), #2563eb);
  color: #fff;
  font-size: var(--fs-sm);
  font-weight: 600;
}
.nlm-btn--primary:hover:not(:disabled) {
  filter: brightness(1.06);
}
.nlm-btn--ghost {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  padding: 5px 9px;
  font-size: var(--fs-sm);
}
.nlm-btn--ghost:hover:not(:disabled) {
  color: var(--ink);
  border-color: rgba(255, 255, 255, 0.16);
}
.nlm-btn--new {
  border: 1px solid rgba(58, 156, 240, 0.35);
  background: var(--accent-dim);
  color: var(--ink);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: var(--fs-sm);
  font-weight: 500;
}
.nlm-btn--new:hover:not(:disabled) {
  background: rgba(58, 156, 240, 0.22);
  border-color: rgba(58, 156, 240, 0.55);
}
</style>
