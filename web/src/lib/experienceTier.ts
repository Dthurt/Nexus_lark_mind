/** Soft model-floor heuristics aligned with `src/common/experience_tiers.py`. */

export type ExperienceTierId = "fast" | "balanced" | "high";

const WEAK_RE =
  /(flash|mini|nano|haiku|lite|tiny|3\.5-turbo|gpt-3\.5|4o-mini|4\.1-nano|qwen.*0\.5|1\.5b|1b|3b)/i;
const STRONG_RE =
  /(opus|sonnet|gpt-4(?!o-mini)|o1|o3|o4|r1|reasoner|plus|pro(?!-mini)|claude-3-5|claude-4|deepseek-v3|qwen.*72|70b|405b)/i;

/** 0 = weak/fast, 1 = mid, 2 = strong */
export function modelStrength(modelName: string | undefined | null): number {
  const name = String(modelName || "").trim();
  if (!name) return 0;
  if (WEAK_RE.test(name)) return 0;
  if (STRONG_RE.test(name)) return 2;
  return 1;
}

const TIER_FLOOR: Record<ExperienceTierId, number> = {
  fast: 0,
  balanced: 1,
  high: 2,
};

export function tierMeetsModelFloor(
  tier: string | undefined | null,
  modelName: string | undefined | null,
): boolean {
  const t = (String(tier || "balanced").toLowerCase() || "balanced") as ExperienceTierId;
  const floor = TIER_FLOOR[t] ?? 1;
  return modelStrength(modelName) >= floor;
}

/** Pick the strongest-looking option; prefer strictly stronger than current. */
export function suggestStrongerModel(
  options: Array<{ value: string; label?: string }>,
  current?: string | null,
): string | null {
  const cur = String(current || "").trim();
  const curStrength = modelStrength(cur);
  let best: string | null = null;
  let bestStrength = curStrength;
  for (const opt of options) {
    const v = String(opt?.value || "").trim();
    if (!v || v === cur) continue;
    const s = modelStrength(v);
    if (s > bestStrength) {
      best = v;
      bestStrength = s;
    }
  }
  return best;
}
