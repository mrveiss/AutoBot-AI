# LLM Fallback Configuration

> **Status**: Implemented (GH#8998)
> **Last Updated**: 2026-06-04

## Overview

AutoBot automatically routes LLM requests through a fallback chain when the primary model hits a rate limit (HTTP 429) or quota cap. Instead of returning an error to the user, the system transparently retries with a backup model in sequence until one succeeds or the chain is exhausted.

**Why it exists:**

- Cloud providers impose per-minute and per-day request limits that vary by plan.
- Multi-worker deployments (multiple uvicorn workers) consume limits faster than single-process setups.
- Local models (Ollama, vLLM) serve as unlimited fallbacks for controlled-cost environments.

Fallback is distinct from retry-with-backoff: backoff waits for the same model to become available again; fallback immediately switches to a different model.

---

## Default Chains

Built-in chains are registered at startup and require no configuration to use.

### Anthropic Claude

| Primary | Fallback 1 | Fallback 2 |
|---------|-----------|-----------|
| `claude-opus-4` (anthropic) | `claude-sonnet-4` (anthropic) | `claude-haiku-4` (anthropic) |
| `claude-sonnet-4` (anthropic) | `claude-haiku-4` (anthropic) | — |

### OpenAI GPT

| Primary | Fallback 1 | Fallback 2 |
|---------|-----------|-----------|
| `gpt-4` (openai) | `gpt-4o` (openai) | `gpt-4o-mini` (openai) |
| `gpt-4o` (openai) | `gpt-4o-mini` (openai) | — |

### Cross-Provider Example (Built-in Demo)

| Primary | Fallback 1 | Fallback 2 |
|---------|-----------|-----------|
| `claude-opus-4-cross` (anthropic) | `gpt-4o` (openai) | `ollama/llama3` (ollama) |

This chain demonstrates the recommended pattern: expensive cloud → cheaper cloud → local model.

---

## Custom Configuration

### Environment Variable Format

Define a custom fallback chain for any primary model:

```
AUTOBOT_FALLBACK_CHAIN_<PRIMARY_MODEL>=<fallback_spec>
```

- `<PRIMARY_MODEL>` — the primary model name, in uppercase, with hyphens replaced by underscores.
- `<fallback_spec>` — comma-separated list of fallback models. Each entry can optionally include a provider prefix (`provider:model`).

The variable name's suffix is lowercased and underscores are converted to hyphens to form the lookup key:

```
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4  →  primary key: "claude-opus-4"
```

### Examples

**Same-provider chain (Anthropic):**

```bash
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4=anthropic:claude-sonnet-4,anthropic:claude-haiku-4
```

**Cross-provider chain (Claude → OpenAI → Local):**

```bash
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4=openai:gpt-4o,ollama:llama3
```

**OpenAI with local fallback:**

```bash
AUTOBOT_FALLBACK_CHAIN_GPT_4O=openai:gpt-4o-mini,ollama:qwen3.5:9b
```

**Without provider prefix (inherits current provider):**

```bash
AUTOBOT_FALLBACK_CHAIN_MY_CUSTOM_MODEL=my-backup-model,my-last-resort-model
```

**Full `.env` example:**

```dotenv
# Primary: claude-opus-4 → claude-sonnet-4 → gpt-4o-mini (if Anthropic quota exhausted)
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4=anthropic:claude-sonnet-4,openai:gpt-4o-mini

# Primary: gpt-4o → local Ollama as emergency fallback
AUTOBOT_FALLBACK_CHAIN_GPT_4O=openai:gpt-4o-mini,ollama:llama3
```

Environment variable chains override default chains for the same primary model key.

---

## Rate Limiter Configuration

AutoBot includes a **proactive Redis-backed token-bucket rate limiter** (GH#8170) that prevents hitting provider limits before they respond with 429. Configure per-provider thresholds with:

```
AUTOBOT_LLM_RL_<PROVIDER>_RPM=<requests_per_minute>
AUTOBOT_LLM_RL_<PROVIDER>_BURST=<burst_capacity>
```

### Built-in Defaults

| Provider | Default RPM | Default Burst |
|----------|------------|--------------|
| `openai` | 500 | 500 |
| `anthropic` | 60 | 60 |
| `groq` | 30 | 30 |
| `ollama` | 600 | 600 |
| `vllm` | 600 | 600 |
| `huggingface` | 30 | 30 |
| `openrouter` | 60 | 60 |
| `custom_openai` | 120 | 120 |

### Override Examples

```bash
# Increase Anthropic limit for a higher-tier plan
AUTOBOT_LLM_RL_ANTHROPIC_RPM=200
AUTOBOT_LLM_RL_ANTHROPIC_BURST=200

# Lower OpenAI to stay within free tier
AUTOBOT_LLM_RL_OPENAI_RPM=60
```

---

## How Fallback Is Triggered

1. A request is sent to the primary model's provider.
2. The provider returns a response containing a rate-limit signal (HTTP 429, `quota exceeded`, `too many requests`, etc.).
3. `extract_rate_limit_info()` detects the signal using pattern matching.
4. `FallbackChainManager.get_next_fallback()` returns the next model in the chain.
5. The request is re-issued to the fallback model.
6. Steps 2–5 repeat until a model succeeds or the chain is exhausted (max 10 attempts).

**Detected rate-limit patterns:**

| Pattern | Example message |
|---------|----------------|
| `rate.limit` | "Rate limit exceeded" |
| `too many requests` | "Too many requests" |
| `429` | HTTP status code |
| `quota.exceeded` | "Quota exceeded for model X" |
| `resource.exhausted` | "Resource exhausted" |
| `requests per (minute\|hour\|day)` | "60 requests per minute" |
| `token.*(per\|limit)` | "Token limit per hour reached" |
| `throttl` | "Request throttled" |

If a `retry-after` header or message field is present, its value (in seconds) is extracted and logged.

---

## Monitoring

### Log Messages

All fallback activity is logged. Set `AUTOBOT_LOG_LEVEL=debug` to see per-attempt messages.

| Level | Message | Meaning |
|-------|---------|---------|
| `debug` | `Attempting chat completion with {model} (attempt {n}/{max})` | Each model attempt |
| `info` | `Loaded {n} default fallback chains` | Startup summary |
| `info` | `Loaded env fallback chain for {model}: {chain}` | Custom chain loaded from env var |
| `info` | `Rate limit hit on {model}, falling back to {provider}:{next_model}` | Fallback activated |
| `info` | `Fallback successful: {model} worked after {n} attempts (tried: {chain})` | Successful fallback |
| `warning` | `Rate limit hit on {model} but no fallback chain configured, returning error` | No chain defined for model |
| `warning` | `Provider {provider} returned error: {error} (attempted: {chain})` | Non-rate-limit error |
| `error` | `Exhausted fallback chain after {n} attempts: {chain}` | All fallbacks failed |
| `debug` | `LLM rate limiter: Redis unavailable — allowing request (provider={provider})` | Proactive limiter degraded gracefully |

**Example log sequence for a successful fallback:**

```
DEBUG  Attempting chat completion with anthropic:claude-opus-4 (attempt 1/10)
INFO   Rate limit hit on anthropic:claude-opus-4, falling back to anthropic:claude-sonnet-4
DEBUG  Attempting chat completion with anthropic:claude-sonnet-4 (attempt 2/10)
INFO   Fallback successful: anthropic:claude-sonnet-4 worked after 2 attempts (tried: anthropic:claude-opus-4 → anthropic:claude-sonnet-4)
```

### Admin UI

The Admin UI surfaces LLM provider health and fallback status via:

- **`GET /api/llm/health/providers`** — health status for all configured providers.
- **`GET /api/llm/health/providers/{provider_name}`** — health status for a specific provider.
- **`GET /api/llm/status/comprehensive`** — full LLM status including `fallback_count` for the current session.

These endpoints require an authenticated admin session (GH#744).

### Redis Keys

The proactive rate limiter stores token-bucket state in Redis under:

```
autobot:llm:rl:{provider}
```

| Key | Example | Fields |
|-----|---------|--------|
| `autobot:llm:rl:openai` | OpenAI bucket | `tokens` (float), `ts` (timestamp) |
| `autobot:llm:rl:anthropic` | Anthropic bucket | `tokens` (float), `ts` (timestamp) |

Keys expire after 3600 seconds of inactivity.

To inspect current token levels:

```bash
redis-cli HGETALL autobot:llm:rl:anthropic
# 1) "tokens"
# 2) "57.34"
# 3) "ts"
# 4) "1749000123.45"
```

A low `tokens` value approaching 0 indicates the provider is near its rate limit.

---

## Troubleshooting

### Fallback not triggering

**Symptom:** Requests fail with a rate-limit error instead of falling back.

**Steps:**

1. Check that the primary model has a chain defined:
   ```bash
   grep AUTOBOT_FALLBACK_CHAIN .env
   ```
2. Confirm the primary model name in the env var matches exactly (with hyphens, not underscores — the suffix is converted automatically, but verify the model key):
   ```bash
   # "gpt-4o" → env var suffix is GPT_4O
   AUTOBOT_FALLBACK_CHAIN_GPT_4O=openai:gpt-4o-mini
   ```
3. Check startup logs for `Loaded env fallback chain for ...` to confirm the chain was parsed.
4. Enable debug logging to trace individual attempts:
   ```bash
   AUTOBOT_LOG_LEVEL=debug
   ```

### All fallbacks exhausted

**Symptom:** Log shows `Exhausted fallback chain after 10 attempts`.

**Steps:**

1. The chain has more models than the 10-attempt safety limit, or all models in the chain are also rate-limited.
2. Add a local model (Ollama, vLLM) as the last entry — local models have no cloud quota:
   ```bash
   AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4=anthropic:claude-sonnet-4,anthropic:claude-haiku-4,ollama:llama3
   ```
3. Check Redis token buckets to see which providers are depleted (see [Redis Keys](#redis-keys)).

### Proactive rate limiter blocking requests before 429

**Symptom:** Requests are denied locally with "Retry after Xs" before reaching the provider.

**Steps:**

1. The configured RPM is lower than your actual plan limit. Increase it:
   ```bash
   AUTOBOT_LLM_RL_ANTHROPIC_RPM=200
   ```
2. Verify Redis is reachable — if Redis is unavailable the limiter degrades gracefully (allows requests, logs a debug message).

### Redis unavailable

**Symptom:** Log shows `LLM rate limiter: Redis unavailable — allowing request`.

**Impact:** The proactive limiter is disabled. Requests proceed without token-bucket gating; provider 429 responses still trigger fallback chains normally.

**Steps:** Verify Redis connectivity per the [Redis runbook](../operations/REDIS_SERVICE_RUNBOOK.md).

### Custom chain not loaded

**Symptom:** No `Loaded env fallback chain for ...` log line at startup.

**Steps:**

1. Ensure the env var starts with `AUTOBOT_FALLBACK_CHAIN_` (exact prefix, case-sensitive).
2. Confirm the `.env` file is loaded before the backend starts.
3. Check that the value is non-empty after the `=`.

---

## Best Practices

**Always include a local model at the end of cross-provider chains.** Local Ollama or vLLM models have no cloud quota, ensuring a last-resort path that never hits a 429:

```bash
AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4=anthropic:claude-sonnet-4,openai:gpt-4o-mini,ollama:llama3
```

**Match fallback model capability to use case.** Falling back from `claude-opus-4` to `claude-haiku-4` is appropriate for most tasks but may degrade quality on complex reasoning. Evaluate whether the fallback result is acceptable for your application's workload.

**Tune RPM limits to your actual plan.** Default limits are conservative free-tier estimates. Operators on paid plans should increase limits to avoid premature proactive blocking:

```bash
AUTOBOT_LLM_RL_ANTHROPIC_RPM=200   # e.g., Anthropic Pro plan
AUTOBOT_LLM_RL_OPENAI_RPM=3000     # e.g., OpenAI Tier 4
```

**Enable Redis in production.** The cross-worker rate limiter requires Redis to correctly bound aggregate request rates across multiple uvicorn workers. Without Redis, each worker applies limits independently, allowing N× the configured rate to reach providers.

**Monitor fallback frequency.** Frequent fallbacks indicate a provider quota issue. Check `GET /api/llm/status/comprehensive` and track the `fallback_count` field. Persistent fallbacks suggest the primary model quota needs to be increased or the model selection strategy needs adjustment.

**Do not rely on fallback as the primary cost-saving mechanism.** Fallback is a reliability feature for unexpected quota spikes. For routine cost optimization, use [tiered model routing](../developer/TIERED_MODEL_ROUTING.md) to assign cheaper models to simpler tasks from the start.
