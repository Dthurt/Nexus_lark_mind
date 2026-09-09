<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import {
  decorateMarkdownLinks,
  enhanceCodeBlocks,
  renderDrawioIn,
  renderMarkdown,
  renderMermaidIn,
} from "@/utils/markdown";

const props = defineProps({
  content: { type: String, default: "" },
  streaming: Boolean,
  plain: Boolean,
  /** Optional model ids for mermaid repair API */
  modelProvider: { type: String, default: "" },
  modelName: { type: String, default: "" },
});

const emit = defineEmits(["mermaid-fixed"]);

const root = ref(null);
const html = computed(() => {
  if (props.plain) return "";
  return renderMarkdown(props.content, { streaming: props.streaming });
});

let renderGen = 0;
let debounceTimer = null;

async function repairMermaid(source, error) {
  const resp = await fetch("/api/mermaid/repair", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source,
      error,
      model_provider: props.modelProvider || undefined,
      model_name: props.modelName || undefined,
    }),
  });
  let json = null;
  try {
    json = await resp.json();
  } catch {
    throw new Error(`mermaid repair HTTP ${resp.status}`);
  }
  if (!resp.ok || !json?.ok) {
    throw new Error(json?.error?.message || `mermaid repair failed (${resp.status})`);
  }
  return json.data?.source || "";
}

function onFixed({ from, to }) {
  emit("mermaid-fixed", { from, to });
}

async function paint() {
  if (props.plain) return;
  const gen = ++renderGen;
  await nextTick();
  if (gen !== renderGen || !root.value) return;
  decorateMarkdownLinks(root.value);
  enhanceCodeBlocks(root.value);
  // Skip diagram engines while streaming to avoid false errors on incomplete fences.
  if (props.streaming) return;
  await Promise.all([
    renderMermaidIn(root.value, {
      streaming: false,
      repair: repairMermaid,
      onFixed,
    }),
    renderDrawioIn(root.value, { streaming: false }),
  ]);
}

watch(
  () => [props.content, props.streaming, props.plain],
  () => {
    if (debounceTimer) clearTimeout(debounceTimer);
    const wait = props.streaming ? 280 : 0;
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      paint();
    }, wait);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
});
</script>

<template>
  <div v-if="plain" class="nlm-md plain">{{ content }}</div>
  <div v-else ref="root" class="nlm-md md body" v-html="html" />
</template>
