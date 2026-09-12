import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import {
  acceptPlan,
  cancelChatTask,
  cancelSession,
  patchInteraction,
  postApprovals,
  postAskAnswers,
  postChat,
} from "@/api/endpoints";
import type { ChatStreamApi } from "@/hooks/useChatStream";
import type { ChatTimelineApi } from "@/hooks/useChatTimeline";
import type { useTrajectory } from "@/hooks/useTrajectory";

type TrajectoryApi = ReturnType<typeof useTrajectory>;

const AGENT_MODE_KEY = "nlm_agent_mode";
const AUTO_ACCEPT_KEY = "nlm_auto_accept";
const MULTITASK_KEY = "nlm_multitask";
const SESSION_KEY = "nlm_session_id";

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

  const sessionIdRef = useRef(sessionId);
  const busyRef = useRef(busy);
  sessionIdRef.current = sessionId;
  busyRef.current = busy;

  const syncInteraction = useCallback(async (patch: Record<string, unknown>) => {
    try {
      await patchInteraction(sessionIdRef.current, patch as any);
    } catch {
      /* ignore */
    }
  }, []);

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
      syncInteraction({ auto_accept: !!v });
    },
    [syncInteraction],
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
        } else {
          stream.setActivity("model", "正在调用模型…", modelName || "");
        }
      } catch (err) {
        timeline.appendMessage("assistant", `计划审阅提交失败：${err}`, { rich: false });
      }
    },
    [modelName, setAgentMode, stream, timeline],
  );

  const acceptPlanAction = useCallback(async () => {
    if (busyRef.current) return;
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
      } as any);
      if ((data as any)?.task_id) onTaskId?.((data as any).task_id);
      stream.setStatus("queued");
      stream.setActivity("model", "正在调用模型…", modelName || "");
    } catch (err: any) {
      timeline.dismissLiveAssistant();
      timeline.appendMessage("assistant", String(err?.message || err), { rich: false });
      onBusyChange?.(false);
      stream.setBusy(false);
      stream.setStatus("error");
    }
  }, [
    autoAccept,
    cwd,
    modelName,
    onBusyChange,
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
    async (taskId?: string | null) => {
      try {
        if (taskId) {
          await cancelChatTask(taskId);
        } else {
          await cancelSession(sessionIdRef.current);
        }
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

  const sendChat = useCallback(
    async (contentOverride?: string) => {
      const content = (contentOverride ?? input).trim();
      if (!content || busyRef.current) return;
      stream.ensureSSE();
      const draft = content;
      setInput("");
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
          model_provider: providerId || undefined,
          model_name: modelName || undefined,
          workspace_id: workspaceId || undefined,
          cwd: cwd || undefined,
          workspace_kind: workspaceKind || undefined,
          ssh_host_id: sshHostId || undefined,
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
        timeline.dismissLiveAssistant();
        timeline.appendMessage("assistant", String(err?.message || err), { rich: false });
        trajectory.addError(String(err?.message || err));
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
  };
}
