<script setup>
defineProps({
  conversations: { type: Array, default: () => [] },
  workspaces: { type: Array, default: () => [] },
  activeId: String,
  status: { type: String, default: "ready" },
});
const emit = defineEmits(["new", "select", "delete", "open-settings", "open-workspace"]);
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="logo">Nexus Lark Mind</div>
      <p class="brand-sub">Agent Console</p>
    </div>
    <NlmButton variant="new" block @click="emit('new')">＋ 新对话</NlmButton>

    <div class="sidebar-label">工作目录</div>
    <div class="ws-side-list">
      <button
        v-for="w in workspaces"
        :key="w.id"
        type="button"
        class="ws-side-item"
        :title="w.path"
        @click="emit('open-workspace', w)"
      >
        <span class="ws-title">{{ w.title }}</span>
      </button>
      <div v-if="!workspaces.length" class="ws-empty">在空对话中添加 Workspace</div>
    </div>

    <div class="sidebar-label">历史记录</div>
    <div class="conv-list">
      <div v-if="!conversations.length" style="color: var(--muted); font-size: 11px; padding: 8px">
        暂无历史
      </div>
      <button
        v-for="c in conversations"
        :key="c.id"
        type="button"
        class="conv-item"
        :class="{ active: c.id === activeId }"
        @click="emit('select', c.id)"
      >
        <span class="title">{{ c.title || "新对话" }}</span>
        <span class="del" title="删除" @click.stop="emit('delete', c.id)">×</span>
        <span class="preview">{{ c.cwd ? c.workspaceTitle || c.cwd : c.preview || "" }}</span>
      </button>
    </div>
    <div class="sidebar-foot">
      <button type="button" class="settings-link" @click="emit('open-settings')">⚙ 设置</button>
      <span>{{ status }}</span>
    </div>
  </aside>
</template>

<style scoped>
.ws-side-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 10px 10px;
  max-height: 120px;
  overflow: auto;
  overscroll-behavior: contain;
  flex-shrink: 0;
}
.ws-side-item {
  text-align: left;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ink);
  border-radius: 8px;
  padding: 6px 8px;
  font: inherit;
  cursor: pointer;
}
.ws-side-item:hover {
  border-color: rgba(58, 156, 240, 0.4);
}
.ws-title {
  font-size: 12px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-empty {
  color: var(--muted);
  font-size: 11px;
  padding: 4px 2px;
}
</style>
