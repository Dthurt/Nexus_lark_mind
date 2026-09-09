# Experience tiers (roadmap)

Goal: a **Codex-like** control that raises or lowers “experience quality” for a conversation — not only model size, but **which diagram fidelity** (and later other UX) the agent is allowed to use.

> Status: **documented / agent-hinted**. UI slider and hard coupling to model routing are **not shipped yet**.

## Proposed ladder (low → high)

| Tier | UX feel | Diagrams | Model expectation |
|------|---------|----------|-------------------|
| **1 · Fast** | Snappy, good enough | **Mermaid only** | Small / fast models OK |
| **2 · Balanced** (default) | Clear structure | Mermaid default; Draw.io when layout matters | Mid-tier |
| **3 · High** | Polished boards | Prefer **Draw.io XML** for architecture / multi-lane | Stronger models required |
| **4 · Max** (future) | Publication-grade | Draw.io + optional export PNG/SVG, stricter validation | Best available model |

Rules of thumb:

- Higher tiers **must** route to stronger models — weak models produce broken or empty `mxfile` XML.
- Lower tiers **forbid** Draw.io fences (or rewrite them to Mermaid) so latency and token cost stay down.
- The agent already self-selects Mermaid vs Draw.io by complexity; the tier control will **constrain** that choice.

## UI sketch (TODO)

- Composer or session header: stepped control (like Codex effort / experience), e.g. `Fast | Balanced | High`.
- Persist per session; show current tier next to model picker.
- When user raises tier, optionally suggest / auto-switch to a stronger provider model if the current one is below a floor.

## Implementation checklist

- [ ] Session/composer `experience_tier` field (API + UI)
- [ ] Kernel prompt injects tier constraints (allowed fence languages)
- [ ] Model floor map per tier in settings
- [ ] Optional: reject or convert Draw.io on tier 1
- [ ] Self-host or vendor diagrams.net viewer for offline High tier
- [ ] Telemetry: which format was used vs tier

See also: [diagrams.md](./diagrams.md).
