import { useCallback, useMemo, useState } from "react";

export type DockTab = {
  id: string;
  kind: string;
  title: string;
  params?: any;
};

export type DockPane = {
  id: string;
  tabs: DockTab[];
  activeId: string | null;
};

export type RightDockState = {
  collapsed: boolean;
  mode: "push" | "overlay" | string;
  split: boolean;
  ratio: number;
  panes: DockPane[];
};

const initialState = (): RightDockState => ({
  collapsed: false,
  mode: "push",
  split: false,
  ratio: 0.5,
  panes: [
    {
      id: "main",
      tabs: [
        { id: "plugins", kind: "plugins", title: "插件" },
        { id: "delivery", kind: "delivery", title: "Delivery" },
        { id: "teams", kind: "teams", title: "Teams" },
        { id: "jobs", kind: "jobs", title: "Jobs" },
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

/**
 * Right dock: push track, 1–2 panes, tab focus (DSH sidebar-right lite).
 */
export function useRightDock() {
  const [state, setState] = useState<RightDockState>(initialState);
  const [highlightActivityId, setHighlightActivityId] = useState<string | null>(null);
  const [inspectorPayload, setInspectorPayload] = useState<any>(null);

  const visiblePanes = useMemo(
    () => (state.split ? state.panes : [state.panes[0]]),
    [state.panes, state.split],
  );

  const toggleCollapsed = useCallback(() => {
    setState((s) => ({ ...s, collapsed: !s.collapsed }));
  }, []);

  const expand = useCallback(() => {
    setState((s) => ({ ...s, collapsed: false }));
  }, []);

  const openTab = useCallback(
    (
      kind: string,
      {
        title,
        contentId,
        params,
        pane = "main",
        reveal = true,
      }: {
        title?: string;
        contentId?: string;
        params?: any;
        pane?: string;
        reveal?: boolean;
      } = {},
    ) => {
      let created: DockTab | null = null;
      setState((s) => {
        const next = {
          ...s,
          collapsed: reveal ? false : s.collapsed,
          panes: s.panes.map((p) => ({ ...p, tabs: [...p.tabs] })),
        };
        const p = next.panes.find((x) => x.id === pane) || next.panes[0];
        const id = contentId || kind;
        let tab = p.tabs.find((t) => t.id === id && t.kind === kind);
        if (!tab) {
          tab = { id, kind, title: title || kind, params: params || null };
          p.tabs.push(tab);
        } else if (params) {
          tab = { ...tab, params };
          const ti = p.tabs.findIndex((t) => t.id === id && t.kind === kind);
          if (ti >= 0) p.tabs[ti] = tab;
        }
        p.activeId = tab.id;
        created = tab;
        return next;
      });
      return (created || { id: kind, kind, title: title || kind }) as DockTab;
    },
    [],
  );

  const closeTab = useCallback((paneId: string, tabId: string) => {
    setState((s) => {
      const panes = s.panes.map((p) => {
        if (p.id !== paneId) return p;
        const tabs = p.tabs.filter((t) => t.id !== tabId);
        const wasActive = p.activeId === tabId;
        return {
          ...p,
          tabs,
          activeId: wasActive ? tabs[0]?.id || null : p.activeId,
        };
      });
      const aux = panes.find((x) => x.id === "aux");
      const split = paneId === "aux" && aux && !aux.tabs.length ? false : s.split;
      return { ...s, panes, split };
    });
  }, []);

  const focusTab = useCallback((paneId: string, tabId: string) => {
    setState((s) => ({
      ...s,
      panes: s.panes.map((p) => (p.id === paneId ? { ...p, activeId: tabId } : p)),
    }));
  }, []);

  const enableSplit = useCallback(
    (kind = "inspector") => {
      setState((s) => ({ ...s, split: true }));
      openTab(kind, { pane: "aux", title: kind === "inspector" ? "检查器" : kind });
    },
    [openTab],
  );

  const disableSplit = useCallback(() => {
    setState((s) => ({
      ...s,
      split: false,
      panes: s.panes.map((p) =>
        p.id === "aux" ? { ...p, tabs: [], activeId: null } : p,
      ),
    }));
  }, []);

  const setRatio = useCallback((r: number) => {
    setState((s) => ({ ...s, ratio: Math.min(0.8, Math.max(0.2, r)) }));
  }, []);

  const openInspector = useCallback(
    (payload: any) => {
      setInspectorPayload(payload);
      setState((s) => {
        const pane = s.split ? "aux" : "main";
        const next = {
          ...s,
          collapsed: false,
          panes: s.panes.map((p) => ({ ...p, tabs: p.tabs.map((t) => ({ ...t })) })),
        };
        const p = next.panes.find((x) => x.id === pane) || next.panes[0];
        let tab = p.tabs.find((t) => t.id === "inspector" && t.kind === "inspector");
        if (!tab) {
          tab = { id: "inspector", kind: "inspector", title: "检查器", params: payload };
          p.tabs.push(tab);
        } else {
          tab.params = payload;
        }
        p.activeId = tab.id;
        return next;
      });
    },
    [],
  );

  const openActivity = useCallback(
    (activityId: string) => {
      setHighlightActivityId(activityId);
      openTab("activity", { title: "本回合" });
    },
    [openTab],
  );

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
