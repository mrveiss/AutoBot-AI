# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which model the pre-action verifier asks, and whether it is actually installed (#21844).

``AUTOBOT_VERIFIER_MODEL`` names an Ollama tag. A tag that is not pulled makes every verifier call fail, and the
fail-open default turns that into silent unverified passes. So the tag is checked against the provider's own model
list (``OllamaProvider.list_models``, the ``/api/tags`` listing): a missing model is logged loudly and the call falls
back to the provider default instead of failing every time. A list that cannot be read proves nothing, so the
configured tag is kept then.

Memory: a verifier model different from the chat model needs room next to it. When ``OLLAMA_MAX_LOADED_MODELS`` (or
VRAM) is too small, Ollama evicts one of the two on every call and each verifier pass pays a model load, which shows
up as ``timeout`` degradations.
"""

from __future__ import annotations

import time
from typing import Any

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Seconds a model-availability reading is reused before the provider is asked again.
VERIFIER_MODEL_CHECK_TTL_S: int = env_int_clamped("VERIFIER_MODEL_CHECK_TTL_SECONDS", 300, min_v=10, max_v=86400)

# model -> (monotonic time read, available: True / False / None when the list could not be read)
_readings: dict[str, tuple[float, bool | None]] = {}


def configured_verifier_model(provider: Any) -> str | None:
    """The SSOT verifier model when *provider* is the local Ollama one, else None (#21844).

    The configured model names an Ollama tag; a different provider keeps its own default.
    """
    from autobot_shared.ssot_config import config
    from llm_shared.models import ProviderType

    if getattr(provider, "provider_name", None) != ProviderType.OLLAMA.value:
        return None
    return config.verifier_model or None


def model_listed(model: str, names: list[str]) -> bool:
    """Whether *model* is among Ollama's tag *names* (a bare name means its ``:latest`` tag)."""
    return model in names or (":" not in model and f"{model}:latest" in names)


async def verifier_model_available(provider: Any, model: str) -> bool | None:
    """True/False from the provider's model list; None when it could not be read. Cached for the TTL."""
    cached = _readings.get(model)
    if cached and time.monotonic() - cached[0] < VERIFIER_MODEL_CHECK_TTL_S:
        return cached[1]
    try:
        names = [str(n) for n in await provider.list_models()]
    except Exception as exc:  # noqa: BLE001 - an unreadable list proves nothing about the model
        logger.warning("verifier model check could not list models (%s: %r)", type(exc).__name__, exc)
        names = []
    available = model_listed(model, names) if names else None
    _readings[model] = (time.monotonic(), available)
    return available


async def resolve_verifier_model(provider: Any) -> str | None:
    """The model to request: the configured one, or None (provider default) when it is not installed."""
    model = configured_verifier_model(provider)
    if model is None or await verifier_model_available(provider, model) is not False:
        return model
    logger.error(
        "pre_action_verifier: configured verifier model %r is NOT installed on the provider -- using the provider "
        "default; pull the model or change AUTOBOT_VERIFIER_MODEL",
        model,
    )
    return None


def verifier_model_status() -> dict[str, Any]:
    """The last reading per model, for the health probe: ``{model: available}`` (None = unknown)."""
    return {model: reading[1] for model, reading in _readings.items()}


async def check_verifier_model() -> tuple[str, bool | None]:
    """Startup/health check: ``(configured model, available)``; ``available`` is None when it cannot be told."""
    from llm_shared.provider_registry import get_provider_registry

    provider = await get_provider_registry().get_provider("ollama")
    model = configured_verifier_model(provider) if provider is not None else None
    if model is None:
        return "", None
    return model, await verifier_model_available(provider, model)
