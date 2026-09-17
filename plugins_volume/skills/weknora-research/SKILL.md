---
name: weknora-research
description: Research local SQLite KB first, then the bound WeKnora KB; cite and optionally push
allowed-tools: kb_search, kb_read, kb_list, kb_add, weknora_search, weknora_read, weknora_list_kbs, weknora_push, weknora_sync, weknora_health, read_file, grep
---

# WeKnora research

Use this when the user wants answers from the knowledge base, a bound WeKnora KB, or both.
This playbook is injected on `/skill:weknora-research` — do not `read_file` a repo-relative SKILL.md.

## Order of operations

1. Prefer **local** `kb_search` (SQLite is the default). Then `kb_read` the best `doc_id` / `chunk_index`.
2. If local hits are thin, the user asked for the remote KB, or a session WeKnora KB is bound, call `weknora_search` (omit `kb_id` to use the session / workspace route).
3. After `weknora_search`, call `weknora_read` with the hit `knowledge_id` / `doc_id` for the full remote body. Do not invent from snippets.
4. If several remote KBs exist and routing is unclear, call `weknora_list_kbs` first. Never search without a KB id.
5. Cite local `source_uri` / `citation` and WeKnora titles.
6. Persist only when asked: `kb_add` for the local store; `weknora_push` (or `weknora_sync` direction=`push`) for the remote KB. Identity is `nlm_doc_id` + `content_hash` — do not create a second local copy after a push. If a remote id is already known, update or skip — do not POST another manual doc.

## Do not

- Skip local search when WeKnora is configured.
- Push or sync write unless the user wants the note shared or indexed remotely.
- Claim WeKnora is available if `weknora_health` / search returns `skipped`.
