# Experience tiers

Codex-like session control for diagram fidelity (and later other UX). Wired in Wave D.

## Ladder (low → high)

| Tier | UX feel | Diagrams | Model expectation |
|------|---------|----------|-------------------|
| **fast** | Snappy | **Mermaid only** (Draw.io fences → source banner) | Small / fast models OK |
| **balanced** (default) | Clear structure | Mermaid default; Draw.io when layout matters | Mid-tier |
| **high** | Polished boards | Prefer **Draw.io XML** for architecture / multi-lane | Stronger models |

## Shipped

- Session field `experience_tier` via `PATCH /api/sessions/{id}/interaction` (+ chat body)
- Composer **+** menu → **体验档**
- Kernel prompt injects tier constraints (`src/common/experience_tiers.py` + `agent_prompts.py`)
- Companion control: `reasoning_effort` (`low` \| `medium` \| `high`) → `ModelRequest.reasoning_effort`
- Soft model-floor hint when raising tier
- **Fast render gate**: `allowDrawio: false` in markdown → blocked Draw.io host (no viewer)

## Model floor (soft)

Raising the Composer **体验档** does **not** block the request. When the current model looks below the tier floor, the UI toasts a hint and offers a one-click switch.

## Still optional

- [x] Soft model-floor hint when raising tier
- [x] Reject / convert Draw.io fences on `fast` at render time
- [ ] Telemetry: format used vs tier

See also: [diagrams.md](./diagrams.md), [canvas.md](./canvas.md), [interaction-modes.md](./interaction-modes.md).
