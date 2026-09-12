/**
 * Approximate RMB pricing helpers.
 * Rates are ¥ per 1M tokens (input / output / cached-input).
 * These are ballpark defaults for UI estimates — not billing invoices.
 */

const DEFAULT_RATE = { input: 2.0, output: 8.0, cache: 0.2 };

/** Longest-prefix / substring match wins via ordered list. */
const MODEL_RATES = [
  // DeepSeek
  { match: /deepseek-r1/i, input: 4.0, output: 16.0, cache: 0.4 },
  { match: /deepseek-v3|deepseek-chat|deepseek/i, input: 1.0, output: 2.0, cache: 0.1 },
  // GLM / Zhipu
  { match: /glm-4\.5|glm-4-plus|glm-4-air|glm-4/i, input: 1.0, output: 2.0, cache: 0.1 },
  { match: /glm-4v|glm-3/i, input: 0.5, output: 0.5, cache: 0.05 },
  // Qwen
  { match: /qwen-max|qwen2\.5-72b|qwen-plus/i, input: 2.4, output: 9.6, cache: 0.24 },
  { match: /qwen-turbo|qwen2\.5|qwen/i, input: 0.8, output: 2.0, cache: 0.08 },
  // OpenAI-ish (USD≈×7.2 ballpark → ¥)
  { match: /gpt-4o-mini/i, input: 1.1, output: 4.3, cache: 0.55 },
  { match: /gpt-4o|gpt-4\.1/i, input: 18.0, output: 72.0, cache: 9.0 },
  { match: /gpt-4/i, input: 216.0, output: 432.0, cache: 108.0 },
  { match: /o3-mini|o1-mini/i, input: 8.0, output: 32.0, cache: 4.0 },
  { match: /o1|o3/i, input: 108.0, output: 432.0, cache: 54.0 },
  // Claude
  { match: /claude-3-5-haiku|claude-haiku/i, input: 5.8, output: 29.0, cache: 0.58 },
  { match: /claude-3-5-sonnet|claude-sonnet|claude-3-opus|claude/i, input: 22.0, output: 108.0, cache: 2.2 },
  // Moonshot / Kimi
  { match: /moonshot|kimi/i, input: 12.0, output: 12.0, cache: 1.2 },
  // Doubao
  { match: /doubao|seed/i, input: 0.8, output: 2.0, cache: 0.08 },
];

export function resolveModelRate(modelName = "", providerId = "") {
  const key = `${providerId || ""} ${modelName || ""}`.trim();
  for (const row of MODEL_RATES) {
    if (row.match.test(key) || row.match.test(modelName || "")) {
      return {
        input: row.input,
        output: row.output,
        cache: row.cache ?? row.input * 0.1,
        matched: row.match.source,
      };
    }
  }
  return { ...DEFAULT_RATE, matched: "default" };
}

export function estimateCostCny(usage: any, { modelName = "", providerId = "" }: { modelName?: string; providerId?: string } = {}) {
  const rate = resolveModelRate(modelName, providerId);
  const prompt = Number(usage?.prompt_tokens || 0);
  const completion = Number(usage?.completion_tokens || 0);
  const cached = Math.min(Number(usage?.cached_tokens || 0), prompt);
  const uncached = Math.max(0, prompt - cached);
  const yuan =
    (uncached / 1e6) * rate.input +
    (cached / 1e6) * rate.cache +
    (completion / 1e6) * rate.output;
  return {
    yuan,
    rate,
    cached,
    uncached,
    prompt,
    completion,
  };
}

export function formatCny(yuan: number, { approx = true }: { approx?: boolean } = {}) {
  const n = Number(yuan) || 0;
  const prefix = approx ? "≈¥" : "¥";
  if (n <= 0) return `${prefix}0`;
  if (n < 0.001) return `${prefix}${n.toFixed(4)}`;
  if (n < 0.01) return `${prefix}${n.toFixed(3)}`;
  if (n < 1) return `${prefix}${n.toFixed(3)}`;
  if (n < 100) return `${prefix}${n.toFixed(2)}`;
  return `${prefix}${n.toFixed(1)}`;
}

export function formatDurationMs(ms: number) {
  const n = Number(ms) || 0;
  if (n <= 0) return "";
  const s = n / 1000;
  if (s < 10) return `${s.toFixed(1)}s`;
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}:${String(rem).padStart(2, "0")}`;
}

export function cacheHitRate(usage: any) {
  const prompt = Number(usage?.prompt_tokens || 0);
  const cached = Number(usage?.cached_tokens || 0);
  if (prompt <= 0 || cached <= 0) return 0;
  return Math.min(100, (cached / prompt) * 100);
}

export function formatCacheHit(usage: any) {
  const cached = Number(usage?.cached_tokens || 0);
  const rate = cacheHitRate(usage);
  if (cached <= 0) return { text: "缓存 0", rate: 0, cached: 0 };
  const rateText = rate >= 10 ? `${Math.round(rate)}%` : `${rate.toFixed(1)}%`;
  return {
    text: `缓存 ${formatTokenCount(cached)} (${rateText})`,
    rate,
    cached,
  };
}

export function formatTokenCount(n: number) {
  const v = Number(n) || 0;
  if (v < 1000) return String(Math.round(v));
  if (v < 1e6) {
    const k = v / 1000;
    return `${k >= 100 ? Math.round(k) : Math.round(k * 10) / 10}k`;
  }
  return `${(v / 1e6).toFixed(2)}M`;
}

export function formatUsageLine(
  usage: any,
  { modelName = "", providerId = "", compact = false }: { modelName?: string; providerId?: string; compact?: boolean } = {}
) {
  const inn = Number(usage?.prompt_tokens || 0);
  const out = Number(usage?.completion_tokens || 0);
  const est = usage?.estimated ? "~" : "";
  const dur = formatDurationMs(usage?.duration_ms);
  const cache = formatCacheHit(usage);
  const cost = estimateCostCny(usage, { modelName, providerId });
  const costText = formatCny(cost.yuan);

  if (compact) {
    const parts = [`${est}in ${formatTokenCount(inn)}`, `out ${formatTokenCount(out)}`];
    if (dur) parts.push(dur);
    if (cache.cached > 0) parts.push(`${Math.round(cache.rate)}%缓存`);
    parts.push(costText);
    if (modelName) parts.push(modelName);
    return parts.join(" · ");
  }

  const parts = [`${est}in ${formatTokenCount(inn)}`, `out ${formatTokenCount(out)}`];
  if (dur) parts.push(dur);
  if (cache.cached > 0) parts.push(cache.text);
  else parts.push("缓存 0");
  parts.push(costText);
  if (modelName) parts.push(modelName);
  return parts.join(" · ");
}
