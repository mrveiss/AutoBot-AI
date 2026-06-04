---
tags:
  - api
  - chat
  - reasoning
aliases:
  - Chat Reasoning Effort API
---

# Chat API: Reasoning Effort Parameter

The `reasoning_effort` metadata field controls how deeply a reasoning model "thinks" before generating a response. It is passed in the `metadata` object of a `ChatMessage` request.

---

## Supported Endpoints

| Endpoint | Method | Supports `reasoning_effort` |
|----------|--------|-----------------------------|
| `/chat` | POST | ✅ |
| `/chat/stream` | POST | ✅ |

---

## Request Schema

`reasoning_effort` is set inside the `metadata` field of a `ChatMessage`:

```json
{
  "content": "Explain the root cause of this production incident.",
  "role": "user",
  "session_id": "chat_abc123",
  "metadata": {
    "reasoning_effort": "high"
  }
}
```

### `metadata.reasoning_effort`

| Property | Type | Values | Default |
|----------|------|--------|---------|
| `reasoning_effort` | `string` | `"low"`, `"medium"`, `"high"`, `"auto"` | User preference, or `"auto"` |

- If omitted, the user's stored preference (Redis `user:{user_id}:preferences:reasoning_effort`) is used.
- If no stored preference exists, the provider default applies (`"auto"` behaviour).
- Unrecognised values are treated as `"auto"` with a warning logged.

---

## Example Requests

### Low effort — fast factual lookup

```bash
curl -X POST http://<frontend-ip>:8001/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the capital of France?",
    "role": "user",
    "session_id": "chat_abc123",
    "metadata": {
      "reasoning_effort": "low"
    }
  }'
```

### High effort — complex multi-step reasoning

```bash
curl -X POST http://<frontend-ip>:8001/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Analyze why our database queries are slow and propose a remediation plan.",
    "role": "user",
    "session_id": "chat_abc123",
    "metadata": {
      "reasoning_effort": "high"
    }
  }'
```

### Streaming with medium effort

```bash
curl -X POST http://<frontend-ip>:8001/chat/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Write a Python function to parse log files.",
    "role": "user",
    "session_id": "chat_abc123",
    "metadata": {
      "reasoning_effort": "medium"
    }
  }'
```

---

## Provider Mapping

`reasoning_effort` is translated to provider-specific parameters by the backend mapping utility:

### OpenAI (o3, o4-mini)

```json
// reasoning_effort: "high"
{ "reasoning_effort": "high" }   // passed directly to OpenAI API
```

### Google Gemini 2.5

```json
// reasoning_effort: "medium"
{ "thinking_mode": "medium" }   // mapped to Gemini thinking_mode parameter
```

### Anthropic Claude (Extended Thinking)

```json
// reasoning_effort: "high"
{
  "thinking": {
    "type": "enabled",
    "budget_tokens": 63000
  }
}

// reasoning_effort: "low"  →  budget_tokens: 10000
// reasoning_effort: "medium"  →  budget_tokens: 30000
// reasoning_effort: "high"  →  budget_tokens: 63000
// reasoning_effort: "auto"  →  extended thinking disabled
```

---

## User Preferences Endpoints

### Get user reasoning effort preference

```
GET /api/users/preferences/reasoning_effort
Authorization: Bearer <token>
```

**Response:**

```json
{
  "reasoning_effort": "medium"
}
```

Returns `"auto"` if no preference is set.

### Set user reasoning effort preference

```
PUT /api/users/preferences/reasoning_effort
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**

```json
{
  "reasoning_effort": "medium"
}
```

**Response:**

```json
{
  "success": true,
  "reasoning_effort": "medium"
}
```

**Allowed values:** `"low"`, `"medium"`, `"high"`, `"auto"`

---

## Backward Compatibility

`reasoning_effort` coexists with the pre-existing `thinking_mode_enabled` / `thinking_budget_tokens` fields on `ChatMessage`:

- If **both** are set, `reasoning_effort` takes precedence for Anthropic, with the effort-level budget overriding `thinking_budget_tokens`.
- If only `thinking_mode_enabled: true` is set (no `reasoning_effort`), the original behaviour is preserved: `thinking_budget_tokens` (or its default) is used.
- Models that do not support reasoning effort ignore the field silently.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Unsupported model | Field silently ignored; response generated without reasoning overhead |
| Invalid `reasoning_effort` value | Treated as `"auto"`; warning logged to backend error log |
| Provider API error during reasoning | Returns standard provider error; no silent fallback |

---

## Related Documentation

- [User Guide: Reasoning Effort](../user-guide/reasoning-effort-guide.md) — End-user explanation of the feature
- [Developer Guide: Provider Integration](../developer/REASONING_EFFORT_PROVIDER_INTEGRATION.md) — Implementation details
- [Public API Reference](public-api-reference.md) — Full API endpoint listing
