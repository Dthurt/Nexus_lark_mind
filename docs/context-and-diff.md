# @ Context & Diff Review

Cursor-inspired workbench features for precise context and post-apply file review.

## @ Context

Composer supports **@ file / directory** chips that the server expands into the model prompt.

### User flow

1. Bind a local (or SSH) workspace.
2. Type `@` in the composer → popover lists cwd entries (filter by query).
3. Select → chip appears above the textarea; a short `@path` token is inserted in the draft.
4. Plus menu **添加文件** also adds a chip.
5. Click a chip to remove it. Chips clear after send.

### Wire format

`POST /api/chat` body field:

```json
{
  "content": "请解释这段逻辑",
  "cwd": "E:\\\\proj",
  "context_refs": [
    { "path": "src/app.py", "kind": "file" },
    { "path": "web/src", "kind": "dir" }
  ]
}
```

### Server expansion

`src/common/context_refs.py` + `WebAdapter.handle_inbound`:

- Local: read file (cap ~24k chars) or list directory entries.
- SSH: path-only stub (use tools to read).
- Merged user message:

```markdown
## Attached context (@)
### @src/app.py
```python
…
```

## User request
请解释这段逻辑
```

Chat timeline still shows the **user-typed** draft (without dumping full file bodies into the bubble).

### Frontend

| Piece | Path |
|-------|------|
| Types / detect `@` | `web/src/lib/contextRefs.ts` |
| Popover | `web/src/components/composer/MentionPopover.tsx` |
| State + send | `useChatActions` (`contextRefs`) |
| UI | `Composer.tsx` chips + `@` placeholder |

---

## Diff Review dock

After `write_file` / `edit_file` **succeeds**, a **变更审阅** panel appears above the composer (like ApprovalDock, but post-apply).

| Action | Effect |
|--------|--------|
| **接受** | Keep disk change; dismiss |
| **撤销** | Restore previous content / reverse edit / delete created file |
| **×** | Dismiss without revert |

### How revert works

1. `write_file` now returns `previous` when overwriting (capped; see agent `_trim_tool_payload` special-case).
2. `edit_file` reverse uses `old_string` / `new_string` from the tool call args.
3. `POST /api/sessions/{id}/diff-revert` → `src/common/diff_revert.py` (local cwd only).

Inline tool cards still show `FileDiffBlock`; DiffDock is the queue for Accept/Reject.

### Frontend

| Piece | Path |
|-------|------|
| Hook | `web/src/hooks/useDiffReview.ts` |
| UI | `web/src/components/chat/DiffDock.tsx` |
| SSE hook | `useChatStream` `onFileMutation` |

### Limits

- SSH: review UI may show; **撤销** requires local cwd.
- Huge overwrites may set `previous_omitted` → cannot auto-revert.
- Pre-apply gate remains **ApprovalDock** when Accept is off.

---

## Related

- [interaction-modes.md](./interaction-modes.md) — approvals / Accept
- [workspaces.md](./workspaces.md) — cwd browse
- [client-architecture.md](./client-architecture.md) — composer stack
- [canvas.md](./canvas.md) — side artifacts (separate from @)
