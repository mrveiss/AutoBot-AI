---
tags: [type/reference, status/current, component/backend]
date: 2026-06-04
issue: 8998
---

# LLM Model Fallback

AutoBot automatically falls back to alternative models when the primary model returns a rate-limit (429) or quota-exceeded error. This prevents user-facing failures during quota exhaustion and enables graceful degradation across model tiers and providers.

---

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

### Key Components

- **`ModelFallbackCoordinator`** — `llm_shared/model_fallback_coordinator.py` — orchestrates fallback execution
- **`FallbackChainManager`** — manages ordered fallback chains per model
- **`ProviderRegistry`** — maps model names to provider implementations
