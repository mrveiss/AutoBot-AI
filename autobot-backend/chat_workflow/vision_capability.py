# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision-capability gate for the chat continuation loop (#11538, #21770).

Ollama's ``/api/show`` returns a ``capabilities`` list that contains
``"vision"`` for vision models. That list is the source of truth; matching the
model *name* against a pattern list (the previous, only gate) is kept purely
as the fallback when the lookup has not run or failed.
"""

from __future__ import annotations

import os
import time

import aiohttp

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# How long a model's /api/show capability answer is trusted (seconds).
VISION_CAPABILITY_CACHE_TTL_S = env_int("CHAT_VISION_CAPABILITY_CACHE_TTL_S", default=3600)
# Bound on the /api/show call so a slow Ollama never stalls the turn.
VISION_CAPABILITY_LOOKUP_TIMEOUT_S = env_float("CHAT_VISION_CAPABILITY_LOOKUP_TIMEOUT_S", default=5.0)

# Case-insensitive substrings of a model name that indicate vision support;
# used only when /api/show gave no answer.
_DEFAULT_VISION_MODEL_PATTERNS = (
    "llava,vision,gpt-4o,gpt-4-vision,claude-3,claude-4,gemini,qwen-vl,qwen2-vl,qwen2.5-vl,pixtral,bakllava"
)
VISION_MODEL_NAME_PATTERNS = tuple(
    p.strip().lower()
    for p in os.getenv("CHAT_VISION_MODEL_PATTERNS", _DEFAULT_VISION_MODEL_PATTERNS).split(",")
    if p.strip()
)

# (endpoint, model) -> (expires_at_monotonic, supports_vision)
_capability_cache: dict[tuple[str, str], tuple[float, bool]] = {}


def _cached_capability(model_name: str) -> bool | None:
    """Return the unexpired cached verdict for *model_name* on any endpoint."""
    now = time.monotonic()
    for (_, model), (expires, verdict) in _capability_cache.items():
        if model == model_name and expires > now:
            return verdict
    return None


def model_supports_vision(model_name: str) -> bool:
    """Capability verdict from the /api/show cache, else the name-pattern fallback."""
    name = (model_name or "").lower()
    if not name:
        return False
    cached = _cached_capability(model_name)
    if cached is not None:
        return cached
    return any(pattern in name for pattern in VISION_MODEL_NAME_PATTERNS)


async def refresh_vision_capability(http_client, ollama_endpoint: str, model_name: str) -> None:
    """Populate the capability cache from Ollama ``/api/show`` (#21770).

    Failures are logged and leave the cache untouched, so the name-pattern
    fallback in :func:`model_supports_vision` decides.
    """
    key = (ollama_endpoint, model_name)
    entry = _capability_cache.get(key)
    if not model_name or not ollama_endpoint or (entry and entry[0] > time.monotonic()):
        return
    try:
        timeout = aiohttp.ClientTimeout(total=VISION_CAPABILITY_LOOKUP_TIMEOUT_S)
        async with await http_client.post(
            f"{ollama_endpoint.rstrip('/')}/api/show", json={"model": model_name}, timeout=timeout
        ) as resp:
            if resp.status != 200:
                logger.debug("vision capability lookup for %s: HTTP %s", model_name, resp.status)
                return
            caps = (await resp.json()).get("capabilities")
    except Exception as exc:  # noqa: BLE001 - lookup is advisory; fall back to name patterns
        logger.debug("vision capability lookup for %s failed: %s", model_name, exc)
        return
    if isinstance(caps, list):
        _capability_cache[key] = (time.monotonic() + VISION_CAPABILITY_CACHE_TTL_S, "vision" in caps)
