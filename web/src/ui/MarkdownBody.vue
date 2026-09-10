<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import {
  decorateMarkdownLinks,
  enhanceCodeBlocks,
  renderDrawioIn,
  renderMarkdownWithMath,
  renderMermaidIn,
  enhanceChatImages,
} from "@/utils/markdown";
import { renderEchartsIn } from "@/utils/echarts";
import { renderMathIn } from "@/utils/math";

const props = defineProps({
  content: { type: String, default: "" },
  streaming: Boolean,
  plain: Boolean,
  modelProvider: { type: String, default: "" },
  modelName: { type: String, default: "" },
});

const emit = defineEmits(["mermaid-fixed"]);

const root = ref(null);
const html = ref("");

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
  if (props.plain) {
    html.value = "";
    return;
  }
  const gen = ++renderGen;
  const nextHtml = await renderMarkdownWithMath(props.content, { streaming: props.streaming });
  if (gen !== renderGen) return;
  html.value = nextHtml;
  await nextTick();
  if (gen !== renderGen || !root.value) return;

  root.value.querySelectorAll(".echarts-block").forEach((block) => {
    if (block._nlmChart) {
      try {
        block._nlmChart.dispose();
      } catch {
        /* ignore */
      }
      block._nlmChart = null;
    }
  });

  decorateMarkdownLinks(root.value);
  enhanceCodeBlocks(root.value);
  enhanceChatImages(root.value);
  // Fallback for any unprotected delimiters
  await renderMathIn(root.value);
  await Promise.all([
    renderMermaidIn(root.value, {
      streaming: false,
      repair: props.streaming ? null : repairMermaid,
      onFixed,
    }),
    renderEchartsIn(root.value, { streaming: props.streaming }),
  ]);
  if (!props.streaming) {
    await renderDrawioIn(root.value, { streaming: false });
  }
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
  root.value?.querySelectorAll?.(".echarts-block").forEach((block) => {
    try {
      block._nlmChart?.dispose?.();
    } catch {
      /* ignore */
    }
  });
});
</script>

<template>
  <div v-if="plain" class="nlm-md plain">{{ content }}</div>
  <div v-else ref="root" class="nlm-md md body" v-html="html" />
</template>
