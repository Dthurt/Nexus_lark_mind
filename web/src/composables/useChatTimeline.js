import { nextTick, ref } from "vue";
import { pretty } from "@/utils/pretty";

let msgSeq = 0;
function mid() {
  msgSeq += 1;
  return `m-${Date.now()}-${msgSeq}`;
}

export function useChatTimeline() {
  const items = ref([]);
  const streamingId = ref(null);
  const liveAssistantId = ref(null);
  const retryNote = ref("");
  const activityLog = ref([]);
  const highlightActivityId = ref(null);

  function clear() {
    items.value = [];
    streamingId.value = null;
    liveAssistantId.value = null;
    retryNote.value = "";
  }

  function pushActivity(kind, payload) {
    const id = `act-${Date.now()}-${activityLog.value.length}`;
    activityLog.value = [
      {
        id,
        kind,
        name: payload.name || payload.id || "tool",
        detail: payload.arguments || payload.result || payload.error || payload,
        callId: payload.id || null,
        at: Date.now(),
      },
      ...activityLog.value,
    ].slice(0, 40);
    return id;
  }

  function clearActivity() {
    activityLog.value = [];
    highlightActivityId.value = null;
  }

  function inspectActivity(activityId) {
    highlightActivityId.value = activityId;
  }

  function appendMessage(role, content, { rich = null, usage = null, streaming = false } = {}) {
    const useRich = rich == null ? role === "assistant" : !!rich;
    const item = {
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
    items.value.push(item);
    if (streaming) {
      streamingId.value = item.id;
      if (role === "assistant") liveAssistantId.value = item.id;
    }
    return item;
  }

  function sealLiveAssistant() {
    const id = liveAssistantId.value;
    if (!id) return;
    const bot = items.value.find((x) => x.id === id && x.kind === "msg");
    if (bot) {
      bot.streaming = false;
      bot.live = false;
      bot.activity = null;
    }
    liveAssistantId.value = null;
    streamingId.value = null;
  }

  /** Remove empty live shell, or seal one that already has content. */
  function dismissLiveAssistant() {
    const id = liveAssistantId.value || streamingId.value;
    if (!id) return;
    const idx = items.value.findIndex((x) => x.id === id && x.kind === "msg");
    if (idx < 0) {
      liveAssistantId.value = null;
      streamingId.value = null;
      return;
    }
    const bot = items.value[idx];
    if (!(bot.content || "").trim()) {
      items.value.splice(idx, 1);
    } else {
      bot.streaming = false;
      bot.live = false;
      bot.activity = null;
    }
    liveAssistantId.value = null;
    streamingId.value = null;
  }

  /** Keep the live assistant shell at the end of the timeline (below tools). */
  function ensureLiveAssistantAtEnd() {
    let bot = liveAssistantId.value
      ? items.value.find((x) => x.id === liveAssistantId.value && x.kind === "msg")
      : null;
    if (bot) {
      const idx = items.value.findIndex((x) => x.id === bot.id);
      if (idx >= 0 && idx !== items.value.length - 1) {
        items.value.splice(idx, 1);
        items.value.push(bot);
      }
    } else {
      bot = appendMessage("assistant", "", { rich: true, streaming: true });
    }
    bot.streaming = true;
    bot.live = true;
    streamingId.value = bot.id;
    liveAssistantId.value = bot.id;
    return bot;
  }

  function beginAssistantTurn(activity = null) {
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
    liveAssistantId.value = bot.id;
    return bot;
  }

  function setBotActivity(phase, label, detail = "") {
    // While tools/subagents run, never leave a caret blinking on prior text bubbles.
    if (phase === "tool" || phase === "subagent" || phase === "model" || phase === "retry") {
      for (const item of items.value) {
        if (item.kind === "msg" && item.role === "assistant" && item.id !== liveAssistantId.value) {
          item.streaming = false;
        }
      }
    }
    const bot = ensureLiveAssistantAtEnd();
    const samePhase = bot.activity?.phase === phase;
    const startedAt = samePhase && bot.activity?.startedAt ? bot.activity.startedAt : Date.now();
    bot.activity = { phase, label, detail: detail || "", startedAt };
    bot.streaming = true;
    bot.live = true;
    return bot;
  }

  function clearBotActivity() {
    const bot = items.value.find((x) => x.id === liveAssistantId.value);
    if (bot) bot.activity = null;
  }

  function ensureBotBubble() {
    if (streamingId.value) {
      const cur = items.value.find((x) => x.id === streamingId.value);
      if (cur) return cur;
    }
    if (liveAssistantId.value) {
      const live = items.value.find((x) => x.id === liveAssistantId.value);
      if (live) {
        streamingId.value = live.id;
        live.streaming = true;
        return live;
      }
    }
    return ensureLiveAssistantAtEnd();
  }

  function appendDelta(delta) {
    const bot = ensureBotBubble();
    bot.content = (bot.content || "") + (delta || "");
    bot.streaming = true;
  }

  function finalizeBot(text, usage) {
    const bot = ensureBotBubble();
    if (text != null && text !== "") bot.content = text;
    bot.streaming = false;
    bot.live = false;
    const started = bot.startedAt || bot.activity?.startedAt || null;
    const clientMs = started ? Math.max(0, Date.now() - started) : null;
    bot.activity = null;
    const merged = { ...(usage || bot.usage || {}) };
    if (merged.duration_ms == null && clientMs != null) merged.duration_ms = clientMs;

    // Drop empty live shells left after tool rounds (ghost narrow bubbles).
    if (!(bot.content || "").trim()) {
      const idx = items.value.findIndex((x) => x.id === bot.id);
      if (idx >= 0) items.value.splice(idx, 1);
      const prev = [...items.value]
        .reverse()
        .find((x) => x.kind === "msg" && x.role === "assistant" && (x.content || "").trim());
      if (prev && Object.keys(merged).length) {
        prev.usage = { ...(prev.usage || {}), ...merged };
      }
    } else {
      bot.usage = Object.keys(merged).length ? merged : null;
    }

    streamingId.value = null;
    liveAssistantId.value = null;
    retryNote.value = "";
  }

  function showRetry(message) {
    const label = message || "模型限流，正在自动重试…";
    retryNote.value = label;
    setBotActivity("retry", label);
  }

  function clearRetry() {
    retryNote.value = "";
    for (const item of items.value) {
      if (item.kind === "msg") {
        item.retryNote = "";
        if (item.activity?.phase === "retry") {
          item.activity = null;
        }
      }
    }
  }

  function afterToolOrSubagentInserted() {
    const live = liveAssistantId.value
      ? items.value.find((x) => x.id === liveAssistantId.value && x.kind === "msg")
      : null;
    // Seal text already streamed so it stays above the tool cards.
    if (live && (live.content || "").trim()) {
      sealLiveAssistant();
    }
    ensureLiveAssistantAtEnd();
  }

  function renderToolCall(payload, activityId = null) {
    const id = payload.id || payload.name || mid();
    const short =
      String(payload.name || "")
        .split(".")
        .pop() || "";
    if (short === "ask_user" || payload.kind === "ask_user") {
      // Dedicated AskUserForm arrives via task.ask_user
      return null;
    }
    const isSub =
      payload.kind === "subagent" ||
      ["subagent", "subagent_fork", "send_message"].includes(short);

    if (isSub) {
      const existing = items.value.find((x) => x.kind === "subagent" && x.callId === id);
      if (existing) {
        existing.open = false;
        existing.prompt = payload.arguments?.prompt || payload.arguments?.message || existing.prompt;
        existing.label = payload.arguments?.description || existing.label;
        existing.mode = payload.subagent_mode || existing.mode;
        if (activityId) existing.activityId = activityId;
        existing.status = "running";
        afterToolOrSubagentInserted();
        return existing;
      }
      const item = {
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
      items.value.push(item);
      afterToolOrSubagentInserted();
      return item;
    }

    const existing = items.value.find((x) => x.kind === "tool" && x.callId === id);
    if (existing) {
      existing.open = false;
      existing.arguments = payload.arguments ?? payload.raw_arguments;
      if (activityId) existing.activityId = activityId;
      existing.openaiName = payload.openai_name || payload.name || existing.openaiName;
      afterToolOrSubagentInserted();
      return existing;
    }
    const item = {
      id: mid(),
      kind: "tool",
      callId: id,
      name: payload.name || "tool",
      openaiName: payload.openai_name || payload.name || null,
      badge: "CALL",
      open: false,
      status: "",
      arguments: payload.arguments ?? payload.raw_arguments,
      result: null,
      error: null,
      durationMs: null,
      success: null,
      activityId,
    };
    items.value.push(item);
    afterToolOrSubagentInserted();
    return item;
  }

  function renderToolResult(payload, activityId = null) {
    const isSub =
      payload.kind === "subagent" ||
      (payload.result && payload.result.subagent_id) ||
      ["subagent", "subagent_fork", "send_message"].includes(String(payload.name || "").split(".").pop());

    if (isSub) {
      let item = items.value.find((x) => x.kind === "subagent" && x.callId === payload.id);
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
        items.value.push(item);
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
      afterToolOrSubagentInserted();
      return item;
    }

    let item = items.value.find((x) => x.kind === "tool" && x.callId === payload.id);
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
      items.value.push(item);
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
    afterToolOrSubagentInserted();
    return item;
  }

  function renderSubagentEvent(payload, activityId = null) {
    const callId = payload.parent_call_id;
    let item = items.value.find((x) => x.kind === "subagent" && x.callId === callId);
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
      items.value.push(item);
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
      const existing = (item.childTools || []).find((t) => t.id === tc.id);
      if (!existing) {
        item.childTools = [
          ...(item.childTools || []),
          { id: tc.id, name: tc.name, arguments: tc.arguments, success: null, status: "" },
        ];
      }
    } else if (phase === "tool_result") {
      const tr = payload.tool_result || {};
      const row = (item.childTools || []).find((t) => t.id === tr.id);
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
    if (phase === "start") afterToolOrSubagentInserted();
    else ensureLiveAssistantAtEnd();
    return item;
  }

  function renderApproval(payload, activityId) {
    sealLiveAssistantBeforeTools();
    const callId = payload?.id || mid();
    let item = items.value.find((x) => x.kind === "approval" && x.callId === callId);
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
      items.value.push(item);
    } else {
      item.arguments = payload?.arguments || item.arguments;
      item.name = payload?.name || item.name;
      item.base = payload?.base || item.base;
      if (item.status !== "allowed" && item.status !== "denied") item.status = "pending";
    }
    afterToolOrSubagentInserted();
    return item;
  }

  function resolveApprovalLocal(callId, status) {
    const item = items.value.find((x) => x.kind === "approval" && x.callId === callId);
    if (item) item.status = status;
  }

  function renderAskUser(payload, activityId) {
    sealLiveAssistantBeforeTools();
    const callId = payload?.id || mid();
    let item = items.value.find((x) => x.kind === "ask" && x.callId === callId);
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
      items.value.push(item);
    } else if (item.status === "pending") {
      item.title = payload?.title || item.title;
      item.questions = payload?.questions || item.questions;
    }
    afterToolOrSubagentInserted();
    return item;
  }

  function resolveAskLocal(callId, status, answers) {
    const item = items.value.find((x) => x.kind === "ask" && x.callId === callId);
    if (item) {
      item.status = status;
      if (answers != null) item.answers = answers;
    }
  }

  function markPlanReady(content) {
    // Mark the latest assistant message (or live) as offering accept-plan.
    for (let i = items.value.length - 1; i >= 0; i -= 1) {
      const it = items.value[i];
      if (it.kind === "msg" && it.role === "assistant") {
        it.planReady = true;
        if (content && !(it.content || "").trim()) it.content = content;
        return it;
      }
    }
    const msg = appendMessage("assistant", content || "", { rich: true });
    msg.planReady = true;
    return msg;
  }

  function clearPlanReadyFlags() {
    for (const it of items.value) {
      if (it.kind === "msg") it.planReady = false;
    }
  }

  function loadFromHistory(messages) {
    clear();
    for (const m of messages || []) {
      const role = m.role || "assistant";
      const meta = m.metadata || {};
      if (meta.kind === "tool_call" || (meta.tool_calls && !m.content)) {
        const tc = (meta.tool_calls && meta.tool_calls[0]) || meta.tool_call || {};
        renderToolCall(tc);
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
    }
    streamingId.value = null;
  }

  async function scrollToBottom(el) {
    await nextTick();
    if (el) el.scrollTop = el.scrollHeight;
  }

  function formatToolDetail(v) {
    return pretty(v);
  }

  return {
    items,
    streamingId,
    liveAssistantId,
    retryNote,
    activityLog,
    highlightActivityId,
    clear,
    clearActivity,
    pushActivity,
    inspectActivity,
    appendMessage,
    appendDelta,
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
    markPlanReady,
    clearPlanReadyFlags,
    loadFromHistory,
    scrollToBottom,
    formatToolDetail,
  };
}
