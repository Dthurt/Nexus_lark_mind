# Plugin packaging (local path)

Marketplace catalog remains deferred; **local install + integrity** is shipped.

## Install

```http
POST /api/plugins/install
Content-Type: application/json

{ "path": "E:/packs/my-plugin" }
```

Or multipart zip: form field `file`.

Package layout:

```text
my-plugin/
  manifest.json   # id, version, kind (cli|mcp), entry?, sha256?, signature?
  entry.py | …
```

- **sha256** (optional): hash of package files excluding `manifest.json` — hard-fail on mismatch
- **signature** (optional): HMAC-SHA256 of canonical manifest JSON (without `signature`) using `PLUGIN_SIGNING_SECRET`

After copy into `plugins_volume/{cli|mcp}/`, adapters call plugin reload.

## Local drop-in (unchanged)

| Kind | Location | Loader |
|------|----------|--------|
| CLI | `plugins_volume/cli/*.py` | `CLI_AUTO_REGISTER=true` |
| MCP | `plugins_volume/mcp/*.json` | manifest JSON |
| In-process | builtin / RPC load | Kernel |

Prefs: `data/plugin_prefs.json`.

See [plugins.md](./plugins.md), [deferred.md](./deferred.md).
