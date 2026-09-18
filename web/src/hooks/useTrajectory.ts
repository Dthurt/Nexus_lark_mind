import { useCallback, useRef, useState } from "react";

import { trajectoryPreviewText } from "@/lib/trajectoryPreview";

export type TrajectoryKind =
  | "turn"
  | "turn-end"
  | "user"
  | "message"
  | "tool"
  | "reasoning"
  | "subagent"
  | "system";

export type TrajectoryRow = {
  id: string;
  seq: number;
  at: number;
  turn: number;
  kind: TrajectoryKind | string;
  title?: string;
  summary?: string;
  detail?: unknown;
  phase?: string;
  error?: boolean;
  durationMs?: number | null;
  startedAt?: number | null;
  activityId?: string | null;
  callId?: string;
  openaiName?: string;
  success?: boolean;
  usage?: unknown;
  args?: unknown;
  result?: unknown;
  opensTurn?: boolean;
  [key: string]: unknown;
};

let seq = 0;
function nextId(prefix = "tr") {
  seq += 1;
  return `${prefix}-${Date.now()}-${seq}`;
}

function previewOf(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return trajectoryPreviewText(value);
  try {
    return trajectoryPreviewText(JSON.stringify(value));
  } catch {
    return trajectoryPreviewText(String(value));
  }
}

/**
 * Trajectory ledger — separate projection from chat bubbles (DSH-inspired).
 * Tool call/result share one row by callId; reasoning/subagent are first-class kinds.
 */
export function useTrajectory() {
  const [rows, setRows] = useState<TrajectoryRow[]>([]);
  const [followTail, setFollowTail] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const turnRef = useRef(0);
  const rowsRef = useRef<TrajectoryRow[]>([]);
  const reasoningIdRef = useRef<string | null>(null);
  const subagentIdMapRef = useRef<Map<string, string>>(new Map());
  rowsRef.current = rows;

  const clear = useCallback(() => {
    rowsRef.current = [];
    setRows([]);
    setSelectedId(null);
    turnRef.current = 0;
    reasoningIdRef.current = null;
    subagentIdMapRef.current.clear();
  }, []);

  const commit = useCallback((next: TrajectoryRow[]) => {
    rowsRef.current = next;
    setRows(next);
  }, []);

  const push = useCallback(
    (row: Partial<TrajectoryRow> & { kind: string }) => {
      const item: TrajectoryRow = {
        id: nextId(),
        seq: rowsRef.current.length + 1,
        at: Date.now(),
        turn: turnRef.current,
        startedAt: Date.now(),
        ...row,
        kind: row.kind,
      };
      commit([...rowsRef.current, item]);
      return item;
    },
    [commit],
  );

  const patchById = useCallback(
    (id: string, patch: Partial<TrajectoryRow>) => {
      const next = rowsRef.current.map((r) => (r.id === id ? { ...r, ...patch } : r));
      commit(next);
      return next.find((r) => r.id === id) || null;
    },
    [commit],
  );

  const startTurn = useCallback(() => {
    turnRef.current += 1;
    reasoningIdRef.current = null;
    subagentIdMapRef.current.clear();
    return push({
      kind: "turn",
      title: `Turn #${turnRef.current}`,
      summary: `Turn #${turnRef.current}`,
      opensTurn: true,
    });
  }, [push]);

  const addUser = useCallback(
    (text: string) =>
      push({
        kind: "user",
        title: "user",
        summary: previewOf(text) || "user",
        detail: text,
      }),
    [push],
  );

  const addAssistant = useCallback(
    (text: string, usage: unknown = null) => {
      if (reasoningIdRef.current) {
        const rid = reasoningIdRef.current;
        const row = rowsRef.current.find((r) => r.id === rid);
        if (row?.phase === "running" && row.startedAt) {
          patchById(rid, {
            phase: "done",
            durationMs: Math.max(0, Date.now() - Number(row.startedAt)),
          });
        }
        reasoningIdRef.current = null;
      }
      return push({
        kind: "message",
        title: "assistant",
        summary: previewOf(text) || "assistant",
        detail: text,
        usage: usage || null,
      });
    },
    [patchById, push],
  );

  const addToolCall = useCallback(
    (payload: any, activityId: string | null = null) => {
      const callId = String(payload?.id || "");
      const name = payload?.name || "tool";
      const args = payload?.arguments ?? payload?.raw_arguments;
      if (callId) {
        const existing = rowsRef.current.find(
          (r) => r.kind === "tool" && r.callId === callId,
        );
        if (existing) {
          return patchById(existing.id, {
            phase: "running",
            title: name,
            summary: name,
            detail: args,
            args,
            activityId: activityId ?? existing.activityId,
            openaiName: payload.openai_name || payload.name,
            startedAt: existing.startedAt || Date.now(),
          });
        }
      }
      return push({
        kind: "tool",
        title: name,
        phase: "running",
        summary: name,
        detail: args,
        args,
        callId: callId || undefined,
        activityId,
        openaiName: payload.openai_name || payload.name,
        startedAt: Date.now(),
      });
    },
    [patchById, push],
  );

  const addToolResult = useCallback(
    (payload: any, activityId: string | null = null) => {
      const callId = String(payload?.id || "");
      const name = payload?.name || "tool";
      const ok = payload?.success !== false;
      const resultBody = ok ? payload?.result : payload?.error;
      const durationMs =
        payload?.duration_ms != null ? Number(payload.duration_ms) : null;
      const summary = `${ok ? "OK" : "FAIL"} · ${name}`;

      if (callId) {
        const existing = rowsRef.current.find(
          (r) => r.kind === "tool" && r.callId === callId,
        );
        if (existing) {
          const started = existing.startedAt ? Number(existing.startedAt) : null;
          return patchById(existing.id, {
            phase: "result",
            title: name,
            summary,
            detail: {
              args: existing.args ?? existing.detail,
              result: resultBody,
            },
            result: resultBody,
            activityId: activityId ?? existing.activityId,
            success: ok,
            error: !ok,
            durationMs:
              durationMs ??
              (started != null ? Math.max(0, Date.now() - started) : null),
            openaiName: payload.openai_name || payload.name || existing.openaiName,
          });
        }
      }

      return push({
        kind: "tool",
        title: name,
        phase: "result",
        summary,
        detail: resultBody,
        result: resultBody,
        callId: callId || undefined,
        activityId,
        success: ok,
        error: !ok,
        durationMs,
        openaiName: payload.openai_name || payload.name,
      });
    },
    [patchById, push],
  );

  const addReasoning = useCallback(
    (delta: string) => {
      const chunk = String(delta || "");
      if (!chunk) return null;
      const existingId = reasoningIdRef.current;
      if (existingId) {
        const row = rowsRef.current.find((r) => r.id === existingId);
        const prev = typeof row?.detail === "string" ? row.detail : "";
        const next = prev + chunk;
        return patchById(existingId, {
          phase: "running",
          summary: previewOf(next) || "reasoning",
          detail: next,
        });
      }
      const item = push({
        kind: "reasoning",
        title: "reasoning",
        phase: "running",
        summary: previewOf(chunk) || "reasoning…",
        detail: chunk,
        startedAt: Date.now(),
      });
      reasoningIdRef.current = item.id;
      return item;
    },
    [patchById, push],
  );

  const addSubagent = useCallback(
    (payload: any, activityId: string | null = null) => {
      const sid = String(payload?.subagent_id || payload?.id || "");
      const label = payload?.label || sid || "subagent";
      const phase = String(payload?.phase || "event");
      const summary =
        phase === "start"
          ? `start · ${label}`
          : phase === "end"
            ? `done · ${label} (${payload?.status || "ok"})`
            : `${phase} · ${label}`;

      if (sid && subagentIdMapRef.current.has(sid)) {
        const id = subagentIdMapRef.current.get(sid)!;
        const row = rowsRef.current.find((r) => r.id === id);
        const started = row?.startedAt ? Number(row.startedAt) : null;
        const done = phase === "end";
        return patchById(id, {
          phase,
          title: label,
          summary,
          detail: payload,
          activityId: activityId ?? row?.activityId,
          error: done && payload?.status === "error",
          durationMs:
            done && started != null ? Math.max(0, Date.now() - started) : row?.durationMs,
        });
      }

      const item = push({
        kind: "subagent",
        title: label,
        phase,
        summary,
        detail: payload,
        activityId,
        startedAt: Date.now(),
        callId: sid || undefined,
      });
      if (sid) subagentIdMapRef.current.set(sid, item.id);
      return item;
    },
    [patchById, push],
  );

  const addStatus = useCallback(
    (message: string) =>
      push({
        kind: "system",
        title: "status",
        summary: previewOf(message) || "status",
        detail: message,
      }),
    [push],
  );

  const addError = useCallback(
    (message: string) =>
      push({
        kind: "system",
        title: "error",
        summary: previewOf(message) || "error",
        detail: message,
        error: true,
      }),
    [push],
  );

  const endTurn = useCallback(
    (usage: unknown = null) => {
      if (reasoningIdRef.current) {
        const rid = reasoningIdRef.current;
        const row = rowsRef.current.find((r) => r.id === rid);
        if (row?.phase === "running" && row.startedAt) {
          patchById(rid, {
            phase: "done",
            durationMs: Math.max(0, Date.now() - Number(row.startedAt)),
          });
        }
        reasoningIdRef.current = null;
      }
      return push({
        kind: "turn-end",
        title: `Turn #${turnRef.current} end`,
        summary: `Turn #${turnRef.current} end`,
        usage,
      });
    },
    [patchById, push],
  );

  const select = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  /** Project from persisted chat history messages */
  const loadFromHistory = useCallback(
    (messages: any[]) => {
      clear();
      let opened = false;
      const ensureTurn = () => {
        if (!opened) {
          startTurn();
          opened = true;
        }
      };
      for (const m of messages || []) {
        const role = m.role || "assistant";
        const meta = m.metadata || {};
        if (meta.kind === "tool_call" || (meta.tool_calls && !m.content)) {
          ensureTurn();
          const tc = (meta.tool_calls && meta.tool_calls[0]) || meta.tool_call || {};
          addToolCall(tc);
          continue;
        }
        if (role === "tool" || meta.kind === "tool_result" || meta.tool_result) {
          ensureTurn();
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
        if (role === "user") {
          if (opened) endTurn();
          startTurn();
          opened = true;
          addUser(m.content || "");
        } else if (role === "assistant" && m.content) {
          ensureTurn();
          if (meta.kind === "error") {
            addError(String(meta.error || m.content));
          } else {
            if (meta.reasoning) addReasoning(String(meta.reasoning));
            addAssistant(m.content, meta.usage);
          }
        }
      }
      if (opened) endTurn();
    },
    [
      addAssistant,
      addError,
      addReasoning,
      addToolCall,
      addToolResult,
      addUser,
      clear,
      endTurn,
      startTurn,
    ],
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
    addReasoning,
    addSubagent,
    addStatus,
    addError,
    endTurn,
    select,
    loadFromHistory,
  };
}
