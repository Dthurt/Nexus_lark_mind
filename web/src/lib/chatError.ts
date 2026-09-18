/** Persisted stream / send failures — keep in sync with src/common/session_errors.py */

export const CHAT_ERROR_KIND = "error";

export type SessionChatMessage = {
  role?: string;
  content?: string;
  metadata?: {
    kind?: string;
    error?: string;
    cancelled?: boolean;
    task_id?: string;
    partial?: string;
    [key: string]: unknown;
  } | null;
};

export function isPersistedErrorMessage(message: SessionChatMessage | null | undefined): boolean {
  return message?.metadata?.kind === CHAT_ERROR_KIND;
}

export function formatStreamErrorText(error: string, cancelled = false): string {
  if (cancelled) return "已停止生成。";
  const text = String(error || "unknown").trim() || "unknown";
  if (text.includes("限流") || text.includes("429")) return `⚠️ ${text}`;
  if (text.startsWith("错误：") || text.startsWith("⚠️")) return text;
  return `错误：${text}`;
}

export function errorFlagsFromMessage(message: SessionChatMessage | null | undefined): {
  error: boolean;
  cancelled: boolean;
} {
  if (!isPersistedErrorMessage(message)) return { error: false, cancelled: false };
  return { error: true, cancelled: !!message?.metadata?.cancelled };
}
