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

---

## Hosted provider default models (#15501)

When a request names no model, each hosted provider uses its `default` tier from
`autobot_shared/ssot_hosted_models.py` (`HOSTED_PROVIDER_DEFAULT_MODELS`, provider × `default`/`light`).
These eight environment variables override the **default tier only** (the `light` tier is not
overridable this way), from the process environment or the project `.env`:

| Variable | Provider |
|---|---|
| `OPENAI_DEFAULT_MODEL` | OpenAI |
| `ANTHROPIC_DEFAULT_MODEL` | Anthropic |
| `GROQ_DEFAULT_MODEL` | Groq |
| `MISTRAL_DEFAULT_MODEL` | Mistral |
| `VERTEX_AI_DEFAULT_MODEL` | Vertex AI |
| `OPENROUTER_DEFAULT_MODEL` | OpenRouter (`vendor/model` naming) |
| `BEDROCK_DEFAULT_MODEL` | Bedrock (a friendly name from `BEDROCK_MODELS`, or a full model ID) |
| `HUGGINGFACE_DEFAULT_MODEL` | HuggingFace |

A blank value is no override. Users can still pick any model per request; these set only the
out-of-the-box choice.
