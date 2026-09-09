<script setup>
import ViewRing from "./ViewRing.vue";

defineProps({
  title: { type: String, default: "新对话" },
  sessionId: { type: String, default: "" },
  centerView: { type: String, default: "chat" },
  workspaceTitle: { type: String, default: "" },
  cwd: { type: String, default: "" },
  workspaceKind: { type: String, default: "local" },
});
const emit = defineEmits([
  "toggle-sidebar",
  "toggle-rail",
  "clear",
  "update:centerView",
  "open-settings",
]);
</script>

<template>
  <header class="topbar">
    <NlmButton variant="ghost" aria-label="切换左侧栏" @click="emit('toggle-sidebar')">☰</NlmButton>
    <div class="topbar-title">
      <h1>{{ title }}</h1>
      <div class="topbar-meta">
        <code v-if="cwd" class="ws-chip" :title="cwd">
          {{ workspaceKind === "ssh" ? "SSH · " : "" }}{{ workspaceTitle || cwd }}
        </code>
        <code class="session-chip">{{ sessionId }}</code>
      </div>
    </div>
    <ViewRing
      class="topbar-views"
      :model-value="centerView"
      @update:model-value="emit('update:centerView', $event)"
    />
    <NlmButton variant="ghost" title="设置" @click="emit('open-settings')">设置</NlmButton>
    <NlmButton variant="ghost" title="清空当前会话" @click="emit('clear')">清空</NlmButton>
    <NlmButton variant="ghost" aria-label="切换右侧栏" @click="emit('toggle-rail')">扩展</NlmButton>
  </header>
</template>

<style scoped>
.topbar-views {
  margin-right: 4px;
}
.topbar-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.ws-chip {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid rgba(43, 184, 160, 0.35);
  color: var(--teal);
  background: rgba(43, 184, 160, 0.08);
}
</style>
