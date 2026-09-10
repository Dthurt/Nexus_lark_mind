<script setup>
import { computed, ref } from "vue";
import ViewRing from "./ViewRing.vue";
import {
  applyTheme,
  cycleTheme,
  loadStoredTheme,
  themeLabel,
} from "@/composables/useTheme";

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
]);

const theme = ref(applyTheme(loadStoredTheme()));
const themeTitle = computed(() => `主题：${themeLabel(theme.value)}（点击切换）`);

function onCycleTheme() {
  theme.value = cycleTheme(theme.value);
}
</script>

<template>
  <header class="topbar">
    <button
      type="button"
      class="tb-icon"
      title="切换左侧栏"
      aria-label="切换左侧栏"
      @click="emit('toggle-sidebar')"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.75" />
        <path d="M9 4v16" fill="none" stroke="currentColor" stroke-width="1.75" />
      </svg>
    </button>

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

    <button
      type="button"
      class="tb-icon"
      :title="themeTitle"
      :aria-label="themeTitle"
      @click="onCycleTheme"
    >
      <!-- day: sun -->
      <svg v-if="theme === 'day'" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.75" />
        <path
          d="M12 2v2.2M12 19.8V22M4.2 12H2M22 12h-2.2M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
        />
      </svg>
      <!-- gray: half moon / contrast -->
      <svg v-else-if="theme === 'gray'" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.75" />
        <path d="M12 4a8 8 0 0 0 0 16V4z" fill="currentColor" opacity="0.85" />
      </svg>
      <!-- night: moon -->
      <svg v-else viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M18.5 14.2A7.2 7.2 0 0 1 9.8 5.5 7.5 7.5 0 1 0 18.5 14.2z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <button
      type="button"
      class="tb-icon"
      title="清空当前会话"
      aria-label="清空当前会话"
      @click="emit('clear')"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M5 7h14M9 7V5.8A1.8 1.8 0 0 1 10.8 4h2.4A1.8 1.8 0 0 1 15 5.8V7M8 7l.8 12.2A1.8 1.8 0 0 0 10.6 21h2.8a1.8 1.8 0 0 0 1.8-1.8L16 7"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <button
      type="button"
      class="tb-icon"
      title="切换右侧栏"
      aria-label="切换右侧栏"
      @click="emit('toggle-rail')"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.75" />
        <path d="M15 4v16" fill="none" stroke="currentColor" stroke-width="1.75" />
      </svg>
    </button>
  </header>
</template>

<style scoped>
.topbar-views {
  margin-right: 2px;
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
.tb-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
  transition: color 120ms ease, border-color 120ms ease, background 120ms ease;
}
.tb-icon svg {
  width: 16px;
  height: 16px;
  display: block;
}
.tb-icon:hover {
  color: var(--ink);
  border-color: color-mix(in srgb, var(--ink) 22%, transparent);
  background: var(--surface-soft);
}
</style>
