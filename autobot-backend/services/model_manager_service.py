# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ModelManagerService — dynamic LLM model list from all configured providers (#3280).

Queries every registered provider via ProviderRegistry.list_models(), enriches
results with provider, context-window, and capability metadata, and caches the
combined list in Redis for 60 seconds to avoid latency on every dropdown open.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

_CACHE_KEY = "model_manager:available_models"
_CACHE_TTL = 60  # seconds — intentionally short for live-system accuracy

# Static capability + context-window hints for well-known model families.
# Values are merged into provider-discovered entries; unknown models get defaults.
_MODEL_HINTS: Dict[str, Dict[str, Any]] = {
    # Ollama / local families
    "llama": {"capabilities": ["chat", "code"], "context_window": 8192},
    "mistral": {"capabilities": ["chat", "code"], "context_window": 32768},
    "mixtral": {"capabilities": ["chat", "code"], "context_window": 32768},
    "gemma": {"capabilities": ["chat"], "context_window": 8192},
    "phi": {"capabilities": ["chat", "code"], "context_window": 4096},
    "qwen": {"capabilities": ["chat", "code"], "context_window": 32768},
    "deepseek": {"capabilities": ["chat", "code"], "context_window": 16384},
    "codellama": {"capabilities": ["code"], "context_window": 16384},
    "nomic-embed": {"capabilities": ["embedding"], "context_window": 8192},
    # OpenAI
    "gpt-4o": {"capabilities": ["chat", "code", "vision"], "context_window": 128000},
    "gpt-4-turbo": {"capabilities": ["chat", "code", "vision"], "context_window": 128000},
    "gpt-4": {"capabilities": ["chat", "code"], "context_window": 8192},
    "gpt-3.5-turbo": {"capabilities": ["chat", "code"], "context_window": 16384},
    "o1": {"capabilities": ["chat", "code", "reasoning"], "context_window": 200000},
    "o3": {"capabilities": ["chat", "code", "reasoning"], "context_window": 200000},
    "text-embedding": {"capabilities": ["embedding"], "context_window": 8192},
    # Anthropic
    "claude-opus": {"capabilities": ["chat", "code", "vision"], "context_window": 200000},
    "claude-sonnet": {"capabilities": ["chat", "code", "vision"], "context_window": 200000},
    "claude-haiku": {"capabilities": ["chat", "code"], "context_window": 200000},
}

_DEFAULT_HINTS: Dict[str, Any] = {
    "capabilities": ["chat"],
    "context_window": 4096,
}


def _hints_for_model(model_name: str) -> Dict[str, Any]:
    """Return the best-matching capability/context hints for *model_name*."""
    name_lower = model_name.lower()
    for prefix, hints in _MODEL_HINTS.items():
        if prefix in name_lower:
            return hints
    return _DEFAULT_HINTS


def _build_model_entry(
    name: str, provider: str, available: bool, extra: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Return a standardised model metadata dict."""
    from llm_shared.model_param_registry import get_architecture_family

    hints = _hints_for_model(name)
    entry: Dict[str, Any] = {
        "name": name,
        "provider": provider,
        "available": available,
        "context_window": hints["context_window"],
        "capabilities": hints["capabilities"],
        "architecture_family": get_architecture_family(name),
    }
    if extra:
        entry.update(extra)
    return entry


async def get_available_models() -> Dict[str, Any]:
    """
    Return all available models from all configured providers.

    Results are cached in Redis (database: main) for 60 seconds.  On cache
    miss, each registered provider is queried concurrently via asyncio.gather.

    Returns:
        dict with keys:
          - models: list of model metadata dicts
          - total_count: int
          - providers_queried: list of provider names
          - providers_errored: list of provider names that failed
          - cached: bool — True when the response was served from cache
    """
    # --- cache read ---
    try:
        redis = await get_async_redis_client(database="main")
        cached = await redis.get(_CACHE_KEY)
        if cached:
            data = json.loads(cached)
            data["cached"] = True
            return data
    except Exception as exc:
        logger.debug("Redis cache read failed for model list: %s", exc)

    # --- live fetch ---
    result = await _fetch_from_providers()

    # --- cache write ---
    try:
        redis = await get_async_redis_client(database="main")
        await redis.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(result))
    except Exception as exc:
        logger.debug("Redis cache write failed for model list: %s", exc)

    result["cached"] = False
    return result


async def _fetch_from_providers() -> Dict[str, Any]:
    """Query every registered provider and aggregate results."""
    import asyncio

    from llm_shared import get_provider_registry

    registry = get_provider_registry()
    providers_info = registry.list_providers()

    models: List[Dict[str, Any]] = []
    providers_errored: List[str] = []
    providers_queried: List[str] = []

    async def _query_one(name: str) -> List[Dict[str, Any]]:
        try:
            provider = registry._providers.get(name)
            if provider is None:
                return []
            names = await provider.list_models()
            available = await provider.is_available()
            return [_build_model_entry(n, name, available) for n in names]
        except Exception as exc:
            logger.warning("Failed to list models for provider %s: %s", name, exc)
            providers_errored.append(name)
            return []

    provider_names = [p["name"] for p in providers_info]
    results = await asyncio.gather(*[_query_one(n) for n in provider_names])

    seen: set[str] = set()
    for name, entries in zip(provider_names, results):
        if entries is not None:
            providers_queried.append(name)
        for entry in entries or []:
            dedup_key = f"{entry['provider']}:{entry['name']}"
            if dedup_key not in seen:
                seen.add(dedup_key)
                models.append(entry)

    return {
        "models": models,
        "total_count": len(models),
        "providers_queried": providers_queried,
        "providers_errored": providers_errored,
    }


async def get_model_names() -> List[str]:
    """Convenience wrapper — return only model name strings."""
    result = await get_available_models()
    return [m["name"] for m in result.get("models", []) if m.get("available", True)]


__all__ = ["get_available_models", "get_model_names"]
