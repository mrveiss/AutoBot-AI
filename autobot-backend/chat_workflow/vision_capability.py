# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vision-capability gate for the chat continuation loop (#11538, #21770).

The model runtime's model-details endpoint (``/api/show``) reports a
``capabilities`` list per tag. That is the authority: it is read once per tag
and cached for ``CHAT_VISION_CAPABILITY_TTL_S``. The model-name substrings
(``CHAT_VISION_MODEL_PATTERNS``) are only the fallback for an endpoint that
reports no capabilities and for a failed or unreachable lookup, so a runtime
outage never fails a turn.
"""

from __future__ import annotations

import os
import time

import aiohttp

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.http_client import get_http_client
from autobot_shared.http_egress_guard import EGRESS_POLICY
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import PATH_OLLAMA_GENERATE

logger = get_logger(__name__)

# Ollama model-details endpoint (ssot_constants is at its size ceiling).
PATH_OLLAMA_SHOW = "/api/show"

# Case-insensitive substrings of a model name that indicate vision support (fallback only).
_DEFAULT_VISION_MODEL_PATTERNS = (
    "llava,vision,gpt-4o,gpt-4-vision,claude-3,claude-4,gemini,qwen-vl,qwen2-vl,qwen2.5-vl,pixtral,bakllava"
)
VISION_MODEL_NAME_PATTERNS = tuple(
    p.strip().lower()
    for p in os.getenv("CHAT_VISION_MODEL_PATTERNS", _DEFAULT_VISION_MODEL_PATTERNS).split(",")
    if p.strip()
)

# TTL of a successful capability lookup, and the (shorter) back-off after a failed one.
VISION_CAPABILITY_TTL_S = env_float("CHAT_VISION_CAPABILITY_TTL_S", default=3600.0)
VISION_CAPABILITY_FAILURE_TTL_S = env_float("CHAT_VISION_CAPABILITY_FAILURE_TTL_S", default=30.0)
VISION_CAPABILITY_LOOKUP_TIMEOUT_S = env_float("CHAT_VISION_CAPABILITY_LOOKUP_TIMEOUT_S", default=5.0)
VISION_CAPABILITY_CACHE_MAX = env_int("CHAT_VISION_CAPABILITY_CACHE_MAX", default=256)

# (base_url, model) -> (expires_at monotonic, capability or None when the lookup gave no answer)
_cache: dict[tuple[str, str], tuple[float, bool | None]] = {}


def model_name_suggests_vision(model_name: str) -> bool:
    """Name-substring heuristic: the fallback when the runtime reports no capabilities."""
    name = (model_name or "").lower()
    return any(pattern in name for pattern in VISION_MODEL_NAME_PATTERNS)


def _base_url_of(endpoint: str) -> str | None:
    """Runtime base URL from the generate endpoint the loop posts to, or None for any other endpoint."""
    if endpoint and endpoint.endswith(PATH_OLLAMA_GENERATE):
        return endpoint[: -len(PATH_OLLAMA_GENERATE)]
    return None


async def _fetch_vision_capability(base_url: str, model_name: str) -> bool | None:
    """Ask ``/api/show``; True/False when it lists capabilities, None when it cannot answer."""
    try:
        async with await get_http_client().post(
            f"{base_url}{PATH_OLLAMA_SHOW}",
            json={"model": model_name},
            timeout=aiohttp.ClientTimeout(total=VISION_CAPABILITY_LOOKUP_TIMEOUT_S),
            guard_egress=EGRESS_POLICY,
        ) as resp:
            if resp.status != 200:
                return None
            capabilities = (await resp.json()).get("capabilities")
    except Exception as exc:  # noqa: BLE001 - a failed lookup must never fail the turn
        logger.warning(
            "[Issue #21770] capability lookup failed for %r: %s",
            model_name,
            type(exc).__name__,
        )
        return None
    if not isinstance(capabilities, list):
        return None
    return "vision" in capabilities


def _remember(key: tuple[str, str], value: bool | None) -> None:
    if len(_cache) >= VISION_CAPABILITY_CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    ttl = VISION_CAPABILITY_TTL_S if value is not None else VISION_CAPABILITY_FAILURE_TTL_S
    _cache[key] = (time.monotonic() + ttl, value)


async def resolve_model_supports_vision(model_name: str, endpoint: str) -> bool:
    """True when *model_name* can take an image: runtime capabilities first, name patterns as fallback."""
    base_url = _base_url_of(endpoint)
    if not model_name or base_url is None:
        return model_name_suggests_vision(model_name)
    key = (base_url, model_name)
    cached = _cache.get(key)
    if cached is None or cached[0] <= time.monotonic():
        _remember(key, await _fetch_vision_capability(base_url, model_name))
        cached = _cache[key]
    return cached[1] if cached[1] is not None else model_name_suggests_vision(model_name)


def reset_vision_capability_cache() -> None:
    """Drop every cached lookup (tests, model pulls)."""
    _cache.clear()
