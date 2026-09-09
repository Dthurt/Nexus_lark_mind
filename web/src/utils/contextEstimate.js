/** Heuristic context-window occupancy (Cursor/DSH-style). */

const DEFAULT_WINDOW = 128_000;

/** Known OpenAI-compat context windows (tokens). */
const MODEL_WINDOWS = [
  { match: /gpt-5/i, window: 400_000 },
  { match: /gpt-4\.1/i, window: 1_048_576 },
  { match: /gpt-4o-mini/i, window: 128_000 },
  { match: /gpt-4o/i, window: 128_000 },
  { match: /o3|o4-mini|o1/i, window: 200_000 },
  { match: /claude-opus-4|claude-sonnet-4|claude-3-7|claude-3\.5|claude-4/i, window: 200_000 },
  { match: /claude-3-haiku/i, window: 200_000 },
  { match: /claude/i, window: 200_000 },
  { match: /deepseek/i, window: 64_000 },
  { match: /glm-4|glm4/i, window: 128_000 },
  { match: /qwen.*235|qwen3/i, window: 131_072 },
  { match: /qwen/i, window: 131_072 },
];

export function resolveContextWindow(modelName = "") {
  const name = String(modelName || "");
  for (const row of MODEL_WINDOWS) {
    if (row.match.test(name)) return row.window;
  }
  return DEFAULT_WINDOW;
}

/** ~4 chars / token — same ballpark as backend estimate_usage. */
export function estimateTokens(text) {
  const s = String(text || "");
  if (!s) return 0;
  return Math.max(1, Math.ceil(s.length / 4));
}

function messageText(item) {
  if (!item) return "";
  if (item.kind === "tool") {
    return JSON.stringify({
      name: item.name,
      arguments: item.arguments,
      result: item.result,
      error: item.error,
    });
  }
  return item.content || "";
}

/**
 * Build occupancy + breakdown for the composer meter.
 * @param {{ items?: any[], tools?: any[], modelName?: string, cwd?: string, workspaceTitle?: string, lastPromptTokens?: number, draft?: string }} opts
 */
export function estimateContextOccupancy(opts = {}) {
  const items = opts.items || [];
  const tools = opts.tools || [];
  const modelName = opts.modelName || "";
  const contextWindow = resolveContextWindow(modelName);

  let systemPrompt =
    "You are Nexus Lark Mind, a helpful personal AI agent that can chat and work inside a bound workspace. "
    + "Be concise, accurate, and tool-aware.";
  if (opts.cwd) {
    systemPrompt +=
      `\n\n## Active workspace\n- path (cwd): \`${opts.cwd}\`\n`
      + (opts.workspaceTitle ? `- title: ${opts.workspaceTitle}\n` : "");
  }
  const systemTokens = estimateTokens(systemPrompt);

  let toolsTokens = 0;
  for (const t of tools) {
    toolsTokens += estimateTokens(
      JSON.stringify({
        name: t.openai_name || t.name,
        description: t.description,
        parameters: t.parameters || t.inputSchema,
      })
    );
  }

  let messageTokens = 0;
  for (const item of items) {
    if (item.kind === "msg" || item.kind === "tool") {
      messageTokens += estimateTokens(messageText(item));
    }
  }
  if (opts.draft) {
    messageTokens += estimateTokens(opts.draft);
  }

  const heuristicUsed = systemTokens + toolsTokens + messageTokens;
  // Prefer last provider prompt_tokens as anchor when larger (more complete).
  const anchor = Number(opts.lastPromptTokens || 0);
  const usedTokens = Math.min(contextWindow, Math.max(heuristicUsed, anchor));
  const freeTokens = Math.max(0, contextWindow - usedTokens);
  const percent = contextWindow > 0 ? Math.min(100, Math.round((usedTokens / contextWindow) * 100)) : 0;

  const breakdownTotal = systemTokens + toolsTokens + messageTokens || 1;

  return {
    contextWindow,
    usedTokens,
    freeTokens,
    percent,
    estimated: true,
    breakdown: {
      systemTokens,
      toolsTokens,
      messageTokens,
      freeTokens,
    },
    // Share of the *used* pie (for colored bar inside used portion)
    usedShares: {
      system: systemTokens / breakdownTotal,
      tools: toolsTokens / breakdownTotal,
      messages: messageTokens / breakdownTotal,
    },
  };
}

export function formatCompactTokens(value) {
  const n = Number(value) || 0;
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) {
    const k = n / 1000;
    return `${k >= 100 ? Math.round(k) : Math.round(k * 10) / 10}K`;
  }
  const m = n / 1_000_000;
  return `${m >= 100 ? Math.round(m) : Math.round(m * 10) / 10}M`;
}
