---
name: verify-change
description: After code edits, run a focused shell check (tests/build/lint) before claiming success
allowed-tools: read_file, grep, glob, list_dir, run_shell
---

# Verify change

When you finish non-trivial code edits:

1. Identify the smallest meaningful check (unit test, typecheck, or a targeted command).
2. Run it with `run_shell` from the workspace cwd.
3. Read the exit code and relevant stderr/stdout.
4. Only then report success — or fix failures and re-check.

Do not claim "done" without evidence from a tool result.
