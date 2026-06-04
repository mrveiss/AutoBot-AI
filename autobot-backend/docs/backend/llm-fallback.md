# LLM Model Fallback

**Status:** Implemented in #9442 (GH#8998)  
**Since:** 2026-06-04

## Overview

AutoBot automatically falls back to alternative models when the primary model returns a rate limit (429) or quota exceeded error. This prevents user-facing failures during quota exhaustion and enables graceful degradation across model tiers and providers.

## Architecture

```
User Request
    ↓
UnifiedLLMInterface.chat_completion()
    ↓
ModelFallbackCoordinator.execute_with_fallback()
    ↓
ProviderRegistry.get_provider_for_request()
    ↓
BaseProvider.chat_completion()
    ↓ (on RateLimitError)
FallbackChainManager.get_next_fallback()
    ↓
Retry with fallback model
```

### Components

- **ModelFallbackCoordinator** (`llm_shared/model_fallback_coordinator.py`)
  - Orchestrates fallback logic
  - Tracks attempt count and audit trail
  - Retries up to `AUTOBOT_MAX_FALLBACK_ATTEMPTS` (default: 3)

- **FallbackChainManager** (`llm_shared/fallback_chain.py`)
  - Manages per-model fallback chains
  - Supports cross-provider fallback
  - Configurable via environment variables

- **RateLimitHandler** (`llm_shared/rate_limit_backoff.py`)
  - Detects 429/quota errors in provider responses
  - Extracts retry-after headers
  - Raises `RateLimitError` for coordinator to catch

## Default Fallback Chains

| Primary Model | Fallback Chain |
|--------------|----------------|
| `claude-opus-4` | claude-sonnet-4 → claude-haiku-4 |
| `claude-sonnet-4` | claude-haiku-4 |
| `gpt-4` | gpt-4o → gpt-4o-mini |
| `gpt-4o` | gpt-4o-mini |
| `claude-opus-4-cross` | gpt-4o → ollama/llama3 |

## Configuration

### Environment Variables

Define custom fallback chains using environment variables:

```bash
# Format: AUTOBOT_FALLBACK_CHAIN_<MODEL>=fallback1,fallback2,...
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS=anthropic:claude-sonnet-4,openai:gpt-4o
AUTOBOT_FALLBACK_CHAIN_GPT_4=openai:gpt-4o,ollama:llama3

# Maximum fallback attempts (default: 3)
AUTOBOT_MAX_FALLBACK_ATTEMPTS=3
```

Provider can be specified with `provider:model` format, or omitted to use the same provider:

```bash
# Same provider fallback
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS=claude-sonnet-4,claude-haiku-4

# Cross-provider fallback
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS=anthropic:claude-sonnet-4,openai:gpt-4o,ollama:llama3
```

### Disabling Fallback

Fallback is enabled by default. To disable for a specific request:

```python
from llm_shared.models import LLMRequest

request = LLMRequest(
    messages=[{"role": "user", "content": "..."}],
    fallback_enabled=False  # Disable fallback for this request
)
```

## Audit Trail

Every response includes fallback metadata in `LLMResponse.provider_metadata`:

```json
{
  "fallback_used": true,
  "primary_model": "claude-opus-4",
  "fallback_model": "claude-sonnet-4",
  "fallback_reason": "rate_limit_429",
  "attempt_count": 2,
  "fallback_chain_tried": ["claude-opus-4", "claude-sonnet-4"],
  "fallback_exhausted": false
}
```

## Logging

Fallback events are logged at `INFO` level:

```
quota-fallback: model='claude-opus-4' hit rate limit (attempt 1), switching to fallback model='claude-sonnet-4' provider='anthropic'
quota-fallback: request succeeded on attempt 2 using model='claude-sonnet-4' (primary='claude-opus-4') chain=['claude-opus-4', 'claude-sonnet-4']
```

When all fallbacks are exhausted:

```
quota-fallback: all 3 fallback attempts exhausted for model='claude-opus-4'
```

## Integration Points

The fallback coordinator is wired into:

- `llm_multi_provider.py` — Main chat completion path
- `api/anthropic_compat.py` — Anthropic API compatibility layer
- `api/openai_compat.py` — OpenAI API compatibility layer

## Testing

Unit tests in `llm_shared/model_fallback_coordinator_test.py`:

```bash
pytest llm_shared/model_fallback_coordinator_test.py -v
```

Test coverage:
- ✅ Primary model succeeds without fallback
- ✅ Rate limit triggers single fallback
- ✅ Multiple fallback hops (exhaustion chain)
- ✅ All fallbacks exhausted returns error response
- ✅ No chain registered for model
- ✅ Fallback disabled via request flag
- ✅ Audit metadata population
- ✅ Provider unavailable handling

## Behavior Notes

### When Fallback Triggers

Fallback activates when:
- Provider returns 429 (Too Many Requests)
- Provider returns quota exceeded error
- Any error matching rate limit patterns in `rate_limit_backoff.py`

### When Fallback Does NOT Trigger

- Network errors (connection timeout, DNS failure)
- Authentication errors (invalid API key)
- Non-rate-limit provider errors
- `request.fallback_enabled = False`

### Complexity Router Interaction

The complexity router (`tiered_routing/complexity_router.py`) disables fallback for Claude escalation requests to avoid double-fallback logic. Escalation itself is a fallback mechanism.

## Admin UI Visibility

PR #9421 adds fallback status visibility to the Admin UI:
- Current fallback state per model
- Fallback attempt history
- Quota pressure indicators

## Related Issues

- #8998 — Original feature request
- #9442 — Implementation PR
- MVA-2922 — Paperclip tracking issue
- MVA-2999 — Admin UI visibility

## Example Usage

```python
from llm_shared import get_provider_registry
from llm_shared.model_fallback_coordinator import get_fallback_coordinator
from llm_shared.models import LLMRequest

# Create request
request = LLMRequest(
    messages=[{"role": "user", "content": "Hello"}],
    model_name="claude-opus-4",
    fallback_enabled=True  # Default
)

# Execute with automatic fallback
coordinator = get_fallback_coordinator()
registry = get_provider_registry()
response = await coordinator.execute_with_fallback(request, registry)

# Check if fallback was used
if response.fallback_used:
    print(f"Fallback triggered: {response.provider_metadata['primary_model']} → {response.provider_metadata['fallback_model']}")
else:
    print("Primary model succeeded")
```

## Monitoring

Operators should monitor:
- Fallback frequency per model (indicates quota pressure)
- Fallback exhaustion events (indicates insufficient quota across entire chain)
- Average attempt count (higher = more quota pressure)

Metrics are available via:
- Application logs (search for `quota-fallback:`)
- `LLMResponse.provider_metadata` audit trail
- (Planned) Prometheus metrics in #9450
