"""Optional pre-compaction hook (Pi-style).

Return {"skip": True} to keep the current window, or
{"instructions": "..."} to annotate the ledger (local extra hint).
"""


def pre_compact(ctx):
    # Default: never skip — NLM still owns window enforcement.
    _ = ctx
    return {}
