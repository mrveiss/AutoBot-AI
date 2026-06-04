---
tags:
  - developer
  - llm-providers
  - reasoning
aliases:
  - Reasoning Effort Provider Integration
---

# Reasoning Effort: Provider Integration

## Overview

AutoBot exposes a unified `reasoning_effort` abstraction across all supported reasoning-capable providers. This document describes the data flow, mapping utility, and provider-specific integration patterns.

**Design decision:** ADR in [MVA-2933](/MVA/issues/MVA-2933#document-plan).

---

## Data Flow

```
ChatMessage.metadata["reasoning_effort"]
       ↓
chat API (api/chat.py)
       ↓
LLMRequest.metadata["reasoning_effort"]
       ↓
Provider-level mapping (per-provider logic)
       ↓
Provider API call with native params
```

1. The chat endpoint reads `metadata["reasoning_effort"]` from the request (or falls back to the user's Redis preference).
2. The value is propagated as-is into `LLMRequest.metadata["reasoning_effort"]`.
3. Each provider's `complete()` / `stream()` method maps the effort level to its native parameter before calling the upstream API.

---

## Mapping Utility

`autobot_shared/reasoning_effort.py` (introduced in [MVA-3012](/MVA/issues/MVA-3012)) exposes:

```python
from autobot_shared.reasoning_effort import effort_to_provider_params, EffortLevel

# Returns a dict of provider-specific kwargs to merge into the API call
params = effort_to_provider_params(
    effort="high",
    provider="anthropic",   # "openai" | "gemini" | "anthropic"
)
# {"thinking": {"type": "enabled", "budget_tokens": 63000}}
```

### `effort_to_provider_params(effort, provider)`

| Argument | Type | Values |
|----------|------|--------|
| `effort` | `str` | `"low"`, `"medium"`, `"high"`, `"auto"` |
| `provider` | `str` | `"openai"`, `"gemini"`, `"anthropic"` |

Returns a `dict` ready to merge into the provider call kwargs, or `{}` if the effort level produces no override (e.g., `"auto"` for OpenAI).

### Anthropic budget token map

```python
ANTHROPIC_BUDGET_TOKENS = {
    "low": 10_000,
    "medium": 30_000,
    "high": 63_000,
    "auto": None,   # extended thinking disabled
}
```

---

## Provider Integration Patterns

### OpenAI (`llm_shared/providers/openai.py`)

OpenAI o3/o4-mini accept `reasoning_effort` as a top-level API parameter:

```python
# Inside OpenAIProvider.complete() / .stream()
effort = request.metadata.get("reasoning_effort")
if effort and effort != "auto":
    api_kwargs["reasoning_effort"] = effort
```

**Supported models:** `o3`, `o4-mini` (and future `o*` series).  
**Non-o-series models:** `reasoning_effort` is not forwarded; field is silently skipped.

### Google Gemini (`llm_shared/providers/vertexai.py`)

Gemini 2.5 uses a `thinking_mode` parameter:

```python
effort = request.metadata.get("reasoning_effort")
thinking_mode_map = {"low": "low", "medium": "medium", "high": "high"}
if effort in thinking_mode_map:
    generation_config["thinking_mode"] = thinking_mode_map[effort]
```

**Supported models:** `gemini-2.5-pro`, `gemini-2.5-flash`.  
**Older Gemini models:** `thinking_mode` is ignored by the API.

### Anthropic (`llm_shared/providers/anthropic.py`)

Anthropic uses an effort-to-budget mapping layered on top of the existing `thinking` API kwargs mechanism:

```python
effort = request.metadata.get("reasoning_effort")
budget = ANTHROPIC_BUDGET_TOKENS.get(effort)

if budget is not None:
    # Inject into api_kwargs so the existing thinking logic picks it up
    api_kwargs.setdefault("thinking", {})
    api_kwargs["thinking"]["type"] = "enabled"
    api_kwargs["thinking"]["budget_tokens"] = budget
    api_kwargs.setdefault("max_tokens", budget + 1000)
    api_kwargs["temperature"] = 1   # required by Anthropic when thinking is enabled
```

The existing `thinking_mode_enabled` / `thinking_budget_tokens` fields are still supported. `reasoning_effort` takes precedence when both are present.

---

## User Preference Storage

User reasoning effort preferences are stored in Redis database 0 (main):

```
Key pattern: user:{user_id}:preferences:reasoning_effort
Value:        "low" | "medium" | "high" | "auto"
TTL:          None (persistent)
```

```python
# Read preference
from autobot_shared.redis_client import get_redis_client

redis = await get_redis_client()
effort = await redis.get(f"user:{user_id}:preferences:reasoning_effort")
effort = effort.decode() if effort else "auto"

# Write preference
await redis.set(f"user:{user_id}:preferences:reasoning_effort", effort)
```

The chat API checks this key when `reasoning_effort` is absent from the request metadata.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Chat Request                                 │
│  metadata["reasoning_effort"] = "high"                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                ┌────────────▼────────────┐
                │      api/chat.py        │
                │  Read effort from:      │
                │  1. request.metadata    │
                │  2. Redis preference    │
                │  3. default "auto"      │
                └────────────┬────────────┘
                             │ LLMRequest.metadata["reasoning_effort"]
                ┌────────────▼────────────┐
                │  autobot_shared/        │
                │  reasoning_effort.py    │
                │  effort_to_provider_    │
                │  params()               │
                └──┬─────────┬─────────┬─┘
                   │         │         │
         ┌─────────▼─┐ ┌─────▼───┐ ┌──▼──────────────┐
         │  OpenAI   │ │ Gemini  │ │   Anthropic      │
         │ reasoning_│ │thinking_│ │ thinking.budget_  │
         │ effort=   │ │mode=    │ │ tokens=63000      │
         │ "high"    │ │"high"   │ │                   │
         └───────────┘ └─────────┘ └───────────────────┘
```

---

## Testing

Tests for the mapping utility live in:

- `autobot-backend/llm_shared/tests/test_reasoning_effort_mapping.py` — unit tests for `effort_to_provider_params()`
- `autobot-backend/api/tests/test_chat_reasoning_effort.py` — integration tests for the chat API with reasoning effort metadata
- `autobot-backend/llm_shared/providers/tests/test_*_reasoning_effort.py` — per-provider unit tests

See [MVA-3016](/MVA/issues/MVA-3016) for test coverage requirements (>90% target).

---

## Adding a New Provider

To add reasoning effort support to a new provider:

1. Add an entry in `effort_to_provider_params()` for the provider key.
2. In the provider's `complete()` / `stream()`, read `request.metadata.get("reasoning_effort")` and apply the mapped params.
3. Guard with a model-capability check — skip silently for unsupported models.
4. Add unit tests in `llm_shared/providers/tests/test_{provider}_reasoning_effort.py`.

---

## Related

- [ADR/Design: MVA-2933](/MVA/issues/MVA-2933#document-plan)
- [Backend Foundation: MVA-3012](/MVA/issues/MVA-3012)
- [Provider Integration: MVA-3013](/MVA/issues/MVA-3013)
- [Frontend UI: MVA-3014](/MVA/issues/MVA-3014)
- [Anthropic provider module](../../autobot-backend/llm_shared/providers/anthropic.py) — existing `thinking` implementation
- [API: reasoning_effort parameter](../api/chat-reasoning-effort.md)
- [User Guide: Reasoning Effort](../user-guide/reasoning-effort-guide.md)
