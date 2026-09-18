"""Optional post-compaction hook (Pi-style). Runs after a ledger entry is built."""


def post_compact(ctx):
    _ = ctx
    return {}
