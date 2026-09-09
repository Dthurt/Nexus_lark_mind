import { computed, reactive, ref } from "vue";

/**
 * Right dock: push track, 1–2 panes, tab focus (DSH sidebar-right lite).
 */
export function useRightDock() {
  const state = reactive({
    collapsed: false,
    mode: "push", // push | overlay (narrow)
    split: false,
    ratio: 0.5, // top pane share when split
    panes: [
      {
        id: "main",
        tabs: [
          { id: "plugins", kind: "plugins", title: "插件" },
          { id: "activity", kind: "activity", title: "本回合" },
          { id: "usage", kind: "usage", title: "用量" },
          { id: "inspector", kind: "inspector", title: "检查器" },
        ],
        activeId: "plugins",
      },
      {
        id: "aux",
        tabs: [],
        activeId: null,
      },
    ],
  });

  const highlightActivityId = ref(null);
  const inspectorPayload = ref(null);

  const visiblePanes = computed(() =>
    state.split ? state.panes : [state.panes[0]]
  );

  function toggleCollapsed() {
    state.collapsed = !state.collapsed;
  }

  function expand() {
    state.collapsed = false;
  }

  function openTab(kind, { title, contentId, params, pane = "main", reveal = true } = {}) {
    if (reveal) state.collapsed = false;
    const p = state.panes.find((x) => x.id === pane) || state.panes[0];
    const id = contentId || kind;
    let tab = p.tabs.find((t) => t.id === id && t.kind === kind);
    if (!tab) {
      tab = { id, kind, title: title || kind, params: params || null };
      p.tabs.push(tab);
    } else if (params) {
      tab.params = params;
    }
    p.activeId = tab.id;
    return tab;
  }

  function closeTab(paneId, tabId) {
    const p = state.panes.find((x) => x.id === paneId);
    if (!p) return;
    const i = p.tabs.findIndex((t) => t.id === tabId);
    if (i < 0) return;
    const wasActive = p.activeId === tabId;
    p.tabs.splice(i, 1);
    if (wasActive) p.activeId = p.tabs[0]?.id || null;
    if (paneId === "aux" && !p.tabs.length) {
      state.split = false;
    }
  }

  function focusTab(paneId, tabId) {
    const p = state.panes.find((x) => x.id === paneId);
    if (p) p.activeId = tabId;
  }

  function enableSplit(kind = "inspector") {
    state.split = true;
    openTab(kind, { pane: "aux", title: kind === "inspector" ? "检查器" : kind });
  }

  function disableSplit() {
    state.split = false;
    state.panes[1].tabs = [];
    state.panes[1].activeId = null;
  }

  function setRatio(r) {
    state.ratio = Math.min(0.8, Math.max(0.2, r));
  }

  function openInspector(payload) {
    inspectorPayload.value = payload;
    if (state.split) {
      openTab("inspector", { pane: "aux", title: "检查器", params: payload });
    } else {
      openTab("inspector", { pane: "main", title: "检查器", params: payload });
    }
  }

  function openActivity(activityId) {
    highlightActivityId.value = activityId;
    openTab("activity", { title: "本回合" });
  }

  return {
    state,
    visiblePanes,
    highlightActivityId,
    inspectorPayload,
    toggleCollapsed,
    expand,
    openTab,
    closeTab,
    focusTab,
    enableSplit,
    disableSplit,
    setRatio,
    openInspector,
    openActivity,
  };
}
