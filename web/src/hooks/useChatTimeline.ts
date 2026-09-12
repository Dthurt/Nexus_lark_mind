import { useCallback, useRef, useState } from "react";
import { pretty } from "@/lib/pretty";

let msgSeq = 0;
function mid() {
  msgSeq += 1;
  return `m-${Date.now()}-${msgSeq}`;
}

export type TimelineItem = {
  id: string;
  kind:
    | "msg"
    | "tool"
    | "tool_group"
    | "approval"
    | "ask"
    | "plan_review"
    | "todos"
    | "subagent"
    | string;
  [key: string]: any;
};

export function useChatTimeline() {
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [liveAssistantId, setLiveAssistantId] = useState<string | null>(null);
  const [retryNote, setRetryNote] = useState("");
  const [activityLog, setActivityLog] = useState<any[]>([]);
  const [highlightActivityId, setHighlightActivityId] = useState<string | null>(null);

  const itemsRef = useRef<TimelineItem[]>([]);
  const streamingIdRef = useRef<string | null>(null);
  const liveAssistantIdRef = useRef<string | null>(null);
  const streamRafRef = useRef<number | null>(null);

  itemsRef.current = items;
  streamingIdRef.current = streamingId;
  liveAssistantIdRef.current = liveAssistantId;

  const commit = useCallback((next: TimelineItem[]) => {
    itemsRef.current = next;
    setItems(next.slice());
  }, []);

  const clear = useCallback(() => {
    commit([]);
    streamingIdRef.current = null;
    liveAssistantIdRef.current = null;
    setStreamingId(null);
    setLiveAssistantId(null);
    setRetryNote("");
  }, [commit]);

  const pushActivity = useCallback((kind: string, payload: any) => {
    const id = `act-${Date.now()}-${activityLog.length}`;
    setActivityLog((prev) =>
      [
        {
          id,
          kind,
          name: payload.name || payload.id || "tool",
          detail: payload.arguments || payload.result || payload.error || payload,
          callId: payload.id || null,
          at: Date.now(),
        },
        ...prev,
      ].slice(0, 40),
    );
    return id;
  }, [activityLog.length]);

  const clearActivity = useCallback(() => {
    setActivityLog([]);
    setHighlightActivityId(null);
  }, []);

  const inspectActivity = useCallback((activityId: string) => {
    setHighlightActivityId(activityId);
  }, []);

  const appendMessage = useCallback(
    (
      role: string,
      content: string,
      { rich = null as boolean | null, usage = null as any, streaming = false } = {},
    ) => {
      const useRich = rich == null ? role === "assistant" : !!rich;
      const item: TimelineItem = {
        id: mid(),
        kind: "msg",
        role,
        content: content || "",
        rich: useRich,
        usage,
        streaming,
        retryNote: "",
        activity: null,
        live: false,
      };
      const next = [...itemsRef.current, item];
      commit(next);
      if (streaming) {
        streamingIdRef.current = item.id;
        setStreamingId(item.id);
        if (role === "assistant") {
          liveAssistantIdRef.current = item.id;
          setLiveAssistantId(item.id);
        }
      }
      return item;
    },
    [commit],
  );

  const sealLiveAssistant = useCallback(() => {
    const id = liveAssistantIdRef.current;
    if (!id) return;
    const list = itemsRef.current.slice();
    const bot = list.find((x) => x.id === id && x.kind === "msg");
    if (bot) {
      bot.streaming = false;
      bot.live = false;
      bot.activity = null;
    }
    commit(list);
    liveAssistantIdRef.current = null;
    streamingIdRef.current = null;
    setLiveAssistantId(null);
    setStreamingId(null);
  }, [commit]);

  /** Remove empty live shell, or seal one that already has content. */
  const dismissLiveAssistant = useCallback(() => {
    const id = liveAssistantIdRef.current || streamingIdRef.current;
    if (!id) return;
    const list = itemsRef.current.slice();
    const idx = list.findIndex((x) => x.id === id && x.kind === "msg");
    if (idx < 0) {
      liveAssistantIdRef.current = null;
      streamingIdRef.current = null;
      setLiveAssistantId(null);
      setStreamingId(null);
      return;
    }
    const bot = list[idx];
    if (!(bot.content || "").trim()) {
      list.splice(idx, 1);
    } else {
      bot.streaming = false;
      bot.live = false;
      bot.activity = null;
    }
    commit(list);
    liveAssistantIdRef.current = null;
    streamingIdRef.current = null;
    setLiveAssistantId(null);
    setStreamingId(null);
  }, [commit]);

  /** Keep the live assistant shell at the end of the timeline (below tools). */
  const ensureLiveAssistantAtEnd = useCallback(() => {
    const list = itemsRef.current.slice();
    let bot = liveAssistantIdRef.current
      ? list.find((x) => x.id === liveAssistantIdRef.current && x.kind === "msg")
      : null;
    if (bot) {
      const idx = list.findIndex((x) => x.id === bot!.id);
      if (idx >= 0 && idx !== list.length - 1) {
        list.splice(idx, 1);
        list.push(bot);
      }
    } else {
      bot = {
        id: mid(),
        kind: "msg",
        role: "assistant",
        content: "",
        rich: true,
        usage: null,
        streaming: true,
        retryNote: "",
        activity: null,
        live: true,
      };
      list.push(bot);
    }
    bot.streaming = true;
    bot.live = true;
    streamingIdRef.current = bot.id;
    liveAssistantIdRef.current = bot.id;
    setStreamingId(bot.id);
    setLiveAssistantId(bot.id);
    commit(list);
    return bot;
  }, [commit]);

  const beginAssistantTurn = useCallback(
    (activity: any = null) => {
      dismissLiveAssistant();
      const bot = appendMessage("assistant", "", { rich: true, streaming: true });
      bot.live = true;
      bot.startedAt = Date.now();
      bot.activity = {
        phase: activity?.phase || "model",
        label: activity?.label || "正在调用模型…",
        detail: activity?.detail || "",
        startedAt: activity?.startedAt || bot.startedAt,
      };
      liveAssistantIdRef.current = bot.id;
      setLiveAssistantId(bot.id);
      commit([...itemsRef.current]);
      return bot;
    },
    [appendMessage, commit, dismissLiveAssistant],
  );

  const setBotActivity = useCallback(
    (phase: string, label: string, detail = "") => {
      if (phase === "tool" || phase === "subagent" || phase === "model" || phase === "retry") {
        for (const item of itemsRef.current) {
          if (
            item.kind === "msg" &&
            item.role === "assistant" &&
            item.id !== liveAssistantIdRef.current
          ) {
            item.streaming = false;
          }
        }
      }
      const bot = ensureLiveAssistantAtEnd();
      const samePhase = bot.activity?.phase === phase;
      const startedAt =
        samePhase && bot.activity?.startedAt ? bot.activity.startedAt : Date.now();
      bot.activity = { phase, label, detail: detail || "", startedAt };
      bot.streaming = true;
      bot.live = true;
      commit([...itemsRef.current]);
      return bot;
    },
    [commit, ensureLiveAssistantAtEnd],
  );

  const clearBotActivity = useCallback(() => {
    const bot = itemsRef.current.find((x) => x.id === liveAssistantIdRef.current);
    if (bot) {
      bot.activity = null;
      commit([...itemsRef.current]);
    }
  }, [commit]);

  const ensureBotBubble = useCallback(() => {
    if (streamingIdRef.current) {
      const cur = itemsRef.current.find((x) => x.id === streamingIdRef.current);
      if (cur) return cur;
    }
    if (liveAssistantIdRef.current) {
      const live = itemsRef.current.find((x) => x.id === liveAssistantIdRef.current);
      if (live) {
        streamingIdRef.current = live.id;
        setStreamingId(live.id);
        live.streaming = true;
        return live;
      }
    }
    return ensureLiveAssistantAtEnd();
  }, [ensureLiveAssistantAtEnd]);

  const appendDelta = useCallback(
    (delta: string) => {
      const bot = ensureBotBubble();
      bot.content = (bot.content || "") + (delta || "");
      bot.streaming = true;
      bot.live = true;
      if (!bot.activity || bot.activity.phase === "model") {
        bot.activity = {
          phase: "stream",
          label: bot.activity?.label || "正在生成回复…",
          detail: bot.activity?.detail || "",
          startedAt: bot.activity?.startedAt || Date.now(),
        };
      }
      // Coalesce React commits to one paint per frame while tokens arrive.
      if (streamRafRef.current == null) {
        streamRafRef.current = requestAnimationFrame(() => {
          streamRafRef.current = null;
          commit([...itemsRef.current]);
        });
      }
    },
    [commit, ensureBotBubble],
  );

  const appendReasoning = useCallback(
    (delta: string) => {
      if (!delta) return;
      const bot = ensureBotBubble();
      bot.reasoning = (bot.reasoning || "") + delta;
      bot.streaming = true;
      bot.live = true;
      if (!bot.activity || bot.activity.phase === "stream") {
        bot.activity = {
          phase: "model",
          label: "思考中…",
          detail: bot.activity?.detail || "",
          startedAt: bot.activity?.startedAt || Date.now(),
        };
      }
      if (streamRafRef.current == null) {
        streamRafRef.current = requestAnimationFrame(() => {
          streamRafRef.current = null;
          commit([...itemsRef.current]);
        });
      }
    },
    [commit, ensureBotBubble],
  );

  const hasRunningTools = useCallback(() => {
    return itemsRef.current.some((it) => {
      if (it.kind !== "tool" && it.kind !== "subagent") return false;
      const s = String(it.status || "").toLowerCase();
      if (it.error != null || it.success === false) return false;
      if (s === "ok" || s === "done" || s === "fail" || s === "failed" || s === "stopped") return false;
      if (it.kind === "tool" && it.result != null && s !== "running") return false;
      if (it.kind === "subagent" && (it.output || it.error) && s !== "running") return false;
      return s === "running" || s === "" || s == null;
    });
  }, []);

  const finalizeBot = useCallback(
    (text?: string, usage?: any, meta?: { modelName?: string; modelProvider?: string }) => {
      const bot = ensureBotBubble();
      if (text != null && text !== "") bot.content = text;
      bot.streaming = false;
      bot.live = false;
      const started = bot.startedAt || bot.activity?.startedAt || null;
      const clientMs = started ? Math.max(0, Date.now() - started) : null;
      bot.activity = null;
      if (meta?.modelName) bot.modelName = meta.modelName;
      if (meta?.modelProvider) bot.modelProvider = meta.modelProvider;
      const merged = { ...(usage || bot.usage || {}) };
      if (merged.duration_ms == null && clientMs != null) merged.duration_ms = clientMs;

      const list = itemsRef.current.slice();
      if (!(bot.content || "").trim()) {
        const idx = list.findIndex((x) => x.id === bot.id);
        if (idx >= 0) list.splice(idx, 1);
        const prev = [...list]
          .reverse()
          .find((x) => x.kind === "msg" && x.role === "assistant" && (x.content || "").trim());
        if (prev && Object.keys(merged).length) {
          prev.usage = { ...(prev.usage || {}), ...merged };
          if (meta?.modelName) prev.modelName = meta.modelName;
          if (meta?.modelProvider) prev.modelProvider = meta.modelProvider;
        }
        commit(list);
      } else {
        bot.usage = Object.keys(merged).length ? merged : null;
        commit(list);
      }

      streamingIdRef.current = null;
      liveAssistantIdRef.current = null;
      setStreamingId(null);
      setLiveAssistantId(null);
      setRetryNote("");
      if (streamRafRef.current != null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }
    },
    [commit, ensureBotBubble],
  );

  const showRetry = useCallback(
    (message?: string) => {
      const label = message || "模型限流，正在自动重试…";
      setRetryNote(label);
      setBotActivity("retry", label);
    },
    [setBotActivity],
  );

  const clearRetry = useCallback(() => {
    setRetryNote("");
    for (const item of itemsRef.current) {
      if (item.kind === "msg") {
        item.retryNote = "";
        if (item.activity?.phase === "retry") {
          item.activity = null;
        }
      }
    }
    commit([...itemsRef.current]);
  }, [commit]);

  const afterToolOrSubagentInserted = useCallback(() => {
    const live = liveAssistantIdRef.current
      ? itemsRef.current.find((x) => x.id === liveAssistantIdRef.current && x.kind === "msg")
      : null;
    if (live && (live.content || "").trim()) {
      sealLiveAssistant();
    }
    ensureLiveAssistantAtEnd();
  }, [ensureLiveAssistantAtEnd, sealLiveAssistant]);

  const sealLiveAssistantBeforeTools = useCallback(() => {
    afterToolOrSubagentInserted();
  }, [afterToolOrSubagentInserted]);

  const renderToolCall = useCallback(
    (payload: any, activityId: string | null = null) => {
      const id = payload.id || payload.name || mid();
      const short =
        String(payload.name || "")
          .split(".")
          .pop() || "";
      if (short === "ask_user" || payload.kind === "ask_user") return null;
      if (short === "todo_write" || payload.kind === "todo") return null;
      if (short === "exit_plan_mode" || payload.kind === "plan_review") return null;

      const isSub =
        payload.kind === "subagent" ||
        ["subagent", "subagent_fork", "send_message"].includes(short);

      const list = itemsRef.current.slice();

      if (isSub) {
        const existing = list.find((x) => x.kind === "subagent" && x.callId === id);
        if (existing) {
          existing.open = false;
          existing.prompt =
            payload.arguments?.prompt || payload.arguments?.message || existing.prompt;
          existing.label = payload.arguments?.description || existing.label;
          existing.mode = payload.subagent_mode || existing.mode;
          if (activityId) existing.activityId = activityId;
          existing.status = "running";
          commit(list);
          afterToolOrSubagentInserted();
          return existing;
        }
        const item: TimelineItem = {
          id: mid(),
          kind: "subagent",
          callId: id,
          subagentId: "",
          name: payload.name || "subagent",
          label: payload.arguments?.description || payload.name || "subagent",
          mode: payload.subagent_mode || "spawn",
          prompt: payload.arguments?.prompt || payload.arguments?.message || "",
          streamText: "",
          output: "",
          error: null,
          status: "running",
          open: false,
          childTools: [],
          activityId,
        };
        list.push(item);
        commit(list);
        afterToolOrSubagentInserted();
        return item;
      }

      const existing = list.find((x) => x.kind === "tool" && x.callId === id);
      if (existing) {
        existing.open = false;
        // Keep Running until tool_result arrives — never flip early on arg patches.
        existing.status = "running";
        existing.error = null;
        existing.success = null;
        if (existing.result == null) existing.result = null;
        existing.arguments = payload.arguments ?? payload.raw_arguments ?? existing.arguments;
        if (activityId) existing.activityId = activityId;
        existing.openaiName = payload.openai_name || payload.name || existing.openaiName;
        commit(list);
        afterToolOrSubagentInserted();
        return existing;
      }
      const item: TimelineItem = {
        id: mid(),
        kind: "tool",
        callId: id,
        name: payload.name || "tool",
        openaiName: payload.openai_name || payload.name || null,
        badge: "CALL",
        open: false,
        status: "running",
        arguments: payload.arguments ?? payload.raw_arguments,
        result: null,
        error: null,
        durationMs: null,
        success: null,
        activityId,
      };
      list.push(item);
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit],
  );

  const renderToolResult = useCallback(
    (payload: any, activityId: string | null = null) => {
      const short =
        String(payload.name || "")
          .split(".")
          .pop() || "";
      if (short === "todo_write" || payload.kind === "todo") return null;

      const isSub =
        payload.kind === "subagent" ||
        (payload.result && payload.result.subagent_id) ||
        ["subagent", "subagent_fork", "send_message"].includes(
          String(payload.name || "").split(".").pop() || "",
        );

      const list = itemsRef.current.slice();

      if (isSub) {
        let item = list.find((x) => x.kind === "subagent" && x.callId === payload.id);
        if (!item) {
          item = {
            id: mid(),
            kind: "subagent",
            callId: payload.id || mid(),
            subagentId: payload.result?.subagent_id || "",
            name: payload.name || "subagent",
            label: payload.result?.label || payload.name || "subagent",
            mode: payload.result?.mode || "spawn",
            prompt: "",
            streamText: "",
            output: "",
            error: null,
            status: "idle",
            open: false,
            childTools: [],
            activityId,
          };
          list.push(item);
        }
        item.success = payload.success !== false;
        item.status = payload.success === false ? "failed" : payload.result?.status || "idle";
        item.durationMs = payload.duration_ms ?? null;
        if (activityId) item.activityId = activityId;
        if (payload.result?.subagent_id) item.subagentId = payload.result.subagent_id;
        if (payload.success === false) {
          item.error = payload.error;
          item.open = true;
        } else {
          item.output = payload.result?.output || payload.result?.render || "";
          if (item.output && !item.streamText) item.streamText = item.output;
          item.open = false;
        }
        commit(list);
        afterToolOrSubagentInserted();
        return item;
      }

      let item = list.find((x) => x.kind === "tool" && x.callId === payload.id);
      if (!item) {
        item = {
          id: mid(),
          kind: "tool",
          callId: payload.id || mid(),
          name: payload.name || "tool",
          openaiName: payload.openai_name || payload.name || null,
          badge: "RESULT",
          open: false,
          status: "",
          arguments: null,
          result: null,
          error: null,
          durationMs: null,
          success: null,
          activityId,
        };
        list.push(item);
      }
      item.success = payload.success !== false;
      item.status = item.success ? "ok" : "fail";
      item.durationMs = payload.duration_ms ?? null;
      if (activityId) item.activityId = activityId;
      if (payload.success === false) {
        item.error = payload.error;
        item.open = true;
      } else {
        item.result = payload.result;
        item.open = false;
      }
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit],
  );

  const renderSubagentEvent = useCallback(
    (payload: any, activityId: string | null = null) => {
      const callId = payload.parent_call_id;
      const list = itemsRef.current.slice();
      let item = list.find((x) => x.kind === "subagent" && x.callId === callId);
      if (!item) {
        item = {
          id: mid(),
          kind: "subagent",
          callId: callId || mid(),
          subagentId: payload.subagent_id || "",
          name: "subagent",
          label: payload.label || "subagent",
          mode: payload.mode || "spawn",
          prompt: payload.prompt || "",
          streamText: "",
          output: "",
          error: null,
          status: "running",
          open: false,
          childTools: [],
          activityId,
        };
        list.push(item);
      }
      if (payload.subagent_id) item.subagentId = payload.subagent_id;
      if (payload.label) item.label = payload.label;
      if (payload.mode) item.mode = payload.mode;
      if (activityId) item.activityId = activityId;

      const phase = payload.phase;
      if (phase === "start") {
        item.status = "running";
        item.prompt = payload.prompt || item.prompt;
        item.open = false;
      } else if (phase === "delta") {
        item.streamText = (item.streamText || "") + (payload.delta || "");
        item.status = "running";
      } else if (phase === "tool_call") {
        const tc = payload.tool_call || {};
        const existing = (item.childTools || []).find((t: any) => t.id === tc.id);
        if (!existing) {
          item.childTools = [
            ...(item.childTools || []),
            { id: tc.id, name: tc.name, arguments: tc.arguments, success: null, status: "" },
          ];
        }
      } else if (phase === "tool_result") {
        const tr = payload.tool_result || {};
        const row = (item.childTools || []).find((t: any) => t.id === tr.id);
        if (row) {
          row.success = tr.success !== false;
          row.status = row.success ? "ok" : "fail";
          row.result = tr.result;
          row.error = tr.error;
        } else {
          item.childTools = [
            ...(item.childTools || []),
            {
              id: tr.id,
              name: tr.name,
              success: tr.success !== false,
              status: tr.success === false ? "fail" : "ok",
            },
          ];
        }
      } else if (phase === "end") {
        item.status = payload.status || (payload.error ? "failed" : "idle");
        item.output = payload.output || item.streamText || "";
        if (payload.output) item.streamText = payload.output;
        item.error = payload.error || null;
        item.open = !!payload.error;
        item.durationMs = payload.duration_ms ?? null;
      }
      commit(list);
      if (phase === "start") afterToolOrSubagentInserted();
      else ensureLiveAssistantAtEnd();
      return item;
    },
    [afterToolOrSubagentInserted, commit, ensureLiveAssistantAtEnd],
  );

  const renderApproval = useCallback(
    (payload: any, activityId?: string | null) => {
      sealLiveAssistantBeforeTools();
      const callId = payload?.id || mid();
      const list = itemsRef.current.slice();
      const tool = list.find((x) => x.kind === "tool" && x.callId === callId);
      if (tool) {
        tool.status = "running";
        tool.approvalDecision = null;
      }
      let item = list.find((x) => x.kind === "approval" && x.callId === callId);
      if (!item) {
        item = {
          id: mid(),
          kind: "approval",
          callId,
          name: payload?.name || "tool",
          base: payload?.base || "",
          arguments: payload?.arguments || {},
          status: "pending",
          activityId,
        };
        list.push(item);
      } else {
        item.arguments = payload?.arguments || item.arguments;
        item.name = payload?.name || item.name;
        item.base = payload?.base || item.base;
        if (item.status !== "allowed" && item.status !== "denied") {
          item.status = "pending";
        }
      }
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit, sealLiveAssistantBeforeTools],
  );

  const resolveApprovalLocal = useCallback(
    (callId: string, status: string, action?: string) => {
      const list = itemsRef.current.slice();
      const decision =
        action === "deny" || status === "denied"
          ? "denied"
          : action === "allow_session" || action === "always"
            ? "allow_session"
            : "allowed";

      const tool = list.find((x) => x.kind === "tool" && x.callId === callId);
      if (tool) {
        tool.approvalDecision = decision;
      }

      // Remove the approval card from the chat timeline once resolved.
      const next = list.filter((x) => !(x.kind === "approval" && x.callId === callId));
      commit(next);
    },
    [commit],
  );

  const renderAskUser = useCallback(
    (payload: any, activityId?: string | null) => {
      sealLiveAssistantBeforeTools();
      const callId = payload?.id || mid();
      const list = itemsRef.current.slice();
      let item = list.find((x) => x.kind === "ask" && x.callId === callId);
      if (!item) {
        item = {
          id: mid(),
          kind: "ask",
          callId,
          name: payload?.name || "ask_user",
          title: payload?.title || "需要你的确认",
          questions: payload?.questions || [],
          status: "pending",
          answers: null,
          activityId,
        };
        list.push(item);
      } else if (item.status === "pending") {
        item.title = payload?.title || item.title;
        item.questions = payload?.questions || item.questions;
      }
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit, sealLiveAssistantBeforeTools],
  );

  const resolveAskLocal = useCallback(
    (callId: string, status: string, answers?: any) => {
      const list = itemsRef.current.slice();
      const item = list.find((x) => x.kind === "ask" && x.callId === callId);
      if (item) {
        item.status = status;
        if (answers != null) item.answers = answers;
        commit(list);
      }
    },
    [commit],
  );

  const renderTodos = useCallback(
    (payload: any, activityId: string | null = null) => {
      sealLiveAssistantBeforeTools();
      const rows = Array.isArray(payload?.items) ? payload.items : [];
      const list = itemsRef.current.slice();
      let item: TimelineItem | null = null;
      for (let i = list.length - 1; i >= 0; i -= 1) {
        if (list[i].kind === "todos") {
          item = list[i];
          break;
        }
      }
      if (!item) {
        item = {
          id: mid(),
          kind: "todos",
          callId: payload?.call_id || mid(),
          items: rows,
          activityId,
        };
        list.push(item);
      } else {
        item.items = rows;
        item.callId = payload?.call_id || item.callId;
        if (activityId) item.activityId = activityId;
      }
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit, sealLiveAssistantBeforeTools],
  );

  const renderPlanReview = useCallback(
    (payload: any, activityId: string | null = null) => {
      sealLiveAssistantBeforeTools();
      const callId = payload?.id || mid();
      const list = itemsRef.current.slice();
      let item = list.find((x) => x.kind === "plan_review" && x.callId === callId);
      if (!item) {
        item = {
          id: mid(),
          kind: "plan_review",
          callId,
          name: payload?.name || "exit_plan_mode",
          title: payload?.title || "计划审阅",
          plan: payload?.plan || "",
          status: "pending",
          activityId,
        };
        list.push(item);
      } else if (item.status === "pending") {
        item.plan = payload?.plan || item.plan;
        item.title = payload?.title || item.title;
      }
      commit(list);
      afterToolOrSubagentInserted();
      return item;
    },
    [afterToolOrSubagentInserted, commit, sealLiveAssistantBeforeTools],
  );

  const resolvePlanReviewLocal = useCallback(
    (callId: string, status: string) => {
      const list = itemsRef.current.slice();
      const item = list.find((x) => x.kind === "plan_review" && x.callId === callId);
      if (item) {
        item.status = status;
        commit(list);
      }
    },
    [commit],
  );

  const markPlanReady = useCallback(
    (content?: string) => {
      const list = itemsRef.current.slice();
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const it = list[i];
        if (it.kind === "msg" && it.role === "assistant") {
          it.planReady = true;
          if (content && !(it.content || "").trim()) it.content = content;
          commit(list);
          return it;
        }
      }
      const msg = appendMessage("assistant", content || "", { rich: true });
      msg.planReady = true;
      commit([...itemsRef.current]);
      return msg;
    },
    [appendMessage, commit],
  );

  const clearPlanReadyFlags = useCallback(() => {
    const list = itemsRef.current.slice();
    for (const it of list) {
      if (it.kind === "msg") it.planReady = false;
    }
    commit(list);
  }, [commit]);

  const appendFileCard = useCallback(
    (file: {
      name: string;
      path?: string;
      content?: string;
      mime?: string;
      url?: string;
      size?: number;
    }) => {
      const item: TimelineItem = {
        id: mid(),
        kind: "file",
        name: file.name || "file",
        path: file.path || "",
        content: file.content ?? "",
        mime: file.mime || "",
        url: file.url || "",
        size: file.size,
        viewMode: "link",
      };
      const list = itemsRef.current.slice();
      list.push(item);
      commit(list);
      return item;
    },
    [commit],
  );

  const markRunningToolsStopped = useCallback(() => {
    const list = itemsRef.current.slice();
    let changed = false;
    for (const it of list) {
      if (it.kind === "tool" && (it.status === "running" || it.status === "" || it.status == null)) {
        if (it.result == null && it.error == null && it.success == null) {
          it.status = "stopped";
          changed = true;
        }
      }
      if (it.kind === "subagent" && it.status === "running") {
        it.status = "stopped";
        changed = true;
      }
    }
    if (changed) commit(list);
  }, [commit]);

  const loadFromHistory = useCallback(
    (messages: any[]) => {
      clear();
      for (const m of messages || []) {
        const role = m.role || "assistant";
        const meta = m.metadata || {};
        if (meta.kind === "file" || meta.file) {
          const file = meta.file || meta;
          appendFileCard({
            name: file.name || file.filename || "file",
            path: file.path || "",
            content: file.content ?? m.content ?? "",
            mime: file.mime || file.mime_type || "",
            url: file.url || "",
            size: file.size,
          });
          continue;
        }
        if (meta.kind === "tool_call" || (meta.tool_calls && !m.content)) {
          const calls = Array.isArray(meta.tool_calls)
            ? meta.tool_calls
            : meta.tool_call
              ? [meta.tool_call]
              : [];
          for (const tc of calls) {
            if (tc) renderToolCall(tc);
          }
          continue;
        }
        if (role === "tool" || meta.kind === "tool_result" || meta.tool_result) {
          const tr = meta.tool_result || {
            id: m.tool_call_id,
            name: m.name,
            success: true,
            result: m.content,
          };
          renderToolResult(tr);
          continue;
        }
        if (role === "system") continue;
        if (!m.content && role === "assistant") continue;
        appendMessage(role === "user" ? "user" : "assistant", m.content || "", {
          usage: role === "assistant" ? meta.usage : null,
        });
        if (role === "assistant") {
          const last = itemsRef.current[itemsRef.current.length - 1];
          if (last?.kind === "msg") {
            if (meta.model || meta.model_name) last.modelName = meta.model || meta.model_name;
            if (meta.model_provider || meta.provider) {
              last.modelProvider = meta.model_provider || meta.provider;
            }
            if (meta.reasoning) last.reasoning = String(meta.reasoning);
          }
        }
      }
      streamingIdRef.current = null;
      setStreamingId(null);
    },
    [appendFileCard, appendMessage, clear, renderToolCall, renderToolResult],
  );

  const scrollToBottom = useCallback(async (el: HTMLElement | null) => {
    await Promise.resolve();
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  const formatToolDetail = useCallback((v: any) => pretty(v), []);

  return {
    items,
    streamingId,
    liveAssistantId,
    retryNote,
    activityLog,
    highlightActivityId,
    setActivityLog,
    clear,
    clearActivity,
    pushActivity,
    inspectActivity,
    appendMessage,
    appendDelta,
    appendReasoning,
    hasRunningTools,
    finalizeBot,
    beginAssistantTurn,
    setBotActivity,
    clearBotActivity,
    dismissLiveAssistant,
    showRetry,
    clearRetry,
    renderToolCall,
    renderToolResult,
    renderSubagentEvent,
    renderApproval,
    resolveApprovalLocal,
    renderAskUser,
    resolveAskLocal,
    renderTodos,
    renderPlanReview,
    resolvePlanReviewLocal,
    markPlanReady,
    clearPlanReadyFlags,
    appendFileCard,
    markRunningToolsStopped,
    loadFromHistory,
    scrollToBottom,
    formatToolDetail,
  };
}

export type ChatTimelineApi = ReturnType<typeof useChatTimeline>;
