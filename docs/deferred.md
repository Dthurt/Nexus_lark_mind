# Deferred / superseded

Original “full DSH port” items:

| Item | Status in Nexus |
|------|-----------------|
| Cordis module graph | **Superseded** by Cordis-lite (`web/src/runtime/createContext.js`) |
| dockkit split tree | **Superseded** by RightDock 2-pane split + tabs |
| Trajectory dual view | **Done** (Chat \| Trajectory ring) |
| Plugin marketplace | Still deferred (remote install registry) |
| Full Anthropic custom wire in Settings | Custom UI currently OpenAI-compat only |
| Experience tier slider (Codex-like) | **Documented** — see [experience-tiers.md](./experience-tiers.md); agent already chooses Mermaid vs Draw.io |
| Offline / bundled Draw.io viewer | Chat uses embed.diagrams.net for now ([diagrams.md](./diagrams.md)) |
| Feishu cards for tool approval / ask_user | **Deferred** — Web workbench has full Plan / Auto-accept / Ask ([interaction-modes.md](./interaction-modes.md)) |

Marketplace remains out of scope until there is a packaging/signing story.
