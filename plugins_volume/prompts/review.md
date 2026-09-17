---
name: review
description: Structured code review for a file or path
variables: FILE,FOCUS
---

You are performing a careful code review of `$FILE`.

Focus areas (if provided): $FOCUS

Checklist:
1. Correctness and edge cases
2. Security / secret leakage
3. API and naming consistency with the surrounding codebase
4. Tests — what is missing?
5. Clarity — suggest concrete diffs, not vague advice

Output:
- Summary (2–4 sentences)
- Findings (severity / medium / nit), each with file:line when possible
- Suggested patches (unified diff snippets when helpful)
