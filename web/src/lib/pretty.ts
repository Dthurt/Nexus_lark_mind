import { formatTokenCount } from "@/lib/pricing";

export function pretty(data: any) {
  if (data == null) return "";
  if (typeof data === "string") {
    try {
      return JSON.stringify(JSON.parse(data), null, 2);
    } catch {
      return data;
    }
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

export function formatUsage(usage: any) {
  const inn = Number(usage?.prompt_tokens || 0);
  const out = Number(usage?.completion_tokens || 0);
  const est = usage?.estimated ? "~" : "";
  return `${est}in ${formatTokenCount(inn)} · out ${formatTokenCount(out)}`;
}

export { formatUsageLine, formatCny, formatDurationMs, formatCacheHit, formatTokenCount } from "./pricing";
