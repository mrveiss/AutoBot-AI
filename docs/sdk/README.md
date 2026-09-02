# AutoBot SDK

SDK packages for integrating with the AutoBot REST API.

Everything on this page is checked against the packages as they are shipped:
`repo_tests/sdk_request_url_test.py` pins every URL the Python SDK builds,
`repo_tests/sdk_request_body_test.py` pins every request body against the
backend's own request models, and `repo_tests/sdk_docs_paths_test.py` pins every
path named in this directory's guides against the backend route table. A snippet
here that stops matching the package is a failing test, not a stale paragraph.

---

## Available SDKs

| Language | Package | Status | Source | Guide |
|----------|---------|--------|--------|-------|
| Python | `autobot-sdk` | In-tree, importable, guarded | `libs/autobot-sdk-python` | [Python Quickstart](python-quickstart.md) |
| TypeScript | `@autobot/sdk` | In-tree, importable | `libs/autobot-sdk-ts` | [TypeScript Quickstart](typescript-quickstart.md) |

Neither package is published to PyPI or npm yet. "In-tree" means the code is
checked in and importable from this repository — install it from the source
directory, not from a registry.

---

## Quick Comparison

### Python

The client is **async only**. There is no synchronous client; `AutoBot` is an
async context manager and every resource method is a coroutine.

```python
import asyncio
import os

from autobot_sdk import AutoBot


async def main():
    async with AutoBot(
        base_url="https://autobot.example.com:8443",
        token=os.environ["AUTOBOT_API_TOKEN"],
    ) as bot:
        sessions = await bot.sessions.list()
        print(sessions.data)


asyncio.run(main())
```

`AutoBotClient` is the HTTP base class and carries no resource namespaces.
`AutoBot` is the entry point — it is `AutoBotClient` plus `sessions`, `agents`,
`knowledge` and `analytics`.

### TypeScript

```typescript
import { AutoBot } from '@autobot/sdk';

const bot = new AutoBot({
  baseUrl: 'https://autobot.example.com:8443',
  token: process.env.AUTOBOT_API_TOKEN,
});

const sessions = await bot.sessions.list();
console.log(sessions.data?.sessions);
```

---

## Core Concepts

### Authentication

Both clients take a **bearer token**, passed as `token` or read from the
`AUTOBOT_API_TOKEN` environment variable. There is no `api_key` parameter and no
username/password constructor: obtain a token from the auth API first (see the
[Python Quickstart](python-quickstart.md)) and hand it to the client.

```python
# Explicit
bot = AutoBot(token=os.environ["AUTOBOT_API_TOKEN"])

# Implicit — the same variable, read by the client
bot = AutoBot()
```

### Base URL

`base_url` is the backend **origin** — the `/api` root is added by the client, so
resource paths are written without it. Omit `base_url` and it is composed from
`AUTOBOT_BASE_URL`, or from `AUTOBOT_BACKEND_HOST` / `AUTOBOT_BACKEND_PORT`.

### Sessions

Chat sessions are created, listed and read through the `sessions` resource. The
SDK does not create a session implicitly for you.

```python
async with AutoBot() as bot:
    created = await bot.sessions.create(title="My Project")
    listed = await bot.sessions.list(scope="user")
    messages = await bot.sessions.get(session_id, page=1, per_page=50)
```

`sessions.list()` takes `scope` and `team_id`, which are the parameters the route
declares. It is not paginated — it returns the caller's whole list.

### Responses

Some routes answer with a `DataResponse` envelope (`success` / `message` /
`data`) and some answer with a flat document. The SDK models each one as what it
actually is, so a method's return type tells you which you have: `sessions.*`
return `DataResponse[...]`, while `knowledge.*`, `agents.health()`,
`agents.get_config()` and `analytics.*` return flat models.
`repo_tests/sdk_response_model_contract_test.py` pins each model to the route it
parses.

### Error handling

The Python SDK raises **`httpx.HTTPStatusError`** on a non-2xx response — it
calls `raise_for_status()` and does not translate. There is no
`autobot_sdk.exceptions` module and no typed exception hierarchy.

```python
import httpx

try:
    stats = await bot.knowledge.stats()
except httpx.HTTPStatusError as exc:
    print(exc.response.status_code, exc.response.text)
```

### Not in the SDK

These are reachable over raw HTTP and have no SDK method. Both quickstarts show
the HTTP calls for them:

* **Streaming.** Neither client streams. `POST /api/chat/stream` is a
  server-sent-event route you call directly.
* **Chat.** There is no `chat` resource. Sending a message is `POST /api/chat`;
  the `sessions` resource manages the sessions those messages belong to.
* **Workflows, models, collections, file upload, voice and multimodal.** No
  resource covers these.

---

## API Reference

For the complete API reference with all endpoints, request/response schemas, and examples, see:

- [Public API Reference](../api/public-api-reference.md)
- [API Versioning Strategy](../api/api-versioning.md)

---

## Feature Coverage

What each package actually implements today, resource by resource. Anything not
listed has no SDK method — use raw HTTP.

| Resource | Method | Python | TypeScript |
|----------|--------|--------|------------|
| sessions | `list` | Yes | Yes |
| sessions | `get` | Yes | Yes |
| sessions | `create` / `update` / `delete` | Yes | Yes |
| agents | `health` | Yes | Yes |
| agents | `get_config` | Yes | Yes (`getConfig`) |
| agents | `set_model` / `set_enabled` | Yes | No |
| agents | `send_command` | Yes (route defect, see below) | Yes (`sendCommand`) |
| knowledge | `stats` / `add_text` / `search` | Yes | Yes |
| knowledge | `get_entries` | Yes | Yes (`getEntries`) |
| analytics | `usage` / `performance` | Yes | Yes |
| chat send / stream | — | No | No |
| collections, workflows, models, file upload, voice, multimodal | — | No | No |

Two known defects, both filed rather than papered over:

* `agents.send_command` (both packages) targets `POST /api/agent/execute_command`,
  which declares a `dict` body parameter alongside a `Form` field. FastAPI
  therefore publishes it as form-encoded while requiring a field that can only
  arrive as JSON, so **no client can call it** — every candidate body answers
  422. The SDK half waits on the route being fixed.
* The TypeScript package has not had the request-contract corrections the Python
  package received (`sessions.list` still sends `limit`/`offset`,
  `analytics.usage` still sends `period`, several flat responses are still
  modelled as envelopes). Prefer the Python SDK until that lands.

---

## Contributing

Both packages live in this repository, under `libs/`. Changes to either must keep
the guards in `repo_tests/sdk_*.py` green — those guards are what stop this page,
the packages, and the API from drifting apart again.
