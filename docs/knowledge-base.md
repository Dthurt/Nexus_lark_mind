# Local knowledge base (Nexus Lark Mind)

NLM keeps a **local SQLite knowledge base** for the coding-agent workbench (Feishu + React). It is **not** a WeKnora Wiki / GraphRAG / RBAC clone. Default path needs no Docker, GPU, or external vector DB.

## Architecture

```
Agent tools (kb_*)     ──► KnowledgeStore (kernel SQLite)
Turn grounding         ──► kb_grounding.py (search bound KB before LLM)
Web 知识库 page / Dock ──► Adapters /api/knowledge/* ──► Kernel /rpc/knowledge/*
Optional               ──► WeKnora HTTP (weknora_client) when WEKNORA_BASE_URL set
```

| Layer | Path |
|-------|------|
| Store + chunks | `src/core_kernel/plugin_runtime/knowledge_store.py` |
| Turn grounding | `src/core_kernel/kb_grounding.py` |
| Ingest helpers | `src/core_kernel/plugin_runtime/knowledge_ingest.py` |
| Embeddings (optional) | `src/core_kernel/plugin_runtime/knowledge_embeddings.py` |
| Query expand (local) | `src/core_kernel/plugin_runtime/knowledge_query.py` |
| Workspace sync | `src/core_kernel/plugin_runtime/knowledge_sync.py` |
| WeKnora HTTP client | `src/core_kernel/plugin_runtime/weknora_client.py` |
| Agent tools | `src/core_kernel/plugin_runtime/knowledge_tools.py` |
| Kernel RPC | `src/core_kernel/rpc_server.py` (`/rpc/knowledge/*`) |
| Adapters REST | `src/adapters/app.py` (`/api/knowledge/*`) |
| Knowledge page | `web/src/components/knowledge/KnowledgeView.tsx` |
| Composer picker | `web/src/components/knowledge/KnowledgeScopePicker.tsx` |
| Dock admin panel | `web/src/components/layout/KnowledgePanel.tsx` |

**Tables:** `knowledge_docs`, `knowledge_chunks`, `knowledge_sync_log`.

Documents are split heading-aware (breadcrumb `context_header` stored separately from body). Long docs use **parent/child** chunks (WeKnora-style, `KB_PARENT_CHILD=1` default): search the ~384-char child, expand a short hit from its ~2048-char parent. Overlap stays ~15%. Search ranks **children** with keyword scoring (CJK bigrams + Latin tokens). Thin recall optionally runs **local query expansion** (stopword strip / quoted phrases / question-word peel — no LLM; `KB_QUERY_EXPAND=0` to disable). When `KB_EMBEDDING_*` or `WEMM_BASE_URL` is set, hybrid merge also scores chunks that have stored vectors — **even if keyword ILIKE misses**. Embeddings index `context_header + body`. `kb_read` / GET read return a char window or a chunk plus neighbors, with a `citation` provenance line (heading path included).

## Agent tools

| Tool | Role |
|------|------|
| `kb_search` | Keyword (+ optional vector) search → `doc_id`, `chunk_id`, `citation`, `citations_md` |
| `kb_read` | Read by `doc_id` (`offset`/`limit` or `chunk_index`/`neighbors`) + citation |
| `kb_get` / `kb_list` / `kb_delete` | Full doc / list / delete |
| `kb_add` | Paste content **or** `path` (`.md/.txt/.rst/.pdf`) → `source=file:...` |
| `kb_sync_docs` | Scan workspace docs with `content_hash` upsert |
| `kb_stats` / `kb_reindex` | Counts + hybrid readiness; backfill missing embeddings |
| `weknora_search` | Optional remote search (`kb_id` / session / `WEKNORA_KB_MAP`) |
| `weknora_read` | Full remote body by `knowledge_id` (after `weknora_search`) |
| `weknora_list_kbs` | List remote knowledge bases |
| `weknora_push` / `weknora_sync` | Push doc or bidirectional sync (content_hash) |
| `weknora_health` | Connectivity / latency probe |

System prompt: search → read before answering; cite `source_uri` / citation like web_search.

Each **agent turn** also runs a **deterministic retrieval step** (`kb_grounding.py`) against the
session-bound KB *before* the LLM: local `kb_search`, or `weknora_search` with that session
`kb_id` only (never the first listed KB / silent `WEKNORA_KB_ID` fallback). Top snippets are
injected as `<knowledge_context>`. Tools still work for follow-up reads.

## Web UI

### Knowledge page (first-class)

Topbar view ring **知识库** (also `/?view=knowledge` and `/knowledge`):

- Left: KB selector (**本地知识库** + WeKnora names when `WEKNORA_BASE_URL` is set), search,
  citation results, full-body preview, empty/health/error states.
- Right: the **same** workbench chat (same session / same agent). Composing here continues
  that session with the selected KB already bound.
- One session ↔ one bound KB (`weknora_kb_id`; empty = local). Changing the picker patches
  the session and subsequent turns.

### Main composer picker

The workbench composer always shows a compact **知识库** selector (name, not raw id).
Placeholder: `基于「xxx」提问`. **在知识库中打开** jumps to the Knowledge page with the
same selection. `/api/chat` also sends `weknora_kb_id` on the turn so a picker change is
not lost if the session patch is still in flight.

### Dock (admin)

Right dock tab **知识库** remains ingest/sync/reindex (Command Palette → 右坞):

- List / search with heading + path
- Stats line (docs / chunks / hybrid)
- Paste Markdown **or** workspace-relative path import
- Edit title inline; delete with confirm
- **同步文档** — workspace ingest + sync log strip
- **回填向量** — when embeddings env is configured
- Optional **远程** browse when a WeKnora KB is selected — list/search that KB via
  `/api/knowledge/weknora/knowledge` and `/api/knowledge/weknora/search`.
  **导入到本地** copies one remote doc into SQLite (`POST /api/knowledge/weknora/import`).
- Dock picker includes **本地知识库** and does **not** auto-select the first remote KB.

Topbar chip always shows the bound scope (本地知识库 or WeKnora name); click opens the
Knowledge page.

## REST (workspace-scoped)

Query/body may include `workspace_id` and `cwd` where relevant.

- `GET /api/knowledge/docs`
- `GET /api/knowledge/search?query=` → `{ results, citations_md }`
- `GET /api/knowledge/stats`
- `GET /api/knowledge/docs/{doc_id}`
- `GET /api/knowledge/docs/{doc_id}/read`
- `POST /api/knowledge/docs` — `{ title, content }` or `{ path, cwd }`
- `PATCH /api/knowledge/docs/{doc_id}` — partial title/content/tags
- `DELETE /api/knowledge/docs/{doc_id}`
- `POST /api/knowledge/reindex` — embed chunks missing vectors
- `POST /api/knowledge/sync/docs` — `{ cwd, workspace_id? }`
- `POST /api/knowledge/sync/feishu` — skeleton (logs TODO; prefer paste/file first)
- `GET /api/knowledge/sync/log`
- `GET /api/knowledge/weknora/health`
- `GET /api/knowledge/weknora/kbs`
- `GET /api/knowledge/weknora/knowledge?kb_id=` — remote list (Dock 远程)
- `GET /api/knowledge/weknora/item?knowledge_id=` — full remote body
- `POST /api/knowledge/weknora/import` — one remote doc → local SQLite
- `POST /api/knowledge/weknora/search`
- `POST /api/knowledge/weknora/push`
- `POST /api/knowledge/weknora/sync`

## Workspace docs sync

Ignores `.git`, `node_modules`, `.venv`, `.nlm`, etc. Indexes `docs/**` and shallow trees for:

- `.md` / `.markdown` / `.mdx`
- `.txt` / `.rst` / `.org`
- `.pdf` (optional `pypdf` if installed; else crude lossy text extract)

Upsert key is a stable `file_<sha1(rel)>` id plus `content_hash` skip-if-unchanged.

## Optional embeddings (hybrid)

Unset → keyword-only (default). Either `KB_EMBEDDING_BASE_URL` **or** `WEMM_BASE_URL` enables hybrid search. Requests try `/embeddings` then `/v1/embeddings` so a bare host or an OpenAI `/v1` base both work. Failures degrade to keyword-only.

```bash
KB_EMBEDDING_BASE_URL=https://api.openai.com/v1
KB_EMBEDDING_MODEL=text-embedding-3-small
KB_EMBEDDING_API_KEY=sk-...
# KB_EMBEDDING_DIM=256        # optional Matryoshka truncate + L2 re-norm
# KB_EMBEDDING_ENABLED=0      # force off
```

### WeMM-Embedding (optional local backend)

[WeMM-Embedding](https://github.com/Tencent/WeMM-Embedding) is a multimodal embedding model (text / image / visdoc). Serve it with vLLM pooling or SGLang, then point NLM at that OpenAI-compatible endpoint. **No package install inside NLM.**

```bash
# vLLM: vllm serve $MODEL_PATH --runner pooling --chat-template $MODEL_PATH/embedding_chat_template.jinja
WEMM_BASE_URL=http://127.0.0.1:8000/v1
WEMM_MODEL=WeMM-Embedding-2B
# WEMM_DIM=256
```

`WEMM_*` is an alias for `KB_EMBEDDING_*`. When the backend is WeMM, workspace sync may also index shallow images (placeholder markdown + image vector). Generic OpenAI shims stay text-only unless `KB_EMBEDDING_MULTIMODAL=1`.

Vectors are stored as JSON on chunks. After configuring embeddings on an existing DB, use Dock **回填向量** or `kb_reindex` / `POST /api/knowledge/reindex`. Hybrid score ≈ keyword + cosine.

## Local RAG knobs (not a WeKnora clone)

| Env | Default | Role |
|-----|---------|------|
| `KB_PARENT_CHILD` | on | Parent/child chunks for long docs |
| `KB_QUERY_EXPAND` | on | Local query variants when first pass is thin |
| `KB_EMBEDDING_*` / `WEMM_*` | off | Optional hybrid + image vectors |

## Optional WeKnora bridge

Local SQLite stays default. When configured, NLM can **search, list KBs, push, and
bidirectionally sync** with WeKnora.

```bash
WEKNORA_BASE_URL=http://127.0.0.1:8080
WEKNORA_API_KEY=...          # X-API-Key + Bearer
WEKNORA_KB_ID=...            # default knowledge-base id
# WEKNORA_KB_MAP=ws-a=kb-1,ws-b=kb-2   # workspace → KB routing
# WEKNORA_SEARCH_PATH=       # optional legacy override
# WEKNORA_INGEST_ENABLED=1   # set 0 to disable push/sync write
```

| Capability | How |
|------------|-----|
| Search | Prefer `POST /api/v1/knowledge-search`; tool `weknora_search` (+ `kb_id`). Requires a KB id — does not pick the first listed KB. Session-bound chat forces that `kb_id` even if the model omits or passes another. |
| Turn grounding | Server-side search injected as `<knowledge_context>` (`src/core_kernel/kb_grounding.py`) |
| Read | `weknora_read` / `GET /api/knowledge/weknora/item` for the full remote body |
| Multi-KB | `weknora_list_kbs` / `GET /api/knowledge/weknora/kbs`; Dock KB picker |
| Route | Explicit `kb_id` → session `weknora_kb_id` → `WEKNORA_KB_MAP[workspace]` → `WEKNORA_KB_ID` |
| Push | `weknora_push` / `POST /api/knowledge/weknora/push`. If a remote id is already known, **update or skip** (no append-only second POST). Title+content push records local identity. |
| Sync | `weknora_sync` direction=`push\|pull\|both` with content_hash skip. Dirty local (hash ≠ last pull/push) is a **conflict** — pull does not overwrite. |
| Identity | Pull matches `nlm_doc_id` / `weknora_idmap` / title+hash fallback / `content_hash` so a push+pull does not mint a second `weknora_*` row (even when WeKnora omits `knowledge_id`) |
| Import | Dock 远程 **导入到本地** / `POST /api/knowledge/weknora/import` |
| Health | `weknora_health` / Dock WeKnora strip |
| Skill / preset | `weknora-research` skill (`/skill:` injects SKILL.md) + `knowledge-research` preset (`kb_search` → `weknora_search` → `weknora_read` / `kb_read`) |

Kernel helper: `weknora_client.py`. Optional MCP stubs (disabled): `plugins_volume/mcp/weknora_http.json` and `weknora_mcp.json` (`WEKNORA_MCP_URL` → WeKnora's `hybrid_search` / `list_knowledge` / `get_knowledge`). Prefer the first-class `weknora_*` tools.

Feishu / GitLab connectors: prefer ingesting into WeKnora first, then `weknora_sync` pull.
## Feishu knowledge sync

`FeishuWikiConnector` remains an incremental-design **stub**. Prefer paste / file sync; wiki OpenAPI fetch is TODO.

## Try it

1. Start the stack (`nlm start` / `scripts/dev.bat`), open the workbench, bind a workspace.
2. Topbar **知识库** (or composer picker → 在知识库中打开): choose 本地知识库 or a WeKnora KB, search, open a hit, then ask in the right-hand chat.
3. On the main composer, the **知识库** chip is always visible; changing it binds the session.
4. In chat (tools on): the turn is pre-retrieved against that KB; the agent should still `kb_read` / `weknora_read` and cite paths.
5. Or: `curl "http://127.0.0.1:8000/api/knowledge/search?query=architecture"`
6. Optional: set `KB_EMBEDDING_*`, sync/add docs, then Dock **回填向量** / `kb_reindex`.
