# Usage Metering API Reference

**Issue:** [#1807](https://github.com/mrveiss/AutoBot-AI/issues/1807)
**Source files:**
- `autobot-backend/api/usage.py` — FastAPI router
- `autobot-backend/services/llm_cost_tracker.py` — `LLMCostTracker` service
- `autobot-backend/constants/model_constants.py` — `MODEL_PRICING_PER_1M_TOKENS`
- `autobot-frontend/src/views/UsageView.vue` — admin dashboard

---

## 1. Overview

AutoBot's usage metering system tracks every LLM API call made by the platform and
converts raw token counts into USD cost figures. Data is stored in Redis (analytics
database, DB 3) and surfaced through a set of admin-only REST endpoints plus a
self-service `/me` endpoint for authenticated users.

**What is tracked per event:**

| Dimension | Description |
|-----------|-------------|
| Tokens | Input and output token counts for each LLM call |
| Cost | Calculated USD cost using provider published rates |
| Provider / Model | Which AI provider and exact model variant was used |
| Session | Optional chat session identifier for per-conversation rollup |
| User | Username of the authenticated caller |
| Agent | Agent ID when the call originated from an AutoBot agent |
| Latency | Wall-clock round-trip time in milliseconds |
| Success | Whether the LLM call completed without an error |

**Who can access what:**

| Endpoint | Required role |
|----------|---------------|
| `GET /api/usage/summary` | Admin |
| `GET /api/usage/by-user` | Admin |
| `GET /api/usage/by-user/{user_id}` | Admin |
| `GET /api/usage/me` | Any authenticated user |
| `POST /api/usage/record` | Any authenticated user |
| `GET /api/usage/export/csv` | Admin |

---

## 2. Data Model

### LLMUsageRecord

The canonical record produced by `LLMCostTracker.track_usage()` and persisted to
Redis. Defined in `llm_cost_tracker.py` as the `LLMUsageRecord` dataclass.

| Field | Type | Unit / Format | Required | Description |
|-------|------|---------------|----------|-------------|
| `provider` | string | enum | yes | LLM provider identifier (see `LLMProvider` enum) |
| `model` | string | model key | yes | Exact model name, e.g. `"gpt-4o"` |
| `input_tokens` | integer | tokens | yes | Number of prompt/input tokens consumed |
| `output_tokens` | integer | tokens | yes | Number of completion/output tokens generated |
| `cost_usd` | float | USD, 6 d.p. | yes | Calculated cost at time of the call |
| `timestamp` | string | ISO 8601 UTC | yes | When the call was made, e.g. `"2026-04-14T10:30:00.123456"` |
| `session_id` | string \| null | opaque | no | Chat session identifier |
| `user_id` | string \| null | username | no | AutoBot username of the caller |
| `agent_id` | string \| null | opaque | no | Agent identifier if call came from an agent |
| `endpoint` | string \| null | path | no | Internal API endpoint that triggered the call |
| `latency_ms` | float \| null | milliseconds | no | Wall-clock time for the LLM API call |
| `success` | boolean | — | yes | `true` if call succeeded, `false` if it errored |
| `error_message` | string \| null | — | no | Error detail when `success` is `false` |
| `metadata` | object | — | no | Provider-specific extra data |

### LLMProvider enum

```
anthropic | openai | ollama | google | openrouter | local
```

### Per-user aggregate (returned by `/by-user`)

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | AutoBot username |
| `call_count` | integer | Total LLM calls attributed to this user |
| `input_tokens` | integer | Cumulative input tokens |
| `output_tokens` | integer | Cumulative output tokens |
| `cost_usd` | float | Total cost in USD (all-time or since last Redis flush) |

---

## 3. API Reference

All endpoints are mounted under the `/api` prefix by `core_routers.py`, so the
full paths are `/api/usage/...`. The `Authorization: Bearer <token>` header is
required for every endpoint. The token is the JWT issued at login and stored in
`localStorage` as `authToken` by the frontend.

### 3.1 GET /api/usage/summary

Returns a system-wide aggregate of tokens, cost, request counts, daily cost time
series, and per-model breakdown for a configurable rolling window.

**Authentication:** Admin only (`check_admin_permission` dependency).

**Query parameters:**

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `days` | integer | 30 | 1–365 | Number of days to include in the summary |

**Response schema:**

```json
{
  "period": {
    "days": 30,
    "start": "2026-03-15",
    "end":   "2026-04-14"
  },
  "tokens": {
    "input":  1234567,
    "output":  456789,
    "total":  1691356
  },
  "cost_usd": 12.3456,
  "requests": 9871,
  "active_users": 5,
  "daily_costs": {
    "2026-04-13": 0.4812,
    "2026-04-14": 0.1234
  },
  "by_model": {
    "gpt-4o": {
      "cost_usd": 8.20,
      "input_tokens": 900000,
      "output_tokens": 310000,
      "call_count": 5412
    },
    "claude-sonnet-4-20250514": {
      "cost_usd": 4.1456,
      "input_tokens": 334567,
      "output_tokens": 146789,
      "call_count": 4459
    }
  }
}
```

**Example curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://autobot.example.com/api/usage/summary?days=7" | python3 -m json.tool
```

**Error responses:**

| HTTP status | Error code | Meaning |
|-------------|------------|---------|
| 401 | — | Missing or invalid JWT |
| 403 | — | Authenticated user does not have admin role |
| 500 | `USAGE_SERVER_ERROR` | Redis unavailable or tracker exception |

---

### 3.2 GET /api/usage/by-user

Returns usage aggregates for every user that has made at least one LLM call,
sorted by `cost_usd` descending.

**Authentication:** Admin only.

**Query parameters:** None.

**Response schema:**

```json
{
  "timestamp": "2026-04-14T10:30:00.000000",
  "total_users": 3,
  "users": [
    {
      "user_id": "alice",
      "call_count": 4102,
      "input_tokens": 820400,
      "output_tokens": 310100,
      "cost_usd": 9.4510
    },
    {
      "user_id": "bob",
      "call_count": 1204,
      "input_tokens": 240800,
      "output_tokens": 92000,
      "cost_usd": 1.5230
    },
    {
      "user_id": "carol",
      "call_count": 565,
      "input_tokens": 113000,
      "output_tokens": 43700,
      "cost_usd": 0.7150
    }
  ]
}
```

**Example curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://autobot.example.com/api/usage/by-user" | python3 -m json.tool
```

**Known limitation (issue #4443):** The underlying `get_all_user_costs()` call
uses `redis.keys()` which is O(N) over the full key space. On deployments with
many users this can block Redis momentarily. A scan-based replacement is tracked
in issue #4443.

---

### 3.3 GET /api/usage/by-user/{user_id}

Returns the usage aggregate for a single named user.

**Authentication:** Admin only.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | string | AutoBot username |

**Response schema (user found):**

```json
{
  "user_id": "alice",
  "found": true,
  "call_count": 4102,
  "input_tokens": 820400,
  "output_tokens": 310100,
  "cost_usd": 9.4510
}
```

**Response schema (user not found):**

```json
{
  "user_id": "unknown-user",
  "found": false
}
```

**Example curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://autobot.example.com/api/usage/by-user/alice" | python3 -m json.tool
```

---

### 3.4 GET /api/usage/me

Returns the authenticated user's own usage summary plus the 50 most recent
individual request records attributed to that user.

**Authentication:** Any authenticated user (`get_current_user` dependency). No
admin role required.

**Query parameters:** None.

**Response schema (data present):**

```json
{
  "user_id": "alice",
  "found": true,
  "call_count": 42,
  "input_tokens": 8400,
  "output_tokens": 3200,
  "cost_usd": 0.0962,
  "recent_requests": [
    {
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "input_tokens": 210,
      "output_tokens": 80,
      "cost_usd": 0.001830,
      "timestamp": "2026-04-14T10:28:44.112233",
      "session_id": "sess_abc123",
      "user_id": "alice",
      "agent_id": null,
      "endpoint": null,
      "latency_ms": 834.5,
      "success": true,
      "error_message": null,
      "metadata": {}
    }
  ]
}
```

**Response schema (no data yet):**

```json
{
  "user_id": "alice",
  "found": false,
  "recent_requests": []
}
```

**Example curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://autobot.example.com/api/usage/me" | python3 -m json.tool
```

---

### 3.5 POST /api/usage/record

Ingests a single LLM usage event. Called internally by AutoBot's LLM handlers
immediately after each API call completes. Can also be called by external
integrations or custom code that invokes an LLM outside the standard pipeline.

**Authentication:** Any authenticated user.

**Request body** (`UsageRecordRequest`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | yes | Provider identifier, e.g. `"openai"` |
| `model` | string | yes | Model name as returned by the provider, e.g. `"gpt-4o"` |
| `input_tokens` | integer | yes | Prompt token count |
| `output_tokens` | integer | yes | Completion token count |
| `session_id` | string \| null | no | Chat session to attribute this call to |
| `user_id` | string \| null | no | Override user attribution; defaults to authenticated username |
| `agent_id` | string \| null | no | Agent identifier |
| `latency_ms` | float \| null | no | Round-trip latency in milliseconds |
| `success` | boolean | no | Default `true`. Set `false` for failed calls |

**Example request body:**

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "input_tokens": 512,
  "output_tokens": 128,
  "session_id": "sess_abc123",
  "agent_id": "agent_007",
  "latency_ms": 1245.0,
  "success": true
}
```

**Response schema:**

```json
{
  "recorded": true,
  "cost_usd": 0.002560,
  "record_id": null
}
```

`record_id` is `null` in the current implementation; it is reserved for a future
persistent-store backend.

**Example curl:**

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","model":"gpt-4o","input_tokens":512,"output_tokens":128}' \
  "https://autobot.example.com/api/usage/record"
```

**Error responses:**

| HTTP status | Meaning |
|-------------|---------|
| 401 | Missing or invalid JWT |
| 422 | Request body validation failed (missing required fields or wrong types) |
| 500 | Redis write failure |

---

### 3.6 GET /api/usage/export/csv

Downloads all usage records for the requested period as a CSV file. The response
is streamed; there is no pagination.

**Authentication:** Admin only.

**Query parameters:**

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `days` | integer | 30 | 1–365 | Rolling window to include in the export |

**Response headers:**

```
Content-Type: text/csv
Content-Disposition: attachment; filename=usage_20260414.csv
```

**CSV columns (in order):**

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO 8601 string | UTC timestamp of the LLM call |
| `provider` | string | LLM provider |
| `model` | string | Model name |
| `user_id` | string | Username (empty string if anonymous) |
| `session_id` | string | Session ID (empty if not set) |
| `agent_id` | string | Agent ID (empty if not set) |
| `input_tokens` | integer | Prompt tokens |
| `output_tokens` | integer | Completion tokens |
| `cost_usd` | float | USD cost to 6 decimal places |
| `latency_ms` | float | Latency in milliseconds (empty if not recorded) |
| `success` | boolean | `True` / `False` |

**Example CSV output:**

```
timestamp,provider,model,user_id,session_id,agent_id,input_tokens,output_tokens,cost_usd,latency_ms,success
2026-04-14T10:28:44.112233,anthropic,claude-sonnet-4-20250514,alice,sess_abc123,,210,80,0.001830,834.5,True
2026-04-14T10:27:01.445566,openai,gpt-4o,bob,,,512,128,0.002560,1245.0,True
```

**Example curl:**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://autobot.example.com/api/usage/export/csv?days=30" \
  -o usage_export.csv
```

**Known limitation (issue #4466):** The `UsageView` frontend currently constructs
the download URL with a `<a>` element approach that cannot attach the `Authorization`
header, causing a 401 error when clicked in a browser. The current workaround
(implemented in `UsageView.vue`) is to perform a `fetch()` with the JWT header and
then trigger a blob download. If your browser blocks the blob URL, use the curl
command above as a fallback.

---

## 4. Cost Model

### How costs are calculated

`LLMCostTracker.calculate_cost()` looks up the model in `MODEL_PRICING_PER_1M_TOKENS`
(defined in `autobot-backend/constants/model_constants.py`) and applies:

```
cost = (input_tokens  / 1_000_000) * pricing["input"]
     + (output_tokens / 1_000_000) * pricing["output"]
```

The result is rounded to 6 decimal places and stored as USD.

### Model lookup order

1. Exact match on lowercased model name.
2. Longest-prefix match — handles date-versioned names like `gpt-4o-2024-11-20`
   matching the `gpt-4o` key. Prevents shorter keys from incorrectly matching
   (e.g. `o3` must not match `o3-mini`).
3. Pattern-based heuristic — substring patterns like `"claude-opus"` or `"gemini-2.5"`
   map unknown model variants to the nearest known model's pricing.
4. If no match: cost is recorded as `$0.00` and a WARNING is logged. This is
   intentional for Ollama/local models.

### Pricing table (as of `PRICING_VERSION = "2026-03-22"`)

Pricing is sourced from provider published rates. The table lives in
`MODEL_PRICING_PER_1M_TOKENS`; all values are **USD per 1 million tokens**.

**Anthropic:**

| Model key | Input $/M | Output $/M |
|-----------|-----------|------------|
| `claude-opus-4-...` | 15.00 | 75.00 |
| `claude-sonnet-4-20250514` | 3.00 | 15.00 |
| `claude-3-5-sonnet-...` | 3.00 | 15.00 |
| `claude-haiku-4-5-...` | 0.80 | 4.00 |
| `claude-3-5-haiku-...` | 0.80 | 4.00 |
| `claude-3-haiku-...` | 0.25 | 1.25 |

**OpenAI:**

| Model key | Input $/M | Output $/M |
|-----------|-----------|------------|
| `gpt-4.1` | 2.00 | 8.00 |
| `gpt-4.1-mini` | 0.40 | 1.60 |
| `gpt-4.1-nano` | 0.10 | 0.40 |
| `gpt-4o` | 2.50 | 10.00 |
| `gpt-4o-mini` | 0.15 | 0.60 |
| `gpt-4-turbo` | 10.00 | 30.00 |
| `gpt-4` | 30.00 | 60.00 |
| `gpt-3.5-turbo` | 0.50 | 1.50 |
| `o1` | 15.00 | 60.00 |
| `o1-mini` | 3.00 | 12.00 |
| `o3` | 2.00 | 8.00 |
| `o3-mini` | 1.10 | 4.40 |
| `o4-mini` | 1.10 | 4.40 |

**Google:**

| Model key | Input $/M | Output $/M |
|-----------|-----------|------------|
| `gemini-2.5-pro` | 1.25 | 10.00 |
| `gemini-2.5-flash` | 0.15 | 0.60 |
| `gemini-2.0-flash` | 0.10 | 0.40 |
| `gemini-1.5-pro` | 1.25 | 5.00 |
| `gemini-1.5-flash` | 0.075 | 0.30 |

**DeepSeek:**

| Model key | Input $/M | Output $/M |
|-----------|-----------|------------|
| `deepseek-v3` | 0.27 | 1.10 |
| `deepseek-r1` | 0.55 | 2.19 |

**Local / Ollama models:** All local models (`llama3`, `mistral`, `codellama`,
`qwen`, `phi`, `gemma`, `deepseek-coder`, etc.) are priced at `$0.00 / M` tokens.

### Staleness warning

`PRICING_VERSION` is set in `llm_cost_tracker.py`. At import time the module emits
a WARNING log if the version date is more than 90 days old (`PRICING_STALENESS_DAYS`).
When you update prices, also update `PRICING_VERSION` to the current date.

---

## 5. UsageView Dashboard

The admin dashboard is implemented in `autobot-frontend/src/views/UsageView.vue`
and reachable at the `/usage` route. It requires an admin account.

**Known issue (#4465):** As of the initial implementation there is no nav link
pointing to `/usage`. Navigate to the URL directly until issue #4465 is resolved.

### Layout and components

**Page header** — Contains the page title ("Usage & Cost Tracking"), a Refresh
button, and an Export CSV button. Both buttons disable with a spinner while their
respective async operations are in flight.

**Error banner** — Displayed when either the summary fetch or the CSV export fails.
Shows the error message and a dismiss button. The error text instructs the user to
verify admin access.

**Summary stat cards** — Three cards rendered once `GET /api/usage/summary`
returns:

| Card | Shows |
|------|-------|
| Total Tokens | `summary.tokens.total` with input/output breakdown below |
| Total Cost | `$summary.cost_usd` (4 decimal places) with period label |
| Requests | `summary.requests` with `summary.active_users` count below |

**Usage by User table** — Populated from `GET /api/usage/by-user`. Columns: User,
Requests, Input Tokens, Output Tokens, Cost (USD). Rows are sorted by the server
(highest cost first). Shows a loading spinner while fetching and an empty-state
message when no data is present.

### Data loading

`onMounted` fires `load()` which issues both API calls in parallel via
`Promise.all`. If either call rejects, the error banner is displayed. A manual
Refresh button re-runs the same `load()` function.

### CSV export

The Export CSV button calls `downloadCsv()`, which performs a `fetch()` request
with the `Authorization: Bearer <token>` header. The response blob is converted
to an object URL and a programmatic `<a>` click triggers the browser's file save
dialog. The filename defaults to `usage.csv` (the server sends
`Content-Disposition: attachment; filename=usage_<date>.csv`, but the frontend
overrides it).

---

## 6. Admin Guide

### Enabling cost tracking

No separate configuration flag is required. `LLMCostTracker` is a module-level
singleton obtained via `get_cost_tracker()`. It initialises lazily on the first
call and connects to Redis analytics DB on demand. As long as the analytics Redis
instance is reachable, tracking is active for every LLM call that goes through
AutoBot's standard LLM handlers.

### Verifying tracking is working

1. Make a chat request in the AutoBot frontend.
2. Call `GET /api/usage/summary` — the `requests` counter should have incremented
   and `cost_usd` should be non-zero.
3. Alternatively, query Redis directly:
   ```bash
   redis-cli -n 3 llen llm_cost:usage
   ```
   The list length equals the total number of tracked events.

### Updating model prices

1. Edit `autobot-backend/constants/model_constants.py`, section
   `MODEL_PRICING_PER_1M_TOKENS`.
2. Update `PRICING_VERSION` in `autobot-backend/services/llm_cost_tracker.py`
   to today's ISO date (e.g. `"2026-04-14"`).
3. Commit and deploy via the standard Ansible playbook. There is no cache to flush;
   the new prices take effect for every call after the backend restarts.

### Adding a new provider or model

Add an entry to `MODEL_PRICING_PER_1M_TOKENS`:

```python
"my-new-model-name": {"input": 1.00, "output": 4.00},
```

The key must match the string that the LLM handler passes as `model=`. Use all
lowercase. If the provider uses versioned names (e.g. `my-model-2026-06-01`),
the prefix-match fallback will resolve it automatically as long as `"my-model"`
is in the table.

### Interpreting aggregates

- `cost_usd` in `/summary` is summed from daily Redis keys (90-day TTL). Records
  older than 90 days roll off the daily totals but remain in the raw usage list
  (100k-record cap, no TTL).
- Per-user and per-agent hash keys have no TTL — they accumulate indefinitely
  until manually deleted.
- `active_users` in `/summary` counts users whose per-user hash key exists in
  Redis, not users active in the current period.

### Budget alerts

`LLMCostTracker` includes a `BudgetAlert` dataclass and a `_check_budget_alerts()`
hook that fires after every usage record is stored. The hook body is currently
a no-op stub. Per-agent monthly budgets can be set via `set_agent_budget()` and
checked via `check_agent_budget()`. A full budget-alert UI is not yet wired
to the frontend.

---

## 7. Redis Storage

AutoBot uses Redis database 3 (`RedisDatabase.ANALYTICS`) for all usage metering
data. The client is obtained via:

```python
from autobot_shared.redis_client import RedisDatabase, get_redis_client
redis = get_redis_client(async_client=True, database=RedisDatabase.ANALYTICS)
```

### Key patterns

All keys are prefixed with `llm_cost:`.

| Key pattern | Redis type | TTL | Description |
|-------------|------------|-----|-------------|
| `llm_cost:usage` | List | None (capped at 100k) | Raw `LLMUsageRecord` JSON, newest first (`LPUSH`) |
| `llm_cost:daily:<YYYY-MM-DD>` | String (float) | 90 days | Cumulative cost in USD for that calendar day |
| `llm_cost:by_model:<model>` | Hash | None | `{input_tokens, output_tokens, cost_usd, call_count}` for each model |
| `llm_cost:by_session:<session_id>` | Hash | 30 days | `{cost_usd, input_tokens, output_tokens}` for a session |
| `llm_cost:by_agent:<agent_id>` | Hash | None | `{cost_usd, input_tokens, output_tokens, call_count}` |
| `llm_cost:by_agent:<agent_id>:daily:<YYYY-MM-DD>` | String (float) | 90 days | Daily cost subtotal per agent |
| `llm_cost:by_user:<user_id>` | Hash | None | `{cost_usd, input_tokens, output_tokens, call_count}` |
| `llm_cost:by_user:<user_id>:daily:<YYYY-MM-DD>` | String (float) | 90 days | Daily cost subtotal per user |
| `llm_cost:agent_budget` | Hash | None | Per-agent monthly budget configuration (JSON values) |
| `llm_cost:budget_alerts` | Hash | None | Budget alert configuration |

### TTL constants

Defined in `autobot-backend/constants/ttl_constants.py`:

| Constant | Seconds | Duration |
|----------|---------|----------|
| `TTL_30_DAYS` | 2,592,000 | Session keys |
| `TTL_90_DAYS` | 7,776,000 | Daily total keys |

### Write strategy

Every call to `LLMCostTracker._store_usage_record()` uses a single Redis pipeline
to batch all writes into one round-trip. This includes the raw list push, daily
total increment, model hash update, and optional session/agent/user hash updates.

---

## 8. Authentication

AutoBot uses JWT bearer tokens. The token is issued by the backend auth service
at login and stored by the frontend in `localStorage` under the key `authToken`.

**Passing the token:**

```
Authorization: Bearer <JWT>
```

**Admin check:** `check_admin_permission` in `auth_middleware.py` verifies the
token and asserts the `admin` role. All admin-only endpoints depend on this.
A user without the admin role receives HTTP 403.

**User identity:** `get_current_user` in `auth_middleware.py` decodes the JWT and
returns the user dict. The `username` field from this dict is used as the
attribution `user_id` when `user_id` is not explicitly supplied in a
`POST /api/usage/record` request body.
