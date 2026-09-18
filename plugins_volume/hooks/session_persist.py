"""Optional session-persist hook (Pi appendEntry analogue).

Return {"entries": [...]} to store a small sidecar on the session
(`extension_entries`). Keep payloads tiny — this is not a second transcript.
"""


def session_persist(ctx):
    _ = ctx
    return {}
