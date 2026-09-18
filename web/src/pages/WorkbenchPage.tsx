import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApprovalDock } from "@/components/chat/ApprovalDock";
import { ChatMessages } from "@/components/chat/ChatMessages";
import { CommandPalette } from "@/components/command/CommandPalette";
import { Composer } from "@/components/composer/Composer";
import { KnowledgeView } from "@/components/knowledge/KnowledgeView";
import { RightDock } from "@/components/layout/RightDock";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import type { CenterViewId } from "@/components/layout/ViewRing";
import {
  TrajectoryView,
  type TrajectoryRow,
} from "@/components/trajectory/TrajectoryView";
import { gitInfo, getPluginCalls, deleteSession as apiDeleteSession, patchInteraction, addSessionBookmark, getSession } from "@/api/endpoints";
import { useChatActions } from "@/hooks/useChatActions";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatTimeline } from "@/hooks/useChatTimeline";
import { useCommandPalette } from "@/hooks/useCommandPalette";
import { useKnowledgeCatalog } from "@/hooks/useKnowledgeCatalog";
import { usePlugins } from "@/hooks/usePlugins";
import { useProviders } from "@/hooks/useProviders";
import { useRightDock } from "@/hooks/useRightDock";
import { useDeliveryArtifact } from "@/hooks/useDeliveryArtifact";
import { useSessions } from "@/hooks/useSessions";
import { useTrajectory } from "@/hooks/useTrajectory";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { CanvasPane } from "@/components/canvas/CanvasPane";
import { DiffDock } from "@/components/chat/DiffDock";
import { useCanvasSession } from "@/hooks/useCanvasSession";
import { useDiffReview } from "@/hooks/useDiffReview";
import { cn } from "@/lib/utils";
import { kbScopeLabel } from "@/lib/knowledgeScope";
import type { Workspace } from "@/types/api";
import { toast } from "sonner";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import "@/styles/workbench.css";

export type WorkbenchPageProps = {
  catalogTick?: number;
  onOpenSettings?: () => void;
};

type LayoutState = {
  sidebarCollapsed: boolean;
  sidebarOpen: boolean;
  railOpen: boolean;
};

export function WorkbenchPage({
  catalogTick = 0,
  onOpenSettings,
}: WorkbenchPageProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState("ready");
  const [busy, setBusy] = useState(false);
  const [gitBranch, setGitBranch] = useState("");
  const [gitInsertions, setGitInsertions] = useState(0);
  const [gitDeletions, setGitDeletions] = useState(0);
  const [toolsEnabled, setToolsEnabled] = useState(true);
  const viewParam = (searchParams.get("view") || "").trim();
  const centerView: CenterViewId =
    location.pathname === "/knowledge" || viewParam === "knowledge"
      ? "knowledge"
      : viewParam === "trajectory"
        ? "trajectory"
        : "chat";
  const setCenterView = useCallback(
    (view: CenterViewId) => {
      if (view === "knowledge") {
        navigate("/knowledge", { replace: true });
        return;
      }
      const next = new URLSearchParams();
      if (view && view !== "chat") next.set("view", String(view));
      const search = next.toString();
      navigate({ pathname: "/", search: search ? `?${search}` : "" }, { replace: true });
    },
    [navigate],
  );
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [activeApprovalCallId, setActiveApprovalCallId] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutState>({
    sidebarCollapsed: false,
    sidebarOpen: false,
    railOpen: false,
  });
  const [narrowUi, setNarrowUi] = useState(
    () => (typeof window !== "undefined" ? window.matchMedia("(max-width: 1100px)").matches : false),
  );
  const [drawerUi, setDrawerUi] = useState(
    () => (typeof window !== "undefined" ? window.matchMedia("(max-width: 820px)").matches : false),
  );

  const timeline = useChatTimeline();
  const trajectory = useTrajectory();
  const dock = useRightDock();
  const delivery = useDeliveryArtifact();
  const commandPalette = useCommandPalette();
  const diffReview = useDiffReview();

  const {
    sessionId,
    setSessionId,
    conversations,
    chatTitle,
    setChatTitle,
    sessionUsage,
    setSessionUsage,
    workspaceId,
    workspaceTitle,
    cwd,
    workspaceKind,
    sshHostId,
    weknoraKbId,
    setWeknoraKbId,
    weknoraKbName,
    setWeknoraKbName,
    activeTools,
    upsertLocalConv,
    syncServerList,
    fetchSession,
    ensureSessionOnServer,
    bindWorkspace,
    startNew,
    switchTo,
    deleteConversation,
    forkCurrent,
    reforkCurrent,
  } = useSessions();

  const canvas = useCanvasSession(sessionId);

  const {
    providerId,
    modelName,
    providerOptions,
    modelOptions,
    providersDisabled,
    modelsDisabled,
    load: loadProviders,
    onProviderChange,
    onModelChange,
  } = useProviders();

  const {
    plugins,
    tools,
    marketplace,
    error: pluginError,
    reloading,
    load: loadPlugins,
    loadMarketplace,
    toggle: togglePlugin,
    reload: reloadPlugins,
    installFromPath,
    installFromZip,
    saveConfig: savePluginConfig,
  } = usePlugins();

  const { workspaces, load: loadWorkspaces } = useWorkspaces();
  const knowledgeCatalog = useKnowledgeCatalog(workspaceId);

  const actionsRef = useRef<ReturnType<typeof useChatActions> | null>(null);
  const completedRef = useRef<() => void>(() => {});

  const stream = useChatStream({
    sessionId,
    timeline,
    trajectory,
    modelName,
    agentMode: actionsRef.current?.agentMode ?? "agent",
    modelProvider: providerId,
    onBusyChange: setBusy,
    onStatusChange: setStatus,
    onTaskId: setCurrentTaskId,
    onUsage: setSessionUsage,
    onCompleted: () => completedRef.current(),
    onModeChange: (mode) => {
      actionsRef.current?.setAgentModeLocal(mode);
    },
    onSyncInteraction: (patch) => {
      void actionsRef.current?.syncInteraction(patch);
    },
    onInbox: (items) => {
      actionsRef.current?.setInboxItems?.(items as any);
    },
    onFileMutation: (payload, args) => {
      diffReview.ingestToolResult(payload, args);
    },
  });

  const actions = useChatActions({
    sessionId,
    setSessionId,
    setChatTitle,
    workspaceId,
    workspaceTitle,
    cwd,
    workspaceKind,
    sshHostId,
    weknoraKbId,
    providerId,
    modelName,
    toolsEnabled,
    upsertLocalConv,
    timeline,
    trajectory,
    stream,
    busy,
    onBusyChange: setBusy,
    onTaskId: setCurrentTaskId,
    onDeliveryCreate: ({ plan, title, callId }) => {
      delivery.setWorkspace(cwd, workspaceKind || "local");
      void delivery.createFromPlan({
        sessionId,
        plan,
        title,
        callId,
        cwd,
        workspaceKind: workspaceKind || "local",
      });
      dock.openTab("delivery", { title: "Delivery", reveal: true });
    },
  });
  actionsRef.current = actions;

  const refreshGitBranch = useCallback(async () => {
    const path = (cwd || "").trim();
    if (!path || workspaceKind === "ssh") {
      setGitBranch("");
      setGitInsertions(0);
      setGitDeletions(0);
      return;
    }
    try {
      const data = await gitInfo(path, workspaceKind || "local");
      setGitBranch(data?.branch || "");
      setGitInsertions(Number(data?.insertions || 0));
      setGitDeletions(Number(data?.deletions || 0));
    } catch {
      setGitBranch("");
      setGitInsertions(0);
      setGitDeletions(0);
    }
  }, [cwd, workspaceKind]);

  useEffect(() => {
    if (!weknoraKbId) {
      setWeknoraKbName("");
      return;
    }
    if (weknoraKbName) return;
    const hit =
      knowledgeCatalog.kbs.find((kb) => kb.id === weknoraKbId) ||
      knowledgeCatalog.localKbs.find((kb) => kb.id === weknoraKbId);
    if (hit) setWeknoraKbName(hit.name || hit.id);
  }, [knowledgeCatalog.kbs, knowledgeCatalog.localKbs, setWeknoraKbName, weknoraKbId, weknoraKbName]);

  const bindKnowledgeBase = useCallback(
    async (kbId: string, kbName?: string) => {
      const id = String(kbId || "").trim();
      setWeknoraKbId(id);
      setWeknoraKbName(id ? kbName || kbScopeLabel(id, kbName) : "");
      try {
        await ensureSessionOnServer();
        if (!id) {
          await patchInteraction(sessionId, { clear_weknora_kb_id: true });
          toast.success("已切换到本地知识库");
        } else {
          await patchInteraction(sessionId, { weknora_kb_id: id });
          toast.success(`已绑定「${kbScopeLabel(id, kbName)}」`);
        }
      } catch (err: any) {
        toast.error(String(err?.message || err || "绑定知识库失败"));
      }
    },
    [ensureSessionOnServer, sessionId, setWeknoraKbId, setWeknoraKbName],
  );

  const openKnowledgeView = useCallback(() => {
    setCenterView("knowledge");
  }, [setCenterView]);

  const loadActivityFromServer = useCallback(async () => {
    try {
      const data = await getPluginCalls(sessionId, 40);
      if (!Array.isArray(data)) return;
      const mapped = data.map((row) => ({
        id: row.call_id,
        kind: row.success ? "RESULT" : "ERROR",
        name: row.tool_name || row.plugin_id,
        detail: row.success ? row.result : row.error || row.arguments,
        callId: row.call_id,
        at: row.created_at ? Date.parse(row.created_at) : Date.now(),
      }));
      if (mapped.length) timeline.setActivityLog(mapped);
    } catch {
      /* ignore */
    }
  }, [sessionId, timeline]);

  const refreshFromServer = useCallback(async () => {
    const data = await fetchSession();
    if (data && Array.isArray(data.messages) && data.messages.length) {
      timeline.loadFromHistory(data.messages);
      trajectory.loadFromHistory(data.messages);
      setChatTitle(data.title || "对话");
      setSessionUsage(data.usage || {});
      upsertLocalConv({
        id: sessionId,
        title: data.title || "对话",
        preview: data.messages.find((m) => m.role === "user")?.content || "",
        updatedAt: data.updated_at || new Date().toISOString(),
        workspaceId: data.workspace_id || "",
        workspaceTitle: data.workspace_title || "",
        cwd: data.cwd || "",
      });
    } else {
      timeline.clear();
      trajectory.clear();
      setChatTitle("新对话");
      setSessionUsage(data?.usage || {});
    }
    stream.turnOpenRef.current = false;
    await loadActivityFromServer();
  }, [
    fetchSession,
    loadActivityFromServer,
    sessionId,
    setChatTitle,
    setSessionUsage,
    stream.turnOpenRef,
    timeline,
    trajectory,
    upsertLocalConv,
  ]);

  completedRef.current = () => {
    void syncServerList();
    void loadActivityFromServer();
    void refreshGitBranch();
    void delivery.syncMutations(sessionId);
  };

  const startNewConversation = useCallback(() => {
    stream.disconnect();
    startNew();
    timeline.clear();
    timeline.clearActivity();
    trajectory.clear();
    stream.turnOpenRef.current = false;
    setCurrentTaskId(null);
    setStatus("ready");
    setBusy(false);
  }, [startNew, stream, timeline, trajectory]);

  const startConversationWithWorkspace = useCallback(
    async (ws: Workspace | { id: string; title?: string; path: string; kind?: string; ssh_host_id?: string }) => {
      stream.disconnect();
      startNew({
        workspace_id: ws.id,
        workspace_title: ws.title,
        cwd: ws.path,
        workspace_kind: ws.kind || "local",
        ssh_host_id: ws.ssh_host_id || "",
      });
      timeline.clear();
      timeline.clearActivity();
      trajectory.clear();
      stream.turnOpenRef.current = false;
      setCurrentTaskId(null);
      try {
        await ensureSessionOnServer({ workspace_id: ws.id });
      } catch (err: any) {
        setStatus(String(err?.message || err));
      }
      setStatus("ready");
      setBusy(false);
      await loadWorkspaces();
    },
    [ensureSessionOnServer, loadWorkspaces, startNew, stream, timeline, trajectory],
  );

  const onPickWorkspace = useCallback(
    async (ws: Workspace) => {
      if (timeline.items.length) {
        await startConversationWithWorkspace(ws);
        return;
      }
      if (cwd) {
        try {
          await bindWorkspace({ workspace_id: ws.id });
          setStatus("workspace ready");
        } catch {
          await startConversationWithWorkspace(ws);
        }
      } else {
        try {
          await ensureSessionOnServer({ workspace_id: ws.id });
          setStatus("workspace ready");
        } catch (err: any) {
          setStatus(String(err?.message || err));
        }
      }
      await loadWorkspaces();
    },
    [
      bindWorkspace,
      cwd,
      ensureSessionOnServer,
      loadWorkspaces,
      startConversationWithWorkspace,
      timeline.items.length,
    ],
  );

  const switchConversation = useCallback(
    async (id: string) => {
      if (!switchTo(id)) return;
      setCurrentTaskId(null);
      setBusy(false);
      // sessionId change reconnects SSE via useChatStream; history reload via effect below
    },
    [switchTo],
  );

  const onDeleteConversation = useCallback(
    async (id: string) => {
      const wasActive = await deleteConversation(id);
      if (wasActive) startNewConversation();
    },
    [deleteConversation, startNewConversation],
  );

  const clearSession = useCallback(async () => {
    timeline.clear();
    trajectory.clear();
    try {
      await apiDeleteSession(sessionId);
    } catch {
      /* ignore */
    }
    setChatTitle("新对话");
    upsertLocalConv({
      id: sessionId,
      title: "新对话",
      preview: "",
      workspaceId,
      workspaceTitle,
      cwd,
    });
    setSessionUsage({});
    timeline.clearActivity();
    setStatus("cleared");
  }, [
    cwd,
    sessionId,
    setChatTitle,
    setSessionUsage,
    timeline,
    trajectory,
    upsertLocalConv,
    workspaceId,
    workspaceTitle,
  ]);

  const toggleSidebar = useCallback(() => {
    if (drawerUi || window.matchMedia("(max-width: 820px)").matches) {
      setLayout((l) => ({
        ...l,
        railOpen: false,
        sidebarOpen: !l.sidebarOpen,
      }));
    } else {
      setLayout((l) => ({ ...l, sidebarCollapsed: !l.sidebarCollapsed }));
    }
  }, [drawerUi]);

  const toggleRail = useCallback(() => {
    if (narrowUi || window.matchMedia("(max-width: 1100px)").matches) {
      setLayout((l) => {
        const next = !l.railOpen;
        if (next) dock.expand();
        return { ...l, sidebarOpen: false, railOpen: next };
      });
    } else {
      dock.toggleCollapsed();
      setLayout((l) => ({ ...l, railOpen: false }));
    }
  }, [dock, narrowUi]);

  const closeOverlays = useCallback(() => {
    setLayout((l) => ({ ...l, sidebarOpen: false, railOpen: false }));
  }, []);

  const onInspectTool = useCallback(
    (activityId: string) => {
      timeline.inspectActivity(activityId);
      dock.openActivity(activityId);
      if (window.matchMedia("(max-width: 1100px)").matches) {
        setLayout((l) => ({ ...l, railOpen: true }));
      }
    },
    [dock, timeline],
  );

  const onTrajectoryInspect = useCallback(
    (row: TrajectoryRow) => {
      trajectory.select(row.id);
      dock.openInspector(row);
      if (row.activityId) {
        timeline.inspectActivity(String(row.activityId));
        // highlight via openActivity
        dock.openActivity(String(row.activityId));
      }
      if (narrowUi || window.matchMedia("(max-width: 1100px)").matches) {
        setLayout((l) => ({ ...l, railOpen: true }));
        dock.expand();
      } else if (dock.state.collapsed) {
        dock.expand();
        setLayout((l) => ({ ...l, railOpen: false }));
      }
    },
    [dock, narrowUi, timeline, trajectory],
  );

  // Mount: narrow media + load catalogs + ensure session history
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1100px)");
    const drawerMq = window.matchMedia("(max-width: 820px)");
    const syncNarrow = () => {
      setNarrowUi(mq.matches);
      if (!mq.matches) setLayout((l) => ({ ...l, railOpen: false }));
    };
    const syncDrawer = () => {
      setDrawerUi(drawerMq.matches);
      if (!drawerMq.matches) setLayout((l) => ({ ...l, sidebarOpen: false }));
    };
    syncNarrow();
    syncDrawer();
    mq.addEventListener("change", syncNarrow);
    drawerMq.addEventListener("change", syncDrawer);

    let cancelled = false;
    (async () => {
      stream.ensureSSE();
      await Promise.all([
        loadProviders(),
        loadPlugins(),
        syncServerList(),
        loadWorkspaces(),
      ]);
      if (cancelled) return;
      await ensureSessionOnServer().catch(() => undefined);
      if (cancelled) return;
      await refreshFromServer();
      await refreshGitBranch();
    })();

    return () => {
      cancelled = true;
      mq.removeEventListener("change", syncNarrow);
      drawerMq.removeEventListener("change", syncDrawer);
      stream.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once
  }, []);

  // catalogTick from settings
  useEffect(() => {
    if (catalogTick > 0) void loadProviders();
  }, [catalogTick, loadProviders]);

  // git refresh when cwd/kind changes + poll local workspaces
  useEffect(() => {
    void refreshGitBranch();
  }, [refreshGitBranch]);

  useEffect(() => {
    if (!cwd || workspaceKind === "ssh") return;
    const id = window.setInterval(() => {
      void refreshGitBranch();
    }, 8000);
    return () => window.clearInterval(id);
  }, [cwd, workspaceKind, refreshGitBranch]);

  // After session switch (sessionId changed by switchTo), reload history
  const prevSessionRef = useRef(sessionId);
  useEffect(() => {
    if (prevSessionRef.current === sessionId) return;
    prevSessionRef.current = sessionId;
    void refreshFromServer();
  }, [sessionId, refreshFromServer]);

  const showMask = (drawerUi && layout.sidebarOpen) || (narrowUi && layout.railOpen);

  const appClass = useMemo(
    () =>
      cn(
        "nlm-app",
        layout.sidebarCollapsed && "sidebar-collapsed",
        dock.state.collapsed && "rail-collapsed",
        layout.sidebarOpen && "sidebar-open",
        layout.railOpen && "rail-open",
      ),
    [dock.state.collapsed, layout.railOpen, layout.sidebarCollapsed, layout.sidebarOpen],
  );

  const highlightId = dock.highlightActivityId || timeline.highlightActivityId;

  return (
    <>
      <div className="atmosphere" aria-hidden="true" />
      {showMask ? (
        <div
          className="workbench-mask"
          aria-hidden="true"
          onClick={closeOverlays}
        />
      ) : null}
      <div className={appClass}>
        <Sidebar
          conversations={conversations}
          workspaces={workspaces}
          activeId={sessionId}
          status={status}
          collapsed={drawerUi ? !layout.sidebarOpen : layout.sidebarCollapsed}
          onToggleCollapse={toggleSidebar}
          onNew={startNewConversation}
          onSelect={(id) => void switchConversation(id)}
          onDelete={(id) => void onDeleteConversation(id)}
          onOpenWorkspace={(ws) => void startConversationWithWorkspace(ws as Workspace)}
          onOpenSettings={onOpenSettings}
          onOpenKnowledge={openKnowledgeView}
          knowledgeActive={centerView === "knowledge"}
        />

        <main className={cn("nlm-workspace", canvas.open && "nlm-workspace--canvas")}>
          <Topbar
            title={chatTitle}
            centerView={centerView}
            onCenterViewChange={setCenterView}
            workspaceTitle={workspaceTitle}
            cwd={cwd}
            workspaceKind={workspaceKind}
            onClear={() => void clearSession()}
            onOpenCommand={commandPalette.show}
            canvasOpen={canvas.open}
            onToggleCanvas={canvas.togglePane}
            weknoraKbId={weknoraKbId}
            weknoraKbName={weknoraKbName}
            onWeknoraKbClick={openKnowledgeView}
            activeTools={activeTools}
          />

          <section className="nlm-chat-panel" aria-label={centerView === "knowledge" ? "知识库" : "对话"}>
            {(() => {
              const composer = (
                <Composer
                  value={actions.input}
                  onChange={actions.setInput}
                  providerId={providerId}
                  modelName={modelName}
                  providerOptions={providerOptions}
                  modelOptions={modelOptions}
                  providersDisabled={providersDisabled}
                  modelsDisabled={modelsDisabled}
                  toolsEnabled={toolsEnabled}
                  onToolsEnabledChange={setToolsEnabled}
                  agentMode={actions.agentMode}
                  onAgentModeChange={actions.setAgentMode}
                  autoAccept={actions.autoAccept}
                  onAutoAcceptChange={actions.setAutoAccept}
                  multitask={actions.multitask}
                  onMultitaskChange={actions.setMultitask}
                  permissionPreset={actions.permissionPreset}
                  onPermissionPresetChange={actions.setPermissionPreset}
                  planEnforcement={actions.planEnforcement}
                  onPlanEnforcementChange={actions.setPlanEnforcement}
                  experienceTier={actions.experienceTier}
                  onExperienceTierChange={actions.setExperienceTier}
                  reasoningEffort={actions.reasoningEffort}
                  onReasoningEffortChange={actions.setReasoningEffort}
                  sessionUsage={sessionUsage}
                  items={timeline.items}
                  tools={tools}
                  cwd={cwd}
                  workspaceTitle={workspaceTitle}
                  workspaceKind={workspaceKind}
                  sshHostId={sshHostId}
                  contextRefs={actions.contextRefs}
                  onAddContextRef={actions.addContextRef}
                  onRemoveContextRef={actions.removeContextRef}
                  gitBranch={gitBranch}
                  gitInsertions={gitInsertions}
                  gitDeletions={gitDeletions}
                  busy={busy}
                  busyEnterMode={actions.busyEnterMode}
                  onBusyEnterModeChange={actions.setBusyEnterMode}
                  inboxItems={actions.inboxItems}
                  onRemoveInboxItem={(id) => void actions.removeInboxItem(id)}
                  onProviderIdChange={onProviderChange}
                  onModelNameChange={onModelChange}
                  onSend={(opts) => void actions.sendChat(undefined, opts)}
                  onStop={() => void actions.stopGeneration(currentTaskId)}
                  weknoraKbId={weknoraKbId}
                  weknoraKbName={weknoraKbName}
                  knowledgeKbs={knowledgeCatalog.kbs}
                  localKbs={knowledgeCatalog.localKbs}
                  knowledgeHealth={knowledgeCatalog.health}
                  onWeknoraKbChange={(id, name) => void bindKnowledgeBase(id, name)}
                  onOpenKnowledge={openKnowledgeView}
                  sessionId={sessionId}
                  workspaceId={workspaceId}
                />
              );

              const chatColumn = (
                <>
                  {centerView === "trajectory" ? (
                    <TrajectoryView
                      rows={trajectory.rows}
                      followTail={trajectory.followTail}
                      selectedId={trajectory.selectedId}
                      onFollowTailChange={trajectory.setFollowTail}
                      onSelect={trajectory.select}
                      onInspect={onTrajectoryInspect}
                    />
                  ) : (
                    <ChatMessages
                      sessionId={sessionId}
                      items={timeline.items}
                      showWorkspacePicker={!cwd}
                      modelProvider={providerId}
                      modelName={modelName}
                      experienceTier={actions.experienceTier}
                      highlightCallId={activeApprovalCallId}
                      onInspectTool={onInspectTool}
                      onStopTool={() => void actions.stopGeneration(currentTaskId)}
                      onPickWorkspace={(ws) => void onPickWorkspace(ws)}
                      onResolveAsk={(p) => void actions.resolveAsk(p)}
                      onResolvePlanReview={(p) => void actions.resolvePlanReview(p)}
                      onAcceptPlan={() => {
                        void actions.acceptPlan();
                      }}
                      onOpenKnowledge={openKnowledgeView}
                    />
                  )}

                  <ApprovalDock
                    items={timeline.items.filter((it) => it.kind === "approval") as any}
                    onResolve={(p) => void actions.resolveApproval(p)}
                    onActiveCallIdChange={setActiveApprovalCallId}
                  />

                  <DiffDock
                    items={diffReview.pending}
                    cwd={cwd}
                    workspaceKind={workspaceKind}
                    onAccept={(id) => {
                      diffReview.accept(id);
                      window.setTimeout(() => diffReview.dismiss(id), 400);
                    }}
                    onReject={(id) =>
                      void diffReview.reject(id, {
                        cwd,
                        workspaceKind,
                        sessionId,
                      })
                    }
                    onDismiss={diffReview.dismiss}
                  />

                  {composer}
                </>
              );

              if (centerView === "knowledge") {
                return (
                  <KnowledgeView
                    className="min-h-0 flex-1"
                    cwd={cwd}
                    workspaceId={workspaceId}
                    sessionId={sessionId}
                    boundKbId={weknoraKbId}
                    boundKbName={weknoraKbName}
                    kbs={knowledgeCatalog.kbs}
                    localKbs={knowledgeCatalog.localKbs}
                    health={knowledgeCatalog.health}
                    catalogLoading={knowledgeCatalog.loading}
                    onBindKb={(id, name) => void bindKnowledgeBase(id, name)}
                    onCatalogRefresh={() => void knowledgeCatalog.refresh()}
                    onAskAbout={(text) => {
                      if (text) actions.setInput(text);
                      setCenterView("chat");
                    }}
                  />
                );
              }

              if (!canvas.open) return chatColumn;

              return (
                <div className="nlm-center-split">
                  <div className="nlm-chat-column">{chatColumn}</div>
                  <CanvasPane
                    canvas={canvas}
                    modelProvider={providerId}
                    modelName={modelName}
                    experienceTier={actions.experienceTier}
                    sessionId={sessionId}
                    cwd={cwd}
                    workspaceKind={workspaceKind}
                  />
                </div>
              );
            })()}
          </section>
        </main>

        <RightDock
          dock={dock}
          collapsed={narrowUi ? !layout.railOpen : dock.state.collapsed}
          onToggleCollapse={toggleRail}
          plugins={plugins}
          tools={tools}
          activity={timeline.activityLog}
          jobs={timeline.items.filter((it) => it.kind === "tool" || it.kind === "subagent")}
          usage={sessionUsage}
          pluginError={pluginError || null}
          reloading={reloading}
          highlightActivityId={highlightId}
          inspectorPayload={dock.inspectorPayload}
          contextItems={timeline.items}
          modelName={modelName}
          cwd={cwd}
          workspaceKind={workspaceKind}
          workspaceTitle={workspaceTitle}
          draft={actions.input}
          teamId={sessionId}
          sessionId={sessionId}
          workspaceId={workspaceId}
          delivery={delivery}
          onBoundKbChange={(kbId, kbName) => {
            void bindKnowledgeBase(kbId, kbName);
          }}
          onInspectJob={onInspectTool}
          onStopJob={() => void actions.stopGeneration(currentTaskId)}
          onTogglePlugin={async (id, enabled) => {
            try {
              await togglePlugin(id, enabled);
              toast.success(enabled ? `已启用 ${id}` : `已停用 ${id}`);
            } catch (err: any) {
              const msg = String(err?.message || err);
              setStatus(msg);
              toast.error(msg);
              await loadPlugins();
            }
          }}
          onReload={async () => {
            try {
              await reloadPlugins(null);
              setStatus("plugins reloaded");
              toast.success("插件已重载");
            } catch (err: any) {
              const msg = String(err?.message || err);
              setStatus(msg);
              toast.error(msg);
            }
          }}
          onReloadOne={async (pluginId) => {
            try {
              await reloadPlugins(pluginId);
              setStatus(`reloaded ${pluginId}`);
              toast.success(`已重载 ${pluginId}`);
            } catch (err: any) {
              const msg = String(err?.message || err);
              setStatus(msg);
              toast.error(msg);
            }
          }}
          onRetryPlugin={async (pluginId) => {
            try {
              await togglePlugin(pluginId, true);
              setStatus(`retry enabled ${pluginId}`);
              toast.success(`已重试启用 ${pluginId}`);
            } catch {
              try {
                await reloadPlugins(pluginId);
                await togglePlugin(pluginId, true);
                toast.success(`已重试启用 ${pluginId}`);
              } catch (err: any) {
                const msg = String(err?.message || err);
                setStatus(msg);
                toast.error(msg);
              }
            }
          }}
          onSavePluginConfig={async (pluginId, values) => {
            try {
              await savePluginConfig(pluginId, values);
              setStatus(`已保存 ${pluginId} 配置`);
              toast.success(`已保存 ${pluginId} 配置`);
            } catch (err: any) {
              const msg = String(err?.message || err);
              setStatus(msg);
              toast.error(msg);
              throw err;
            }
          }}
          marketplace={marketplace}
          onLoadMarketplace={async () => {
            try {
              await loadMarketplace();
            } catch (err: any) {
              toast.error(String(err?.message || err));
            }
          }}
          onInstallPluginPath={async (path) => {
            try {
              const data = await installFromPath(path);
              toast.success(`已安装 ${data?.id || path}`);
            } catch (err: any) {
              const msg = String(err?.message || err);
              toast.error(msg);
              throw err;
            }
          }}
          onInstallPluginZip={async (file) => {
            try {
              const data = await installFromZip(file);
              toast.success(`已安装 ${data?.id || file.name}`);
            } catch (err: any) {
              const msg = String(err?.message || err);
              toast.error(msg);
              throw err;
            }
          }}
        />
      </div>

      <CommandPalette
        open={commandPalette.open}
        onOpenChange={commandPalette.setOpen}
        conversations={conversations}
        cwd={cwd}
        workspaceId={workspaceId}
        sessionId={sessionId}
        onNewChat={startNewConversation}
        onSelectChat={(id) => void switchConversation(id)}
        onClearChat={() => void clearSession()}
        onForkChat={() => {
          void (async () => {
            try {
              await forkCurrent();
              toast.success("已分叉会话");
            } catch (err: any) {
              toast.error(String(err?.message || err || "分叉失败"));
            }
          })();
        }}
        onReforkChat={() => {
          void (async () => {
            try {
              await reforkCurrent();
              toast.success("已从分叉点重新开枝");
            } catch (err: any) {
              toast.error(String(err?.message || err || "回到分叉点失败"));
            }
          })();
        }}
        onBookmarkLast={() => {
          void (async () => {
            try {
              const sess = await getSession(sessionId);
              const count = Array.isArray(sess?.messages) ? sess.messages.length : 0;
              if (count < 1) {
                toast.error("当前会话没有可收藏的消息");
                return;
              }
              await addSessionBookmark(sessionId, {
                message_index: count - 1,
                label: "bookmark",
              });
              toast.success(`已收藏消息 #${count - 1}`);
            } catch (err: any) {
              toast.error(String(err?.message || err || "收藏失败"));
            }
          })();
        }}
        onInsertText={(text) => {
          const cur = actions.input || "";
          actions.setInput(cur.trim() ? `${cur.trim()}\n${text}` : text);
        }}
        onApplyPreset={(name) => {
          void (async () => {
            try {
              await patchInteraction(sessionId, { preset_name: name, cwd: cwd || undefined });
              await fetchSession();
              toast.success(`已应用预设 ${name}`);
            } catch (err: any) {
              toast.error(String(err?.message || err || "预设应用失败"));
            }
          })();
        }}
        onClearActiveTools={() => {
          void (async () => {
            try {
              await patchInteraction(sessionId, { clear_active_tools: true });
              await fetchSession();
              toast.success("已清除工具收敛");
            } catch (err: any) {
              toast.error(String(err?.message || err || "清除失败"));
            }
          })();
        }}
        onSetCenterView={setCenterView}
        onToggleCanvas={canvas.togglePane}
        onNewCanvas={() =>
          canvas.openDoc({
            kind: "markdown",
            title: "笔记",
            body: "# Canvas\n\n在此编辑旁侧文档。\n",
            dedupeKey: `blank:${Date.now()}`,
          })
        }
        onOpenDockTab={(tab) => {
          dock.expand();
          dock.openTab(tab, { reveal: true });
          if (narrowUi) setLayout((s) => ({ ...s, railOpen: true }));
        }}
        onToggleTools={() => setToolsEnabled((v) => !v)}
        onOpenSettings={onOpenSettings}
      />
    </>
  );
}

export default WorkbenchPage;
