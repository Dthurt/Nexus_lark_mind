# Model settings

## Concepts (DSH-inspired)

- **Builtin providers** — from `.env` (`openai` / `deepseek` / `glm` / `anthropic`), read-only in UI
- **Custom providers** — OpenAI-compatible routes persisted in `data/model_providers.json`
- **Composer** — picks from merged catalog (`GET /api/providers`)

## UI

Topbar / sidebar → **设置** → Models page:

- set default provider
- list builtins
- add / edit / delete custom providers (id, label, base URL, API key, model list)

## API

```bash
GET  /api/settings/models
POST /api/settings/models/providers
DELETE /api/settings/models/providers/{id}
PUT  /api/settings/models/default
POST /api/settings/models/reload
POST /api/settings/models/discover
POST /api/settings/models/test
GET  /api/providers?configured_only=true
```

`POST /api/settings/models/test` — 连通性探测（`/models` + 可选短对话）。

Custom provider JSON shape:

```json
{
  "id": "my-proxy",
  "label": "My Proxy",
  "api": "openai-completions",
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-...",
  "default_model": "gpt-4o-mini",
  "models": ["gpt-4o-mini", "gpt-4o"],
  "enabled": true
}
```

Discover available models (OpenAI-compatible `GET {base_url}/models`):

```bash
curl -X POST http://127.0.0.1:8000/api/settings/models/discover \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://api.openai.com/v1","api_key":"sk-..."}'
```

Settings UI: after Base URL + API Key, click **拉取可用模型** (or wait for auto-fetch) to fill the model list.

Keys are never returned in full — only `api_key_set` + preview.
