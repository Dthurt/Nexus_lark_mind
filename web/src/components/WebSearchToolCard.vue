<script setup>
import { computed } from "vue";
import { pretty } from "@/utils/pretty";
import GenericToolCard from "./GenericToolCard.vue";

const props = defineProps({
  item: { type: Object, required: true },
  nested: { type: Boolean, default: false },
});
defineEmits(["inspect"]);

const searchPayload = computed(() => {
  const raw = props.item.result;
  if (!raw) return null;
  let data = raw;
  if (typeof raw === "string") {
    try {
      data = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (data && typeof data === "object" && data.value && !data.results) {
    data = data.value;
  }
  if (!data || typeof data !== "object" || !Array.isArray(data.results)) return null;
  return data;
});

const results = computed(() => searchPayload.value?.results || []);
</script>

<template>
  <GenericToolCard
    v-if="!searchPayload"
    :item="item"
    :nested="nested"
    @inspect="$emit('inspect', $event)"
  />
  <details
    v-else
    class="tool-card ok"
    :class="{ nested }"
    :open="!!item.open"
    @toggle="item.open = $event.target.open"
  >
    <summary>
      <span class="tool-chevron" aria-hidden="true" />
      <span class="tool-badge">SEARCH</span>
      <span class="tool-name">{{ item.name }}</span>
      <span class="tool-meta">
        {{ searchPayload.provider || "web" }} · {{ results.length }} 条
      </span>
    </summary>
    <div class="tool-body">
      <div v-if="item.arguments" class="tool-block">
        <label>Query</label>
        <pre>{{ pretty(item.arguments.query || item.arguments) }}</pre>
      </div>
      <div class="search-results">
        <a
          v-for="(r, i) in results"
          :key="i"
          class="search-hit"
          :href="r.url || '#'"
          target="_blank"
          rel="noopener noreferrer"
        >
          <div class="stitle">{{ r.title || r.url || "result" }}</div>
          <div v-if="r.url" class="surl">{{ r.url }}</div>
          <div v-if="r.snippet" class="ssnip">{{ r.snippet }}</div>
        </a>
      </div>
      <div class="tool-actions">
        <button
          v-if="item.activityId"
          type="button"
          class="tool-inspect"
          @click.stop.prevent="$emit('inspect', item.activityId)"
        >
          查看活动
        </button>
      </div>
    </div>
  </details>
</template>

<style scoped>
.search-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.search-hit {
  display: block;
  text-decoration: none;
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 7px 8px;
  background: rgba(0, 0, 0, 0.18);
}
.search-hit:hover {
  border-color: rgba(58, 156, 240, 0.4);
}
.stitle {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: #7eb8f5;
}
.surl {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--teal);
  margin-top: 2px;
  word-break: break-all;
}
.ssnip {
  margin-top: 4px;
  font-size: var(--fs-xs);
  color: var(--muted);
  line-height: 1.4;
}
.tool-actions {
  display: flex;
  justify-content: flex-end;
}
.tool-inspect {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: var(--fs-xs);
  border-radius: 6px;
  padding: 3px 8px;
  cursor: pointer;
}
</style>
