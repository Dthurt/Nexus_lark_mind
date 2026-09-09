<script setup>
defineProps({
  active: Boolean,
});
</script>

<template>
  <span class="nlm-chip" :class="{ on: active }"><slot /></span>
</template>

<style scoped>
.nlm-chip {
  font-family: var(--mono);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--muted);
}
.nlm-chip.on {
  color: var(--teal);
  border-color: rgba(43, 184, 160, 0.35);
}
</style>
