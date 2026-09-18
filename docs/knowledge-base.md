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
| Kernel RPC | `src/core_kernel/knowledge_rpc.py` (`/rpc/knowledge/*`, registered from `rpc_server.py`) |
| Adapters REST | `src/adapters/knowledge_routes.py` (`/api/knowledge/*` + session uploads) |
| Knowledge page | `web/src/components/knowledge/KnowledgeView.tsx` |
| Composer picker | `web/src/components/knowledge/KnowledgeScopePicker.tsx` |
| Dock admin panel | `web/src/components/layout/KnowledgePanel.tsx` |

**Tables:** `knowledge_docs`, `knowledge_chunks`, `knowledge_sync_log`, plus optional FTS5 virtual table `knowledge_chunks_fts`.

Documents are split heading-aware (breadcrumb `context_header` stored separately from body). Long docs use **parent/child** chunks (WeKnora-style, `KB_PARENT_CHILD=1` default): search the ~384-char child, expand a short hit from its ~2048-char parent. Overlap stays ~15%. Keyword recall uses **SQLite FTS5** when the build supports it (`tokenize='trigram'` first for CJK substrings, else `unicode61`). If FTS5 is missing (some slim SQLite builds), search falls back to ILIKE token matching. Thin recall optionally runs **local query expansion** (stopword strip / quoted phrases / question-word peel — no LLM; `KB_QUERY_EXPAND=0` to disable). When `KB_EMBEDDING_*` or `WEMM_BASE_URL` is set, hybrid merge also scores chunks that have stored vectors — **even if keyword FTS/ILIKE misses**. Embeddings index `context_header + body`. A second-stage token rerank (`rerank_hits`) is unchanged. `kb_stats` reports `fts5` / `fts5_tokenizer`. `kb_read` / GET read return a char window or a chunk plus neighbors, with a `citation` provenance line (heading path included).

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

Dedicated **知识库** page (`/knowledge`) is the library only: pick a KB, search, preview,
ingest. It does **not** split the workbench chat on the same screen.

Open it from:

- Topbar view ring **知识库** (`/knowledge`, also `/?view=knowledge`)
- Topbar chip **知识库**
- Sidebar **知识库** (under 新对话)
- Empty-state card **打开知识库**
- Composer **打开知识库** (next to the KB picker)
- Command palette **知识库（检索 / 管理）** (`Ctrl+K`)

Once open:

- KB selector (**本地知识库** + WeKnora names when `WEKNORA_BASE_URL` is set), search,
  citation results, full-body preview, empty/health/error states.
- Local library **导入文件** (`POST /api/knowledge/docs/file`) — PDF / Office / Markdown
  extracted to text (default ~20MB, `KB_INGEST_MAX_BYTES`; PDF pages `KB_PDF_MAX_PAGES`).
- **去对话** / row **提问** returns to the main chat with that KB already bound.
- One session ↔ one bound KB (`weknora_kb_id`; empty = local). Changing the picker patches
  the session and subsequent turns.

### Main composer picker

The workbench composer always shows a compact **知识库** selector (name, not raw id).
Placeholder: `基于「xxx」提问`. **打开知识库** jumps to the library page with the
same selection. `/api/chat` also sends `weknora_kb_id` on the turn so a picker change is
not lost if the session patch is still in flight.

Composer **添加文件** uploads into a session-scoped knowledge document (`source=session-upload`,
tag `session:{id}`) via `POST /api/sessions/{session_id}/uploads`. Types follow
`SUPPORTED_SUFFIXES` (~512KB). Grounding and `kb_search` for that session include these
docs; other sessions do not see them. Chips on the composer revoke the upload. Files live
under `data/session_uploads/{session_id}/` until the chip is removed or the session is
deleted (`DELETE /api/sessions/{id}` also purges those docs). Adapters reject uploads over
~512KB before proxying to the kernel.

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
- `POST /api/knowledge/docs/file` — multipart library ingest (`file`, optional `workspace_id` / `title`; ~20MB)
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
- `POST /api/sessions/{session_id}/uploads` — multipart session file → tagged KB doc
- `GET /api/sessions/{session_id}/uploads`
- `DELETE /api/sessions/{session_id}/uploads/{doc_id}`

## Workspace docs sync

Ignores `.git`, `node_modules`, `.venv`, `.nlm`, etc. Indexes `docs/**` and shallow trees for:

- `.md` / `.markdown` / `.mdx`
- `.txt` / `.rst` / `.org`
- `.pdf` (`pypdf`; crude scrape only if extraction fails)

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
| `KB_INGEST_MAX_BYTES` | 20MB | Library file ingest + workspace docs sync (session chips stay 512KB) |
| `KB_PDF_MAX_PAGES` | 400 | Pages extracted per PDF |
| `KB_QUERY_EXPAND` | on | Local query variants when first pass is thin |
| `KB_RERANK` | on | Second-stage token rerank of the candidate pool |
| `KB_RERANK_URL` | off | Optional HTTP reranker (OpenAI/Cohere-shaped JSON) |
| `KB_EMBEDDING_*` / `WEMM_*` | off | Optional hybrid + image vectors |

FTS5 has **no env switch**: `ensure_schema` tries trigram → unicode61 and keeps ILIKE if both fail.
Existing databases get an empty FTS table **backfilled** from `knowledge_chunks` on first open.

Ingest also covers **docx / xlsx / pptx** via dep-free OOXML text scrape (not WeKnora anydoc / OCR). Scanned or image-only PDFs may yield no text. `kb_search` / `GET /api/knowledge/search?tag=` and `list_docs?tag=` filter by comma tags. Pass `session_id` on search to include that session’s temporary uploads.

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
| Multi-KB | `weknora_list_kbs` / `GET /api/knowledge/weknora/kbs`; Dock / composer / Feishu `/知识库` picker |
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
2. Topbar **知识库** (`/knowledge`): on 本地知识库, **导入文件** a PDF/Office/Markdown, or paste, or **同步文档**. Search a hit, then **提问** / **去对话**.
3. On the main composer, the **知识库** chip is always visible; changing it binds the session. **添加文件** uploads a temporary doc for this session only (~512KB).
4. In chat (tools on): the turn is pre-retrieved against that KB (plus this session’s uploads); the agent should still `kb_read` / `weknora_read` and cite paths.
5. Or: `curl "http://127.0.0.1:8000/api/knowledge/search?query=architecture"`
6. Optional: set `KB_EMBEDDING_*`, sync/add docs, then Dock **回填向量** / `kb_reindex`.
