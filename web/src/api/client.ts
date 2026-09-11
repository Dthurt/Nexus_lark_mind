import type { ApiEnvelope } from "@/types/api";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Extract a human-readable error message from an API envelope / HTTP JSON body. */
export function parseError(json: unknown, fallback = "request failed"): string {
  const root = asRecord(json);
  if (!root) return fallback;

  if (typeof root.detail === "string" && root.detail.trim()) {
    return root.detail;
  }

  if (typeof root.error === "string" && root.error.trim()) {
    return root.error;
  }

  const err = asRecord(root.error);
  if (!err) return fallback;

  const detail = err.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const nested = (detail as Record<string, unknown>).message;
    if (nested != null && String(nested).trim()) return String(nested);
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (err.message != null && String(err.message).trim()) return String(err.message);
  return fallback;
}

async function readJsonSafe(resp: Response): Promise<unknown> {
  const text = await resp.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error(
      resp.status === 404
        ? "接口不存在（404）。请重启本地服务：scripts\\start_local.bat"
        : `响应不是 JSON（HTTP ${resp.status}）`,
    );
  }
}

/**
 * JSON request against the Nexus Lark Mind API.
 * Expects `{ ok, data, error }` envelope; throws Error with message when `!ok`.
 */
export async function apiRequest<T>(
  method: string,
  url: string,
  body?: unknown,
): Promise<T> {
  const init: RequestInit = {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };

  const resp = await fetch(url, init);
  const json = await readJsonSafe(resp);
  const envelope = asRecord(json) as ApiEnvelope<T> | null;

  if (!resp.ok || !envelope?.ok) {
    throw new Error(parseError(json, `HTTP ${resp.status}`));
  }

  return envelope.data as T;
}

export function apiGet<T>(url: string): Promise<T> {
  return apiRequest<T>("GET", url);
}

export function apiPost<T>(url: string, body?: unknown): Promise<T> {
  return apiRequest<T>("POST", url, body);
}

export function apiPut<T>(url: string, body?: unknown): Promise<T> {
  return apiRequest<T>("PUT", url, body);
}

export function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  return apiRequest<T>("PATCH", url, body);
}

export function apiDelete<T>(url: string, body?: unknown): Promise<T> {
  return apiRequest<T>("DELETE", url, body);
}
