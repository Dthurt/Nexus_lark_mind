---
name: weknora-research
description: Research local SQLite KB first, then the bound WeKnora KB; cite and optionally push
allowed-tools: kb_search, kb_read, kb_list, kb_add, weknora_search, weknora_list_kbs, weknora_push, weknora_sync, weknora_health, read_file, grep
---

# WeKnora research

Use this when the user wants answers from the knowledge base, a bound WeKnora KB, or both.

## Order of operations

1. Prefer **local** `kb_search` (SQLite is the default). Then `kb_read` the best `doc_id` / `chunk_index`.
2. If local hits are thin, the user asked for the remote KB, or a session WeKnora KB is bound, call `weknora_search` (omit `kb_id` to use the session / workspace route).
3. If several remote KBs exist and routing is unclear, call `weknora_list_kbs` first.
4. Cite local `source_uri` / `citation` and WeKnora titles. Do not invent from snippets alone.
5. Persist only when asked: `kb_add` for the local store; `weknora_push` (or `weknora_sync` direction=`push`) for the remote KB. Identity is `nlm_doc_id` + `content_hash` — do not create a second local copy after a push.

## Do not

- Skip local search when WeKnora is configured.
- Push or sync write unless the user wants the note shared or indexed remotely.
- Claim WeKnora is available if `weknora_health` / search returns `skipped`.
