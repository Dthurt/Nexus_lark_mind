import { useCallback, useEffect, useRef } from "react";
import { openChatStream } from "@/api/endpoints";
import type { ChatTimelineApi } from "@/hooks/useChatTimeline";
import type { useTrajectory } from "@/hooks/useTrajectory";

type TrajectoryApi = ReturnType<typeof useTrajectory>;

export type UseChatStreamOpts = {
  sessionId: string;
  timeline: Pick<
    ChatTimelineApi,
    | "clearRetry"
    | "showRetry"
    | "pushActivity"
    | "renderToolCall"
    | "renderToolResult"
    | "renderApproval"
    | "renderAskUser"
    | "renderPlanReview"
    | "renderTodos"
    | "renderSubagentEvent"
    | "appendDelta"
    | "appendReasoning"
    | "hasRunningTools"
    | "finalizeBot"
    | "dismissLiveAssistant"
    | "appendMessage"
    | "setBotActivity"
    | "markPlanReady"
    | "clearPlanReadyFlags"
    | "beginAssistantTurn"
  >;
  trajectory: Pick<
    TrajectoryApi,
    | "startTurn"
    | "addStatus"
    | "addToolCall"
    | "addToolResult"
    | "addAssistant"
    | "addReasoning"
    | "addSubagent"
    | "addError"
    | "addUser"
    | "endTurn"
  >;
  modelName?: string;
  modelProvider?: string;
  agentMode?: string;
  onBusyChange?: (busy: boolean) => void;
  onStatusChange?: (status: string) => void;
  onTaskId?: (taskId: string | null) => void;
  onUsage?: (usage: any) => void;
  onCompleted?: () => void;
  onModeChange?: (mode: string) => void;
  onSyncInteraction?: (patch: Record<string, unknown>) => void;
  onInbox?: (items: any[]) => void;
  onFileMutation?: (payload: any, args: Record<string, any>) => void;
};

function shortToolName(name: string) {
  const raw = String(name || "tool");
  return raw
    .replace(/^builtin_workspace_/, "")
    .replace(/^builtin_subagent_/, "")
    .replace(/^cli_/, "")
    .split(".")
    .pop();
}

/**
 * SSE EventSource for `/api/chat/stream`.
 * Handles all task.* event types from WorkbenchView.
 */
export function useChatStream(opts: UseChatStreamOpts) {
  const {
    sessionId,
    timeline,
    trajectory,
    modelName = "",
    modelProvider = "",
    agentMode = "agent",
    onBusyChange,
    onStatusChange,
    onTaskId,
    onUsage,
    onCompleted,
    onModeChange,
    onSyncInteraction,
    onInbox,
    onFileMutation,
  } = opts;

  const esRef = useRef<EventSource | null>(null);
  const turnOpenRef = useRef(false);
  const lastEventIdRef = useRef("");
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionIdRef = useRef(sessionId);
  const agentModeRef = useRef(agentMode);
  const modelNameRef = useRef(modelName);
  const modelProviderRef = useRef(modelProvider);
  const timelineRef = useRef(timeline);
  const trajectoryRef = useRef(trajectory);
  const cbsRef = useRef({
    onBusyChange,
    onStatusChange,
    onTaskId,
    onUsage,
    onCompleted,
    onModeChange,
    onSyncInteraction,
    onInbox,
    onFileMutation,
  });

  sessionIdRef.current = sessionId;
  agentModeRef.current = agentMode;
  modelNameRef.current = modelName;
  modelProviderRef.current = modelProvider;
  timelineRef.current = timeline;
  trajectoryRef.current = trajectory;
  cbsRef.current = {
    onBusyChange,
    onStatusChange,
    onTaskId,
    onUsage,
    onCompleted,
    onModeChange,
    onSyncInteraction,
    onInbox,
    onFileMutation,
  };

  const setBusy = useCallback((b: boolean) => {
    cbsRef.current.onBusyChange?.(b);
  }, []);

  const setStatus = useCallback((s: string) => {
    cbsRef.current.onStatusChange?.(s);
  }, []);

  const setActivity = useCallback((phase: string, label: string, detail = "") => {
    timelineRef.current.setBotActivity(phase, label, detail);
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const handleMessage = useCallback((ev: MessageEvent) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.event_id) {
        lastEventIdRef.current = String(data.event_id);
      }
      const type = data.event_type;
      const payload = data.payload || {};
      const tl = timelineRef.current;
      const tr = trajectoryRef.current;
      const cbs = cbsRef.current;

      if (data.task_id) cbs.onTaskId?.(data.task_id);

      if (type === "task.started") {
        tl.clearRetry();
        if (!turnOpenRef.current) {
          tr.startTurn();
          turnOpenRef.current = true;
        }
        tl.beginAssistantTurn?.({
          phase: "model",
          label: "正在调用模型…",
          detail: modelNameRef.current || "",
          startedAt: Date.now(),
        });
        setBusy(true);
        setStatus("thinking…");
        setActivity("model", "正在调用模型…", modelNameRef.current || "");
      } else if (type === "task.inbox") {
        if (Array.isArray(payload.items)) {
          cbs.onInbox?.(payload.items);
        }
        const claimed = payload.items_claimed;
        if (Array.isArray(claimed)) {
          for (const item of claimed) {
            if (!item || item.kind !== "steer") continue;
            const text = String(item.content || "").trim();
            if (!text) continue;
            // Queue items already appear when the user enqueued them.
            tl.appendMessage("user", `〔引导〕 ${text}`, { rich: false });
            tr.addUser?.(text);
          }
        }
      } else if (type === "task.status") {
        const msg = payload.message || "处理中…";
        tl.showRetry(msg);
        if (payload.kind === "compaction" || payload.compaction) {
          const via = payload.compaction?.via || "";
          tr.addStatus(via ? `compaction (${via}): ${msg}` : `compaction: ${msg}`);
        } else {
          tr.addStatus(msg);
        }
        setActivity("retry", msg);
      } else if (type === "task.tool_call") {
        tl.clearRetry();
        const actId = tl.pushActivity("CALL", payload);
        tl.renderToolCall(payload, actId);
        tr.addToolCall(payload, actId);
        const tname = shortToolName(payload.name);
        setStatus("tool call…");
        if (["subagent", "subagent_fork", "send_message"].includes(tname || "")) {
          setActivity(
            "subagent",
            "正在启动子 agent…",
            payload.arguments?.description || tname || "",
          );
        } else {
          setActivity("tool", "正在调用工具…", tname || "");
        }
      } else if (type === "task.tool_result") {
        const actId = tl.pushActivity("RESULT", payload);
        const toolItem = tl.renderToolResult(payload, actId);
        tr.addToolResult(payload, actId);
        setStatus("tool result…");
        try {
          const args =
            (toolItem && typeof toolItem === "object" && (toolItem as any).arguments) || {};
          cbs.onFileMutation?.(payload, args);
        } catch {
          /* ignore */
        }
        // Keep tool/subagent activity while siblings are still running.
        if (typeof tl.hasRunningTools === "function" && tl.hasRunningTools()) {
          setActivity("tool", "工具运行中…", shortToolName(payload.name) || "");
        } else {
          setActivity("model", "正在调用模型…", modelNameRef.current || "");
        }
      } else if (type === "task.reasoning") {
        tl.clearRetry();
        const reasoningChunk = payload.delta || payload.reasoning || "";
        tl.appendReasoning?.(reasoningChunk);
        tr.addReasoning?.(reasoningChunk);
        setStatus("thinking…");
        setActivity("model", "思考中…", modelNameRef.current || "");
      } else if (type === "task.tool_approval") {
        tl.clearRetry();
        const actId = tl.pushActivity("APPROVE", payload);
        tl.renderApproval(payload, actId);
        tr.addStatus(`approval ${payload.name || payload.base || ""}`);
        setStatus("waiting approval…");
        setActivity("tool", "等待你批准工具…", payload.name || payload.base || "");
      } else if (type === "task.ask_user") {
        tl.clearRetry();
        const actId = tl.pushActivity("ASK", payload);
        tl.renderAskUser(payload, actId);
        tr.addStatus("ask_user");
        setStatus("waiting ask…");
        setActivity("tool", "等待你回答…", payload.title || "");
      } else if (type === "task.plan_review") {
        tl.clearRetry();
        const actId = tl.pushActivity("PLAN", payload);
        tl.renderPlanReview(payload, actId);
        tr.addStatus("plan_review");
        setStatus("waiting plan review…");
        setActivity("tool", "等待审阅计划…", "");
      } else if (type === "task.plan_mode") {
        if (payload.active === false) {
          cbs.onModeChange?.("agent");
          try {
            localStorage.setItem("nlm_agent_mode", "agent");
          } catch {
            /* ignore */
          }
          cbs.onSyncInteraction?.({ agent_mode: "agent", plan_status: "accepted" });
          tl.clearPlanReadyFlags();
          setActivity("model", "计划已批准，开始执行…", "");
        }
      } else if (type === "task.todos") {
        tl.clearRetry();
        const actId = tl.pushActivity("TODOS", payload);
        tl.renderTodos(payload, actId);
        tr.addStatus("todos");
        setStatus("todos…");
      } else if (type === "task.canvas_open") {
        tl.clearRetry();
        const body = String(payload.body || "").trim();
        if (body) {
          window.dispatchEvent(
            new CustomEvent("nlm-canvas-open", {
              detail: {
                kind: payload.kind || "markdown",
                title: payload.title || "Canvas",
                body,
                dedupeKey: payload.dedupeKey || payload.path || "",
                source: payload.path || "",
              },
            }),
          );
        }
        tr.addStatus(`canvas ${payload.kind || "open"}`);
        setStatus("canvas…");
        setActivity("tool", "已打开 Canvas", String(payload.title || payload.kind || ""));
      } else if (type === "task.plan_ready") {
        tl.markPlanReady(payload.content || "");
        setActivity("model", "计划已就绪，可接受并执行", "");
      } else if (type === "task.subagent") {
        tl.clearRetry();
        const actId = tl.pushActivity("SUB", payload);
        tl.renderSubagentEvent(payload, actId);
        const subLabel = payload.label || payload.subagent_id || "";
        tr.addSubagent?.(payload, actId);
        setStatus("subagent…");
        if (payload.phase === "start") {
          setActivity("subagent", "子 agent 运行中…", subLabel);
        } else if (payload.phase === "delta") {
          setActivity("subagent", "子 agent 输出中…", subLabel);
        } else if (payload.phase === "tool_call") {
          setActivity(
            "subagent",
            "子 agent 调用工具…",
            shortToolName(payload.tool_call?.name || payload.name) || subLabel,
          );
        } else if (payload.phase === "tool_result") {
          setActivity("subagent", "子 agent 运行中…", subLabel);
        } else if (payload.phase === "end") {
          setActivity("model", "正在调用模型…", modelNameRef.current || "");
        }
      } else if (type === "task.delta") {
        tl.clearRetry();
        if (payload.reasoning_delta) {
          tl.appendReasoning?.(payload.reasoning_delta);
          tr.addReasoning?.(payload.reasoning_delta);
        }
        if (payload.delta) {
          tl.appendDelta(payload.delta || "");
          setStatus("正在生成…");
          setActivity("stream", "正在生成回复…");
        } else if (payload.reasoning_delta) {
          setStatus("思考中…");
          setActivity("model", "思考中…", modelNameRef.current || "");
        }
      } else if (type === "task.completed") {
        tl.clearRetry();
        tl.finalizeBot(payload.content || undefined, payload.usage, {
          modelName: payload.model_name || modelNameRef.current || "",
          modelProvider:
            payload.model_provider || payload.provider || modelProviderRef.current || "",
        });
        if (agentModeRef.current === "plan") tl.markPlanReady(payload.content || "");
        tr.addAssistant(payload.content || "", payload.usage);
        tr.endTurn(payload.session_usage || payload.usage);
        turnOpenRef.current = false;
        if (payload.session_usage) cbs.onUsage?.(payload.session_usage);
        cbs.onTaskId?.(null);
        setStatus("就绪");
        setBusy(false);
        cbs.onCompleted?.();
      } else if (type === "task.failed") {
        tl.clearRetry();
        const err = payload.error || "unknown";
        if (payload.cancelled) {
          if (payload.partial) {
            tl.finalizeBot(payload.partial, undefined, {
              modelName: modelNameRef.current || "",
              modelProvider: modelProviderRef.current || "",
            });
            tr.addAssistant(payload.partial);
          } else {
            tl.dismissLiveAssistant();
          }
          tl.appendMessage("assistant", "已停止生成。", { rich: false });
          tr.addError("已停止生成");
          setStatus("stopped");
        } else {
          tl.dismissLiveAssistant();
          tl.appendMessage(
            "assistant",
            err.includes("限流") || err.includes("429") ? `⚠️ ${err}` : `错误：${err}`,
            { rich: false },
          );
          tr.addError(err);
          setStatus("error");
        }
        tr.endTurn();
        turnOpenRef.current = false;
        cbs.onTaskId?.(null);
        setBusy(false);
      }
    } catch {
      /* ignore */
    }
  }, [setActivity, setBusy, setStatus]);

  const connect = useCallback(
    (sid?: string, afterEventId?: string) => {
      const id = sid || sessionIdRef.current;
      if (!id) return;
      disconnect();
      const after =
        afterEventId !== undefined
          ? afterEventId
          : lastEventIdRef.current || undefined;
      const es = openChatStream(id, after || undefined);
      esRef.current = es;
      es.onopen = () => setStatus("connected");
      es.onerror = () => {
        setStatus("sse reconnecting…");
        // Native EventSource retries the same URL (without cursor). Close and
        // reconnect with last event_id so the ring buffer can replay gaps.
        const afterId = lastEventIdRef.current;
        if (esRef.current === es) {
          es.close();
          esRef.current = null;
        }
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          if (!sessionIdRef.current) return;
          connect(sessionIdRef.current, afterId);
        }, 1200);
      };
      es.onmessage = handleMessage;
    },
    [disconnect, handleMessage, setStatus],
  );

  const ensureSSE = useCallback(
    (sid?: string) => {
      const es = esRef.current;
      if (es && es.readyState !== EventSource.CLOSED) return;
      connect(sid);
    },
    [connect],
  );

  const reopenForSession = useCallback(
    (sid: string) => {
      disconnect();
      connect(sid);
    },
    [connect, disconnect],
  );

  // Reconnect when sessionId changes
  useEffect(() => {
    if (!sessionId) return;
    lastEventIdRef.current = "";
    disconnect();
    connect(sessionId, "");
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on session change
  }, [sessionId]);

  return {
    connect,
    disconnect,
    ensureSSE,
    reopenForSession,
    turnOpenRef,
    setBusy,
    setStatus,
    setActivity,
  };
}

export type ChatStreamApi = ReturnType<typeof useChatStream>;
