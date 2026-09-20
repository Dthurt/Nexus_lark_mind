import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  acceptPlan,
  cancelChatTask,
  cancelSession,
  deleteSessionInboxItem,
  getSessionInbox,
  patchInteraction,
  postApprovals,
  postAskAnswers,
  postChat,
  persistTurnError,
  postSessionInbox,
  type InboxItem,
} from "@/api/endpoints";
import type { ChatStreamApi } from "@/hooks/useChatStream";
import type { ChatTimelineApi } from "@/hooks/useChatTimeline";
import type { useTrajectory } from "@/hooks/useTrajectory";
import {
  addContextRef,
  type ContextRef,
} from "@/lib/contextRefs";
import { formatStreamErrorText } from "@/lib/chatError";

type TrajectoryApi = ReturnType<typeof useTrajectory>;

const AGENT_MODE_KEY = "nlm_agent_mode";
const AUTO_ACCEPT_KEY = "nlm_auto_accept";
const MULTITASK_KEY = "nlm_multitask";
const SESSION_KEY = "nlm_session_id";
const BUSY_ENTER_KEY = "nlm_busy_enter";
const PERMISSION_PRESET_KEY = "nlm_permission_preset";
const PLAN_ENFORCEMENT_KEY = "nlm_plan_enforcement";
const EXPERIENCE_TIER_KEY = "nlm_experience_tier";
const REASONING_EFFORT_KEY = "nlm_reasoning_effort";

export type BusyEnterMode = "queue" | "steer";
export type PermissionPreset = "read-only" | "workspace-write" | "danger-full-access";
export type PlanEnforcement = "hard" | "soft";
export type ExperienceTier = "fast" | "balanced" | "high";
export type ReasoningEffort = "low" | "medium" | "high";

export type SendChatOpts = {
  /** Flip default busy-enter mode for this send (Ctrl+Enter). */
  alternate?: boolean;
};

export type UseChatActionsOpts = {
  sessionId: string;
  setSessionId?: (id: string) => void;
  chatTitle?: string;
  setChatTitle?: (t: string) => void;
  workspaceId?: string;
  workspaceTitle?: string;
  cwd?: string;
  workspaceKind?: string;
  sshHostId?: string;
  weknoraKbId?: string;
  providerId?: string;
  modelName?: string;
  toolsEnabled?: boolean;
  upsertLocalConv?: (partial: any) => void;
  timeline: Pick<
    ChatTimelineApi,
    | "appendMessage"
    | "beginAssistantTurn"
    | "dismissLiveAssistant"
    | "setBotActivity"
    | "resolveApprovalLocal"
    | "resolveAskLocal"
    | "resolvePlanReviewLocal"
    | "clearPlanReadyFlags"
    | "markRunningToolsStopped"
    | "items"
  >;
  trajectory: Pick<TrajectoryApi, "startTurn" | "addUser" | "addError">;
  stream: Pick<
    ChatStreamApi,
    "ensureSSE" | "reopenForSession" | "turnOpenRef" | "setBusy" | "setStatus" | "setActivity"
  >;
  busy?: boolean;
  onBusyChange?: (b: boolean) => void;
  onTaskId?: (id: string | null) => void;
  onModeChange?: (mode: string) => void;
  /** Create Delivery artifact after plan approve / accept-plan. */
  onDeliveryCreate?: (opts: { plan: string; title?: string; callId?: string }) => void | Promise<void>;
};

/**
 * sendChat / approvals / ask-answers / accept-plan — extracted from WorkbenchView.
 */
export function useChatActions(opts: UseChatActionsOpts) {
  const {
    sessionId,
    setSessionId,
    setChatTitle,
    workspaceId = "",
    workspaceTitle = "",
    cwd = "",
    workspaceKind = "",
    sshHostId = "",
    weknoraKbId = "",
    providerId = "",
    modelName = "",
    toolsEnabled = true,
    upsertLocalConv,
    timeline,
    trajectory,
    stream,
    busy = false,
    onBusyChange,
    onTaskId,
    onModeChange,
    onDeliveryCreate,
  } = opts;

  const [agentMode, setAgentModeState] = useState<"agent" | "plan" | string>(() =>
    typeof localStorage !== "undefined" && localStorage.getItem(AGENT_MODE_KEY) === "plan"
      ? "plan"
      : "agent",
  );
  const [autoAccept, setAutoAcceptState] = useState(
    () => typeof localStorage !== "undefined" && localStorage.getItem(AUTO_ACCEPT_KEY) === "1",
  );
  const [multitask, setMultitaskState] = useState(
    () => typeof localStorage === "undefined" || localStorage.getItem(MULTITASK_KEY) !== "0",
  );
  const [input, setInput] = useState("");
  const [contextRefs, setContextRefs] = useState<ContextRef[]>([]);
  const contextRefsRef = useRef(contextRefs);
  contextRefsRef.current = contextRefs;
  const [inboxItems, setInboxItems] = useState<InboxItem[]>([]);
  const [busyEnterMode, setBusyEnterModeState] = useState<BusyEnterMode>(() =>
    typeof localStorage !== "undefined" && localStorage.getItem(BUSY_ENTER_KEY) === "steer"
      ? "steer"
      : "queue",
  );
  const [permissionPreset, setPermissionPresetState] = useState<PermissionPreset>(() => {
    const v =
      typeof localStorage !== "undefined" ? localStorage.getItem(PERMISSION_PRESET_KEY) || "" : "";
    if (v === "read-only" || v === "danger-full-access") return v;
    return "workspace-write";
  });
  const [planEnforcement, setPlanEnforcementState] = useState<PlanEnforcement>(() =>
    typeof localStorage !== "undefined" && localStorage.getItem(PLAN_ENFORCEMENT_KEY) === "soft"
      ? "soft"
      : "hard",
  );
  const [experienceTier, setExperienceTierState] = useState<ExperienceTier>(() => {
    const v =
      typeof localStorage !== "undefined" ? localStorage.getItem(EXPERIENCE_TIER_KEY) || "" : "";
    if (v === "fast" || v === "high") return v;
    return "balanced";
  });
  const [reasoningEffort, setReasoningEffortState] = useState<ReasoningEffort>(() => {
    const v =
      typeof localStorage !== "undefined" ? localStorage.getItem(REASONING_EFFORT_KEY) || "" : "";
    if (v === "low" || v === "high") return v;
    return "medium";
  });

  const sessionIdRef = useRef(sessionId);
  const busyRef = useRef(busy);
  sessionIdRef.current = sessionId;
  busyRef.current = busy;

  const setBusyEnterMode = useCallback((mode: BusyEnterMode) => {
    setBusyEnterModeState(mode);
    try {
      localStorage.setItem(BUSY_ENTER_KEY, mode);
    } catch {
      /* ignore */
    }
  }, []);

  const refreshInbox = useCallback(async () => {
    try {
      const data = await getSessionInbox(sessionIdRef.current);
      setInboxItems(Array.isArray(data?.items) ? data.items : []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refreshInbox();
  }, [sessionId, refreshInbox]);

  useEffect(() => {
    if (permissionPreset === "workspace-write") return;
    setPermissionPresetState("workspace-write");
    try {
      localStorage.setItem(PERMISSION_PRESET_KEY, "workspace-write");
    } catch {
      /* ignore */
    }
    void syncInteraction({
      permission_preset: "workspace-write",
      auto_accept: autoAccept,
    });
    // One-time unstick leftover 权限 presets so Accept is the only gate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const syncInteraction = useCallback(async (patch: Record<string, unknown>) => {
    try {
      await patchInteraction(sessionIdRef.current, patch as any);
    } catch {
      /* ignore */
    }
  }, []);

  const setPermissionPreset = useCallback(
    (preset: PermissionPreset) => {
      setPermissionPresetState(preset);
      try {
        localStorage.setItem(PERMISSION_PRESET_KEY, preset);
      } catch {
        /* ignore */
      }
      let auto = false;
      if (preset === "danger-full-access") {
        auto = true;
        setAutoAcceptState(true);
        try {
          localStorage.setItem(AUTO_ACCEPT_KEY, "1");
        } catch {
          /* ignore */
        }
      } else if (preset === "read-only") {
        auto = false;
        setAutoAcceptState(false);
        try {
          localStorage.setItem(AUTO_ACCEPT_KEY, "0");
        } catch {
          /* ignore */
        }
      } else {
        auto = !!autoAccept;
      }
      void syncInteraction({
        permission_preset: preset,
        auto_accept: auto,
      });
    },
    [autoAccept, syncInteraction],
  );

  const setPlanEnforcement = useCallback(
    (mode: PlanEnforcement) => {
      setPlanEnforcementState(mode);
      try {
        localStorage.setItem(PLAN_ENFORCEMENT_KEY, mode);
      } catch {
        /* ignore */
      }
      void syncInteraction({ plan_enforcement: mode });
    },
    [syncInteraction],
  );

  const setExperienceTier = useCallback(
    (tier: ExperienceTier) => {
      setExperienceTierState(tier);
      try {
        localStorage.setItem(EXPERIENCE_TIER_KEY, tier);
      } catch {
        /* ignore */
      }
      void syncInteraction({ experience_tier: tier });
    },
    [syncInteraction],
  );

  const setReasoningEffort = useCallback(
    (effort: ReasoningEffort) => {
      setReasoningEffortState(effort);
      try {
        localStorage.setItem(REASONING_EFFORT_KEY, effort);
      } catch {
        /* ignore */
      }
      void syncInteraction({ reasoning_effort: effort });
    },
    [syncInteraction],
  );

  const setAgentModeLocal = useCallback((v: string) => {
    setAgentModeState(v);
    try {
      localStorage.setItem(AGENT_MODE_KEY, v);
    } catch {
      /* ignore */
    }
  }, []);

  const setAgentMode = useCallback(
    (v: string) => {
      setAgentModeLocal(v);
      syncInteraction({
        agent_mode: v,
        plan_status: v === "plan" ? "drafting" : "idle",
      });
      if (v !== "plan") timeline.clearPlanReadyFlags();
      onModeChange?.(v);
    },
    [onModeChange, setAgentModeLocal, syncInteraction, timeline],
  );

  const setAutoAccept = useCallback(
    (v: boolean) => {
      setAutoAcceptState(v);
      try {
        localStorage.setItem(AUTO_ACCEPT_KEY, v ? "1" : "0");
      } catch {
        /* ignore */
      }
      if (permissionPreset !== "workspace-write") {
        setPermissionPresetState("workspace-write");
        try {
          localStorage.setItem(PERMISSION_PRESET_KEY, "workspace-write");
        } catch {
          /* ignore */
        }
      }
      syncInteraction({
        auto_accept: !!v,
        permission_preset: "workspace-write",
      });
    },
    [permissionPreset, syncInteraction],
  );

  const setMultitask = useCallback((v: boolean) => {
    setMultitaskState(v);
    try {
      localStorage.setItem(MULTITASK_KEY, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  // Persist agentMode/autoAccept/multitask via setters (localStorage keys preserved).

  const resolveApproval = useCallback(
    async ({ item, action }: { item: any; action?: string }) => {
      if (!item?.callId) return;
      const act = action || "allow";
      try {
        await postApprovals(sessionIdRef.current, {
          call_id: item.callId,
          action: act,
        });
        if (act === "allow_session" || act === "always") {
          setAutoAccept(true);
        }
        timeline.resolveApprovalLocal(
          item.callId,
          act === "deny" ? "denied" : "allowed",
          act,
        );
        stream.setActivity("model", "正在调用模型…", modelName || "");
      } catch (err) {
        timeline.appendMessage("assistant", `审批失败：${err}`, { rich: false });
      }
    },
    [modelName, setAutoAccept, stream, timeline],
  );

  const resolveAsk = useCallback(
    async ({
      item,
      action,
      answers,
    }: {
      item: any;
      action?: string;
      answers?: Record<string, unknown>;
    }) => {
      if (!item?.callId) return;
      try {
        await postAskAnswers(sessionIdRef.current, {
          call_id: item.callId,
          action: action || "submit",
          answers: answers || {},
        } as any);
        timeline.resolveAskLocal(
          item.callId,
          action === "deny" ? "dismissed" : "answered",
          answers || null,
        );
        stream.setActivity("model", "正在调用模型…", modelName || "");
      } catch (err) {
        timeline.appendMessage("assistant", `提交回答失败：${err}`, { rich: false });
      }
    },
    [modelName, stream, timeline],
  );

  const resolvePlanReview = useCallback(
    async ({
      item,
      action,
      feedback,
    }: {
      item: any;
      action?: string;
      feedback?: string;
    }) => {
      if (!item?.callId) return;
      const act = (action || "deny").toLowerCase();
      try {
        await postAskAnswers(sessionIdRef.current, {
          call_id: item.callId,
          action:
            act === "approve" ? "approve" : act === "keep_planning" ? "keep_planning" : "deny",
          feedback: feedback || "",
          reason: feedback || "",
        } as any);
        const status =
          act === "approve"
            ? "approved"
            : act === "keep_planning"
              ? "keep_planning"
              : "dismissed";
        timeline.resolvePlanReviewLocal(item.callId, status);
        if (act === "approve") {
          setAgentMode("agent");
          stream.setActivity("model", "计划已批准，开始执行…", modelName || "");
          const planText = String(item.plan || item.content || "").trim();
          if (planText && onDeliveryCreate) {
            void onDeliveryCreate({
              plan: planText,
              title: item.title,
              callId: item.callId,
            });
          }
        } else {
          stream.setActivity("model", "正在调用模型…", modelName || "");
        }
      } catch (err) {
        timeline.appendMessage("assistant", `计划审阅提交失败：${err}`, { rich: false });
      }
    },
    [modelName, onDeliveryCreate, setAgentMode, stream, timeline],
  );

  const acceptPlanAction = useCallback(async () => {
    if (busyRef.current) return;
    // Seed Delivery from the latest plan_review or planReady assistant content.
    try {
      const list = Array.isArray(timeline.items) ? timeline.items : [];
      let planText = "";
      let callId = "";
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const it = list[i] as any;
        if (it?.kind === "plan_review" && it.plan) {
          planText = String(it.plan);
          callId = String(it.callId || "");
          break;
        }
        if (it?.kind === "msg" && it.role === "assistant" && it.planReady && it.content) {
          planText = String(it.content);
          break;
        }
      }
      if (planText && onDeliveryCreate) {
        void onDeliveryCreate({ plan: planText, callId: callId || undefined });
      }
    } catch {
      /* ignore seed errors */
    }
    timeline.clearPlanReadyFlags();
    setAgentMode("agent");
    stream.ensureSSE();
    onBusyChange?.(true);
    stream.setBusy(true);
    stream.setStatus("accepting plan…");
    timeline.beginAssistantTurn({
      phase: "send",
      label: "正在按计划执行…",
      detail: "",
      startedAt: Date.now(),
    });
    try {
      const data = await acceptPlan(sessionIdRef.current, {
        tools_enabled: !!toolsEnabled,
        model_provider: providerId || undefined,
        model_name: modelName || undefined,
        workspace_id: workspaceId || undefined,
        cwd: cwd || undefined,
        workspace_kind: workspaceKind || undefined,
        ssh_host_id: sshHostId || undefined,
        auto_accept: !!autoAccept,
        permission_preset: "workspace-write",
      } as any);
      if ((data as any)?.task_id) onTaskId?.((data as any).task_id);
      stream.setStatus("queued");
      stream.setActivity("model", "正在调用模型…", modelName || "");
      } catch (err: any) {
        const raw = String(err?.message || err);
        timeline.dismissLiveAssistant();
        timeline.appendMessage("assistant", formatStreamErrorText(raw), { rich: false, error: true });
        void persistTurnError(sessionIdRef.current, { error: raw }).catch(() => undefined);
        onBusyChange?.(false);
        stream.setBusy(false);
        stream.setStatus("error");
      }
  }, [
    autoAccept,
    cwd,
    modelName,
    onBusyChange,
    onDeliveryCreate,
    onTaskId,
    providerId,
    setAgentMode,
    sshHostId,
    stream,
    timeline,
    toolsEnabled,
    workspaceId,
    workspaceKind,
  ]);

  const stopGeneration = useCallback(
    async (taskId?: string | null, opts?: { keepInbox?: boolean }) => {
      const keepInbox = opts?.keepInbox !== false;
      try {
        if (taskId && keepInbox) {
          await cancelChatTask(taskId, { keep_inbox: true });
        } else {
          await cancelSession(sessionIdRef.current, { keep_inbox: keepInbox });
        }
        if (!keepInbox) setInboxItems([]);
        timeline.markRunningToolsStopped();
        stream.setStatus("正在停止…");
        stream.setActivity("stop", "正在停止…");
      } catch (err) {
        stream.setStatus(String(err));
        onBusyChange?.(false);
        stream.setBusy(false);
      }
    },
    [onBusyChange, stream, timeline],
  );

  const removeInboxItem = useCallback(async (itemId: string) => {
    try {
      const data = await deleteSessionInboxItem(sessionIdRef.current, itemId);
      setInboxItems(Array.isArray(data?.items) ? data.items : []);
    } catch (err: any) {
      toast.error(String(err?.message || err || "撤销失败"));
    }
  }, []);

  const applyInboxSnapshot = useCallback((items: InboxItem[]) => {
    setInboxItems(Array.isArray(items) ? items : []);
  }, []);

  const sendChat = useCallback(
    async (contentOverride?: string, sendOpts?: SendChatOpts) => {
      const content = (contentOverride ?? input).trim();
      if (!content) return;
      if (!busyRef.current && !(cwd || "").trim()) {
        toast.error("请先绑定工作目录");
        return;
      }

      // Busy: push to session inbox (steer or queue) instead of blocking.
      if (busyRef.current) {
        let kind: BusyEnterMode = busyEnterMode;
        if (sendOpts?.alternate) {
          kind = kind === "queue" ? "steer" : "queue";
        }
        stream.ensureSSE();
        const draft = content;
        setInput(""); // optimistic
        try {
          const data = await postSessionInbox(sessionIdRef.current, {
            kind,
            content: draft,
          });
          setInboxItems(Array.isArray(data?.items) ? data.items : []);
          if (kind === "queue") {
            timeline.appendMessage("user", draft, { rich: false });
            trajectory.addUser(draft);
          }
          const label =
            kind === "steer"
              ? "已加入中途引导（下一步模型调用前注入）"
              : "已加入排队（本轮结束后发送）";
          stream.setStatus(label);
          toast.success(label);
        } catch (err: any) {
          setInput((cur) => (cur.trim() ? cur : draft));
          toast.error(String(err?.message || err || "加入收件箱失败"));
        }
        return;
      }

      stream.ensureSSE();
      const draft = content;
      const refs = contextRefsRef.current.slice();
      setInput("");
      setContextRefs([]);
      timeline.appendMessage("user", draft, { rich: false });
      if (!stream.turnOpenRef.current) {
        trajectory.startTurn();
        stream.turnOpenRef.current = true;
      }
      trajectory.addUser(draft);
      const title = draft.slice(0, 36) + (draft.length > 36 ? "…" : "");
      upsertLocalConv?.({
        id: sessionIdRef.current,
        title,
        preview: draft.slice(0, 80),
        updatedAt: new Date().toISOString(),
        workspaceId,
        workspaceTitle,
        cwd,
      });
      setChatTitle?.(title);
      onBusyChange?.(true);
      stream.setBusy(true);
      stream.setStatus("sending…");
      timeline.beginAssistantTurn({
        phase: "send",
        label: "正在发送…",
        detail: "",
        startedAt: Date.now(),
      });
      try {
        const data = await postChat({
          content: draft,
          session_id: sessionIdRef.current,
          stream: true,
          tools_enabled: !!toolsEnabled,
          agent_mode: agentMode || "agent",
          auto_accept: !!autoAccept,
          multitask: !!multitask,
          permission_preset: "workspace-write",
          plan_enforcement: planEnforcement,
          experience_tier: experienceTier,
          reasoning_effort: reasoningEffort,
          model_provider: providerId || undefined,
          model_name: modelName || undefined,
          workspace_id: workspaceId || undefined,
          cwd: cwd || undefined,
          workspace_kind: workspaceKind || undefined,
          ssh_host_id: sshHostId || undefined,
          context_refs: refs.length ? refs : undefined,
          weknora_kb_id: weknoraKbId || "",
        } as any);
        if ((data as any)?.task_id) onTaskId?.((data as any).task_id);
        if ((data as any)?.session_id && (data as any).session_id !== sessionIdRef.current) {
          const newId = (data as any).session_id as string;
          setSessionId?.(newId);
          try {
            localStorage.setItem(SESSION_KEY, newId);
          } catch {
            /* ignore */
          }
          stream.reopenForSession(newId);
        }
        stream.setStatus("queued");
        stream.setActivity("model", "正在调用模型…", modelName || "");
      } catch (err: any) {
        const raw = String(err?.message || err);
        timeline.dismissLiveAssistant();
        timeline.appendMessage("assistant", formatStreamErrorText(raw), { rich: false, error: true });
        trajectory.addError(raw);
        void persistTurnError(sessionIdRef.current, { error: raw, user_content: draft }).catch(
          () => undefined,
        );
        setInput((cur) => (cur.trim() ? cur : draft));
        onBusyChange?.(false);
        stream.setBusy(false);
        stream.setStatus("error");
        toast.error(String(err?.message || err || "发送失败"));
      }
    },
    [
      agentMode,
      autoAccept,
      busyEnterMode,
      permissionPreset,
      planEnforcement,
      experienceTier,
      reasoningEffort,
      cwd,
      input,
      modelName,
      multitask,
      onBusyChange,
      onTaskId,
      providerId,
      setChatTitle,
      setSessionId,
      sshHostId,
      weknoraKbId,
      stream,
      timeline,
      toolsEnabled,
      trajectory,
      upsertLocalConv,
      workspaceId,
      workspaceKind,
      workspaceTitle,
    ],
  );

  return {
    input,
    setInput,
    contextRefs,
    addContextRef: (ref: ContextRef) => setContextRefs((prev) => addContextRef(prev, ref)),
    removeContextRef: (path: string) =>
      setContextRefs((prev) => prev.filter((r) => r.path !== path)),
    clearContextRefs: () => setContextRefs([]),
    agentMode,
    setAgentMode,
    setAgentModeLocal,
    autoAccept,
    setAutoAccept,
    multitask,
    setMultitask,
    syncInteraction,
    sendChat,
    stopGeneration,
    resolveApproval,
    resolveAsk,
    resolvePlanReview,
    acceptPlan: acceptPlanAction,
    inboxItems,
    setInboxItems: applyInboxSnapshot,
    refreshInbox,
    removeInboxItem,
    busyEnterMode,
    setBusyEnterMode,
    permissionPreset,
    setPermissionPreset,
    planEnforcement,
    setPlanEnforcement,
    experienceTier,
    setExperienceTier,
    reasoningEffort,
    setReasoningEffort,
  };
}
