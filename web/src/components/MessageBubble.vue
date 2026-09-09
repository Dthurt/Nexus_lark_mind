<script setup>
import { formatUsageLine } from "@/utils/pretty";
import {
  cacheHitRate,
  estimateCostCny,
  formatCacheHit,
  formatCny,
  formatDurationMs,
  formatTokenCount,
  resolveModelRate,
} from "@/utils/pricing";
import { computed, ref } from "vue";
import ActivityHint from "@/components/ActivityHint.vue";

const props = defineProps({
  item: { type: Object, required: true },
  modelProvider: { type: String, default: "" },
  modelName: { type: String, default: "" },
});

const emit = defineEmits(["accept-plan"]);

const openUsage = ref(false);

/** Caret only while tokens are streaming — not during tool/subagent/wait phases. */
const showCaret = computed(() => {
  if (!props.item.streaming) return false;
  const phase = props.item.activity?.phase;
  return !phase || phase === "stream";
});

const usageSummary = computed(() => {
  if (!props.item.usage) return "";
  return formatUsageLine(props.item.usage, {
    modelName: props.modelName,
    providerId: props.modelProvider,
  });
});

const usageDetail = computed(() => {
  const u = props.item.usage;
  if (!u) return null;
  const cost = estimateCostCny(u, {
    modelName: props.modelName,
    providerId: props.modelProvider,
  });
  const cache = formatCacheHit(u);
  const rate = resolveModelRate(props.modelName, props.modelProvider);
  return {
    prompt: Number(u.prompt_tokens || 0),
    completion: Number(u.completion_tokens || 0),
    total: Number(u.total_tokens || (u.prompt_tokens || 0) + (u.completion_tokens || 0)),
    duration: formatDurationMs(u.duration_ms) || "—",
    cached: Number(u.cached_tokens || 0),
    cacheText: cache.cached > 0 ? `${formatTokenCount(cache.cached)} · ${cacheHitRate(u).toFixed(1)}%` : "0",
    costText: formatCny(cost.yuan),
    rateText: `输入 ¥${rate.input}/M · 输出 ¥${rate.output}/M · 缓存 ¥${rate.cache}/M`,
    estimated: !!u.estimated,
  };
});

function onMermaidFixed({ from, to }) {
  if (!from || !to || from === to) return;
  const content = props.item.content || "";
  if (!content.includes(from)) return;
  props.item.content = content.replace(from, to);
}
</script>

<template>
  <div class="msg" :class="[item.role, { live: item.live || item.streaming }]">
    <MarkdownBody
      v-if="item.content"
      class="body"
      :content="item.content"
      :streaming="showCaret"
      :plain="!item.rich"
      :model-provider="modelProvider"
      :model-name="modelName"
      @mermaid-fixed="onMermaidFixed"
    />
    <ActivityHint
      v-if="item.activity && (item.streaming || item.live)"
      embedded
      :active="true"
      :phase="item.activity.phase"
      :label="item.activity.label"
      :detail="item.activity.detail"
      :started-at="item.activity.startedAt"
    />
    <button
      v-if="item.planReady && item.role === 'assistant' && !item.streaming && !item.live"
      type="button"
      class="accept-plan-btn"
      @click="emit('accept-plan', item)"
    >
      接受计划并执行
    </button>
    <button
      v-if="item.usage"
      type="button"
      class="token-badge clickable"
      :title="'点击查看明细'"
      @click="openUsage = !openUsage"
    >
      {{ usageSummary }}
    </button>
    <div v-if="openUsage && usageDetail" class="turn-usage">
      <div class="usage-row"><span>输入</span><strong>{{ usageDetail.prompt }}</strong></div>
      <div class="usage-row"><span>输出</span><strong>{{ usageDetail.completion }}</strong></div>
      <div class="usage-row"><span>合计</span><strong>{{ usageDetail.total }}</strong></div>
      <div class="usage-row"><span>耗时</span><strong>{{ usageDetail.duration }}</strong></div>
      <div class="usage-row"><span>缓存命中</span><strong>{{ usageDetail.cacheText }}</strong></div>
      <div class="usage-row"><span>估算费用</span><strong>{{ usageDetail.costText }}</strong></div>
      <p class="rail-hint">{{ usageDetail.rateText }}</p>
      <p v-if="usageDetail.estimated" class="rail-hint">含估算 token（接口未返回 usage）</p>
    </div>
  </div>
</template>

<style scoped>
/* Long user messages stay in a capped viewport; wheel to scroll (scrollbar hidden globally). */
.msg.user :deep(.body) {
  max-height: 10.5em;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.msg.user :deep(.body)::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}
.token-badge.clickable {
  cursor: pointer;
  border: 0;
  background: transparent;
  padding: 0;
  max-width: 100%;
  text-align: left;
  white-space: normal;
  line-height: 1.35;
}
.accept-plan-btn {
  margin-top: 8px;
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid rgba(58, 156, 240, 0.45);
  background: rgba(58, 156, 240, 0.12);
  color: var(--accent);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}
.accept-plan-btn:hover {
  filter: brightness(1.08);
}
.token-badge.clickable:hover {
  color: var(--ink);
}
.turn-usage {
  margin-top: 6px;
  padding: 7px 8px;
  border-radius: 7px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  max-width: 280px;
}
.usage-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: var(--fs-xs);
  padding: 2px 0;
}
.usage-row strong {
  font-family: var(--mono);
  font-weight: 500;
}
.rail-hint {
  margin: 4px 0 0;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.35;
}
</style>
