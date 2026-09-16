# Local knowledge base (Nexus Lark Mind)

NLM keeps a **local SQLite knowledge base** for the coding-agent workbench (Feishu + React). It is **not** a WeKnora Wiki / GraphRAG / RBAC clone. Default path needs no Docker, GPU, or external vector DB.

## Architecture

```
Agent tools (kb_*) ──► KnowledgeStore (kernel SQLite)
Web Dock / REST    ──► Adapters /api/knowledge/* ──► Kernel /rpc/knowledge/*
Optional           ──► WeKnora HTTP/MCP stub (read-only) when env set
```

| Layer | Path |
|-------|------|
| Store + chunks | `src/core_kernel/plugin_runtime/knowledge_store.py` |
| Embeddings (optional) | `src/core_kernel/plugin_runtime/knowledge_embeddings.py` |
| Workspace / Feishu sync | `src/core_kernel/plugin_runtime/knowledge_sync.py` |
| Agent tools | `src/core_kernel/plugin_runtime/knowledge_tools.py` |
| Kernel RPC | `src/core_kernel/rpc_server.py` (`/rpc/knowledge/*`) |
| Adapters REST | `src/adapters/app.py` (`/api/knowledge/*`) |
| Web panel | `web/src/components/layout/KnowledgePanel.tsx` |

**Tables:** `knowledge_docs`, `knowledge_chunks`, `knowledge_sync_log`.

Documents are split on headings / blank lines into ~512-character chunks with ~15% overlap. Search ranks **chunks** (keyword; optionally hybrid with embeddings). `kb_read` / GET read can return a char window or a chunk plus neighbors.

## Agent tools

| Tool | Role |
|------|------|
| `kb_search` | Keyword (+ optional vector) search → stable `doc_id`, `chunk_id`, longer snippets |
| `kb_read` | Read by `doc_id` (`offset`/`limit` or `chunk_index`/`neighbors`) |
| `kb_get` / `kb_list` / `kb_delete` | Full doc / list / delete |
| `kb_add` | Paste content **or** `path` (workspace-relative → `source=file:...`) |
| `kb_sync_docs` | Scan `docs/**/*.md` (+ shallow `*.md`) with `content_hash` upsert |

System prompt: **always search → read** before answering from KB content.

## Web UI

Right dock tab **知识库** (Command Palette → 右坞 → 知识库):

- List / search
- Paste Markdown → add
- Delete
- **同步文档** — workspace markdown ingest

## REST (workspace-scoped)

Query/body may include `workspace_id` and `cwd` where relevant.

- `GET /api/knowledge/docs`
- `GET /api/knowledge/search?query=`
- `GET /api/knowledge/docs/{doc_id}`
- `GET /api/knowledge/docs/{doc_id}/read`
- `POST /api/knowledge/docs` — `{ title, content }` or `{ path, cwd }`
- `DELETE /api/knowledge/docs/{doc_id}`
- `POST /api/knowledge/sync/docs` — `{ cwd, workspace_id? }`
- `POST /api/knowledge/sync/feishu` — skeleton (logs TODO; prefer paste/file first)
- `GET /api/knowledge/sync/log`

## Workspace docs sync

Ignores `.git`, `node_modules`, `.venv`, `.nlm`, etc. Prefer `docs/**/*.md`; also indexes shallow `*.md` under cwd. Upsert key is a stable `file_<sha1(rel)>` id plus `content_hash` skip-if-unchanged.

## Optional embeddings (hybrid)

Unset → keyword-only (default).

```bash
KB_EMBEDDING_BASE_URL=https://api.openai.com/v1   # or WeMM / vLLM OpenAI-compatible base
KB_EMBEDDING_MODEL=text-embedding-3-small
KB_EMBEDDING_API_KEY=sk-...
# KB_EMBEDDING_ENABLED=0   # force off
```

Vectors are stored as JSON on chunks. Hybrid score ≈ keyword + cosine. **WeMM is not a default dependency** — point `KB_EMBEDDING_BASE_URL` at any OpenAI-style `/embeddings` endpoint later.

## Optional WeKnora bridge

Local SQLite stays default. Optional stubs:

- MCP config: `plugins_volume/mcp/weknora_http.json` (disabled; set URL when ready)
- CLI: `plugins_volume/cli/weknora_search.py` — no-op unless `WEKNORA_BASE_URL` (+ optional `WEKNORA_API_KEY`)

## Feishu knowledge sync

`FeishuWikiConnector` in `knowledge_sync.py` is an incremental-design **stub** (`source` / `source_uri` / `content_hash` + `knowledge_sync_log`). Feishu OpenAPI client today covers IM cards, not wiki export — **manual paste / file sync first**; wiki fetch is TODO.

## Try it

1. Start the stack (`nlm start` / `scripts/dev.bat`), open the workbench, bind a workspace.
2. Dock → **知识库** → paste a note, or **同步文档**.
3. In chat (tools on): ask something that should hit the KB; agent should `kb_search` then `kb_read`.
4. Or: `curl "http://127.0.0.1:8000/api/knowledge/search?query=architecture"`.
