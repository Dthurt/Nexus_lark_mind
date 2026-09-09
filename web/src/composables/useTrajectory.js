import { ref } from "vue";

let seq = 0;
function nextId(prefix = "tr") {
  seq += 1;
  return `${prefix}-${Date.now()}-${seq}`;
}

/**
 * Trajectory ledger — separate projection from chat bubbles (DSH-inspired).
 */
export function useTrajectory() {
  const rows = ref([]);
  const followTail = ref(true);
  const selectedId = ref(null);
  let turn = 0;

  function clear() {
    rows.value = [];
    selectedId.value = null;
    turn = 0;
  }

  function push(row) {
    const item = {
      id: nextId(),
      seq: rows.value.length + 1,
      at: Date.now(),
      turn,
      ...row,
    };
    rows.value.push(item);
    return item;
  }

  function startTurn() {
    turn += 1;
    return push({
      kind: "turn",
      title: `Turn #${turn}`,
      opensTurn: true,
    });
  }

  function addUser(text) {
    return push({
      kind: "user",
      title: "user",
      summary: String(text || "").slice(0, 200),
      detail: text,
    });
  }

  function addAssistant(text, usage = null) {
    return push({
      kind: "message",
      title: "assistant",
      summary: String(text || "").slice(0, 200),
      detail: text,
      usage: usage || null,
    });
  }

  function addToolCall(payload, activityId = null) {
    return push({
      kind: "tool",
      title: payload.name || "tool",
      phase: "call",
      summary: `CALL ${payload.name || "tool"}`,
      detail: payload.arguments ?? payload.raw_arguments,
      callId: payload.id,
      activityId,
      openaiName: payload.openai_name || payload.name,
    });
  }

  function addToolResult(payload, activityId = null) {
    return push({
      kind: "tool",
      title: payload.name || "tool",
      phase: "result",
      summary: `${payload.success === false ? "FAIL" : "OK"} ${payload.name || "tool"}`,
      detail: payload.success === false ? payload.error : payload.result,
      callId: payload.id,
      activityId,
      success: payload.success !== false,
      durationMs: payload.duration_ms ?? null,
      openaiName: payload.openai_name || payload.name,
    });
  }

  function addStatus(message) {
    return push({
      kind: "system",
      title: "status",
      summary: message,
      detail: message,
    });
  }

  function addError(message) {
    return push({
      kind: "system",
      title: "error",
      summary: message,
      detail: message,
      error: true,
    });
  }

  function endTurn(usage = null) {
    return push({
      kind: "turn-end",
      title: `Turn #${turn} end`,
      usage,
    });
  }

  function select(id) {
    selectedId.value = id;
  }

  /** Project from persisted chat history messages */
  function loadFromHistory(messages) {
    clear();
    startTurn();
    for (const m of messages || []) {
      const role = m.role || "assistant";
      const meta = m.metadata || {};
      if (meta.kind === "tool_call" || (meta.tool_calls && !m.content)) {
        const tc = (meta.tool_calls && meta.tool_calls[0]) || meta.tool_call || {};
        addToolCall(tc);
        continue;
      }
      if (role === "tool" || meta.kind === "tool_result" || meta.tool_result) {
        const tr = meta.tool_result || {
          id: m.tool_call_id,
          name: m.name,
          success: true,
          result: m.content,
        };
        addToolResult(tr);
        continue;
      }
      if (role === "system") continue;
      if (role === "user") addUser(m.content || "");
      else if (role === "assistant" && m.content) addAssistant(m.content, meta.usage);
    }
    endTurn();
  }

  return {
    rows,
    followTail,
    selectedId,
    clear,
    startTurn,
    addUser,
    addAssistant,
    addToolCall,
    addToolResult,
    addStatus,
    addError,
    endTurn,
    select,
    loadFromHistory,
  };
}
