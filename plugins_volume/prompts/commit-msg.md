---
name: commit-msg
description: Draft a conventional commit message from the current diff context
variables: SUMMARY
---

Draft a concise conventional commit message for the following change summary:

$SUMMARY

Rules:
- Subject ≤ 72 chars, imperative mood
- Optional body with why (not what)
- No trailing period on subject
- Output ONLY the commit message text
