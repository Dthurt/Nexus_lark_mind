# Local knowledge base (Nexus Lark Mind)

NLM keeps a **local SQLite knowledge base** for the coding-agent workbench (Feishu + React). It is **not** a WeKnora Wiki / GraphRAG / RBAC clone. Default path needs no Docker, GPU, or external vector DB.

## Architecture

```
Agent tools (kb_*) ──► KnowledgeStore (kernel SQLite)
Web Dock / REST    ──► Adapters /api/knowledge/* ──► Kernel /rpc/knowledge/*
Optional           ──► WeKnora HTTP (weknora_search CLI / weknora_client) when env set
```

| Layer | Path |
|-------|------|
| Store + chunks | `src/core_kernel/plugin_runtime/knowledge_store.py` |
| Ingest helpers | `src/core_kernel/plugin_runtime/knowledge_ingest.py` |
| Embeddings (optional) | `src/core_kernel/plugin_runtime/knowledge_embeddings.py` |
| Workspace sync | `src/core_kernel/plugin_runtime/knowledge_sync.py` |
| WeKnora HTTP client | `src/core_kernel/plugin_runtime/weknora_client.py` |
| Agent tools | `src/core_kernel/plugin_runtime/knowledge_tools.py` |
| Kernel RPC | `src/core_kernel/rpc_server.py` (`/rpc/knowledge/*`) |
| Adapters REST | `src/adapters/app.py` (`/api/knowledge/*`) |
| Web panel | `web/src/components/layout/KnowledgePanel.tsx` |

**Tables:** `knowledge_docs`, `knowledge_chunks`, `knowledge_sync_log`.

Documents are split on headings / blank lines into ~512-character chunks with ~15% overlap. Search ranks **chunks** with keyword scoring (CJK bigrams + Latin tokens). When `KB_EMBEDDING_*` is set, hybrid merge also scores chunks that have stored vectors — **even if keyword ILIKE misses** (semantic recall). `kb_read` / GET read return a char window or a chunk plus neighbors, with a `citation` provenance line.

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
| `weknora_list_kbs` | List remote knowledge bases |
| `weknora_push` / `weknora_sync` | Push doc or bidirectional sync (content_hash) |
| `weknora_health` | Connectivity / latency probe |

System prompt: search → read before answering; cite `source_uri` / citation like web_search.

## Web UI

Right dock tab **知识库** (Command Palette → 右坞 → 知识库):

- List / search with heading + path
- Stats line (docs / chunks / hybrid)
- Paste Markdown **or** workspace-relative path import
- Edit title inline; delete with confirm
- **同步文档** — workspace ingest + sync log strip
- **回填向量** — when embeddings env is configured
- Optional **远程** tab when a WeKnora KB is selected — list/search that KB via
  `/api/knowledge/weknora/knowledge` and `/api/knowledge/weknora/search`.
  Local SQLite remains the default tab.
- Session chrome shows the bound WeKnora KB and active-tools count after Dock
  select or Command Palette preset apply.

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

Unset → keyword-only (default).

```bash
KB_EMBEDDING_BASE_URL=https://api.openai.com/v1   # or WeMM / vLLM OpenAI-compatible base
KB_EMBEDDING_MODEL=text-embedding-3-small
KB_EMBEDDING_API_KEY=sk-...
# KB_EMBEDDING_ENABLED=0   # force off
```

Vectors are stored as JSON on chunks. After configuring embeddings on an existing DB, use Dock **回填向量** or `kb_reindex` / `POST /api/knowledge/reindex`. Hybrid score ≈ keyword + cosine. **WeMM is not a default dependency.**

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
| Search | Prefer `POST /api/v1/knowledge-search`; tool `weknora_search` (+ `kb_id`) |
| Multi-KB | `weknora_list_kbs` / `GET /api/knowledge/weknora/kbs`; Dock KB picker |
| Route | Explicit `kb_id` → session `weknora_kb_id` → `WEKNORA_KB_MAP[workspace]` → `WEKNORA_KB_ID` |
| Push | `weknora_push` / `POST /api/knowledge/weknora/push` → manual knowledge |
| Sync | `weknora_sync` direction=`push\|pull\|both` with content_hash skip |
| Identity | Pull matches `nlm_doc_id` / `weknora_idmap` / `content_hash` so a push+pull does not mint a second `weknora_*` row |
| Health | `weknora_health` / Dock WeKnora strip |
| Skill / preset | `weknora-research` skill + `knowledge-research` preset (`kb_search` → `weknora_search` → `kb_read` / `weknora_push`) |

Kernel helper: `weknora_client.py`. MCP stub: `plugins_volume/mcp/weknora_http.json`.

Feishu / GitLab connectors: prefer ingesting into WeKnora first, then `weknora_sync` pull.
## Feishu knowledge sync

`FeishuWikiConnector` remains an incremental-design **stub**. Prefer paste / file sync; wiki OpenAPI fetch is TODO.

## Try it

1. Start the stack (`nlm start` / `scripts/dev.bat`), open the workbench, bind a workspace.
2. Dock → **知识库** → paste a note, path-import, or **同步文档**.
3. In chat (tools on): ask something that should hit the KB; agent should `kb_search` then `kb_read` and cite paths.
4. Or: `curl "http://127.0.0.1:8000/api/knowledge/search?query=architecture"`
5. Optional: set `KB_EMBEDDING_*`, sync/add docs, then **回填向量** / `kb_reindex`.
