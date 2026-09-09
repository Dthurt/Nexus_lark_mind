<script setup>
import { computed } from "vue";
import { SlotNames, uiSlots } from "@nlm/ui";
import GenericToolCard from "./GenericToolCard.vue";

const props = defineProps({
  item: { type: Object, required: true },
  nested: { type: Boolean, default: false },
});
const emit = defineEmits(["inspect"]);

const resolved = computed(() => {
  const keys = [props.item.openaiName, props.item.name].filter(Boolean);
  for (const key of keys) {
    const hit = uiSlots.resolveKeyed(SlotNames.TOOL_CALL_VIEW, key);
    if (hit?.component) return hit.component;
  }
  return GenericToolCard;
});
</script>

<template>
  <component :is="resolved" :item="item" :nested="nested" @inspect="emit('inspect', $event)" />
</template>
