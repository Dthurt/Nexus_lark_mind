import { useCallback, useRef, useState } from "react";

let seq = 0;
function nextId(prefix = "tr") {
  seq += 1;
  return `${prefix}-${Date.now()}-${seq}`;
}

/**
 * Trajectory ledger — separate projection from chat bubbles (DSH-inspired).
 */
export function useTrajectory() {
  const [rows, setRows] = useState<any[]>([]);
  const [followTail, setFollowTail] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const turnRef = useRef(0);
  const rowsRef = useRef<any[]>([]);
  rowsRef.current = rows;

  const clear = useCallback(() => {
    rowsRef.current = [];
    setRows([]);
    setSelectedId(null);
    turnRef.current = 0;
  }, []);

  const push = useCallback((row: any) => {
    const item = {
      id: nextId(),
      seq: rowsRef.current.length + 1,
      at: Date.now(),
      turn: turnRef.current,
      ...row,
    };
    const next = [...rowsRef.current, item];
    rowsRef.current = next;
    setRows(next);
    return item;
  }, []);

  const startTurn = useCallback(() => {
    turnRef.current += 1;
    return push({
      kind: "turn",
      title: `Turn #${turnRef.current}`,
      opensTurn: true,
    });
  }, [push]);

  const addUser = useCallback(
    (text: string) =>
      push({
        kind: "user",
        title: "user",
        summary: String(text || "").slice(0, 200),
        detail: text,
      }),
    [push],
  );

  const addAssistant = useCallback(
    (text: string, usage: any = null) =>
      push({
        kind: "message",
        title: "assistant",
        summary: String(text || "").slice(0, 200),
        detail: text,
        usage: usage || null,
      }),
    [push],
  );

  const addToolCall = useCallback(
    (payload: any, activityId: string | null = null) =>
      push({
        kind: "tool",
        title: payload.name || "tool",
        phase: "call",
        summary: `CALL ${payload.name || "tool"}`,
        detail: payload.arguments ?? payload.raw_arguments,
        callId: payload.id,
        activityId,
        openaiName: payload.openai_name || payload.name,
      }),
    [push],
  );

  const addToolResult = useCallback(
    (payload: any, activityId: string | null = null) =>
      push({
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
      }),
    [push],
  );

  const addStatus = useCallback(
    (message: string) =>
      push({
        kind: "system",
        title: "status",
        summary: message,
        detail: message,
      }),
    [push],
  );

  const addError = useCallback(
    (message: string) =>
      push({
        kind: "system",
        title: "error",
        summary: message,
        detail: message,
        error: true,
      }),
    [push],
  );

  const endTurn = useCallback(
    (usage: any = null) =>
      push({
        kind: "turn-end",
        title: `Turn #${turnRef.current} end`,
        usage,
      }),
    [push],
  );

  const select = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  /** Project from persisted chat history messages */
  const loadFromHistory = useCallback(
    (messages: any[]) => {
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
    },
    [addAssistant, addToolCall, addToolResult, addUser, clear, endTurn, startTurn],
  );

  return {
    rows,
    followTail,
    setFollowTail,
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
