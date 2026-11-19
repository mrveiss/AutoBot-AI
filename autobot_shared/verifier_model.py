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

Memory (owner decision on #21844): a verifier model different from the chat model needs room next to it, else Ollama
evicts one of the two on every call and each pass pays a model load (a cold chat reload was measured at 74 s). So the
dedicated model is used only when the provider is Ollama AND it is already loaded (``/api/ps``, read on every pass) or
nothing else is loaded. Ollama's API reports no total or free VRAM (``/api/ps`` gives each loaded model's
``size``/``size_vram``, ``/api/tags`` an installed model's size, nothing gives the card's capacity), so "fits beside
the loaded models" cannot be measured and the rule stays conservative. Otherwise the configured chat model answers when
it is loaded (never an embedding model; else the verifier model), with the chat's ``num_ctx`` so the runner is not
reloaded for a context change. An unreadable ``/api/ps`` keeps the configured model (the earlier rule).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from autobot_shared.env_utils import env_registered
from autobot_shared.http_client import get_http_client
from autobot_shared.http_egress_guard import EGRESS_POLICY
from autobot_shared.logging_manager import get_logger
from autobot_shared.ollama_urls import ollama_ps_url
from autobot_shared.spend_recording import report_spend

logger = get_logger(__name__)

#: Where the verifier's spend is attributed (#19650).
VERIFIER_SPEND_SITE = "pre_action_verifier"

#: Seconds a model-availability reading is reused before the provider is asked again.
VERIFIER_MODEL_CHECK_TTL_S: int = env_registered("AUTOBOT_VERIFIER_MODEL_CHECK_TTL_SECONDS")

#: Seconds ``/api/ps`` may take; it is a local, in-memory listing.
_PS_TIMEOUT_S = 2.0

#: Strong references to in-flight spend recordings.
_spend_tasks: set[asyncio.Task[Any]] = set()

# model -> (monotonic time read, available: True / False / None when the list could not be read)
_readings: dict[str, tuple[float, bool | None]] = {}

# verifier model -> (monotonic time, model to ask, reuses the chat model, reason); ONLY an unreadable /api/ps is kept
_residency: dict[str, tuple[float, str, bool, str]] = {}


def configured_verifier_model(provider: Any) -> str | None:
    """The SSOT verifier model when *provider* is the local Ollama one, else None (#21844).

    The configured model names an Ollama tag; a different provider keeps its own default.
    """
    from autobot_shared.ssot_config import config
    from llm_shared.models import ProviderType

    if getattr(provider, "provider_name", None) != ProviderType.OLLAMA.value:
        return None
    # An explicitly empty AUTOBOT_VERIFIER_MODEL means the light-processing model (its registered meaning), never the
    # provider default, which is the chat model.
    return config.verifier_model or config.light_processing_model or None


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


async def loaded_models(provider: Any) -> list[str] | None:
    """Names of the models Ollama has resident now (``/api/ps``); None when that cannot be read."""
    try:
        timeout = aiohttp.ClientTimeout(total=_PS_TIMEOUT_S)
        url = ollama_ps_url(provider.resolved_base_url())
        async with await get_http_client().get(url, timeout=timeout, guard_egress=EGRESS_POLICY) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        return [str(m.get("name") or m.get("model")) for m in data.get("models", [])]
    except Exception as exc:  # noqa: BLE001 - an unreadable listing proves nothing about residency
        logger.warning("verifier residency check could not read loaded models (%s: %r)", type(exc).__name__, exc)
        return None


def _chat_model_loaded(loaded: list[str]) -> str | None:
    """The configured chat model's loaded tag, never an embedding model; None when it is not resident."""
    from autobot_shared.ssot_config import config

    chat = config.default_llm_model
    if not chat or model_listed(chat, [config.embedding_model]) or model_listed(config.embedding_model, [chat]):
        return None
    return next((name for name in loaded if model_listed(chat, [name]) or model_listed(name, [chat])), None)


def _residency_choice(model: str, loaded: list[str] | None) -> tuple[str, bool, str]:
    """``(model to ask, reuses the chat model, reason)`` from what Ollama has loaded."""
    if loaded is None:
        return model, False, "loaded models unreadable: configured verifier model"
    if any(model_listed(model, [name]) or model_listed(name, [model]) for name in loaded):
        return model, False, "verifier model already loaded"
    if not loaded:
        return model, False, "nothing else loaded"
    if (chat := _chat_model_loaded(loaded)) is not None:
        return chat, True, f"verifier model not loaded and free VRAM is unknown: reusing loaded chat model {chat!r}"
    return model, False, "other models loaded but not the chat model: configured verifier model"


async def residency_decision(provider: Any, model: str) -> tuple[str, bool, str]:
    """``(model to ask, reuses the chat model, reason)``, read from ``/api/ps`` on every pass.

    Residency changes whenever the chat model loads or is evicted, so a reading is never reused: a stale "reuse chat
    model X" or "verifier loaded" costs a cold reload (74 s measured). Only an UNREADABLE listing is remembered for
    the check TTL, so a down Ollama does not add a timeout to every pass; a failed call forgets it.
    """
    cached = _residency.get(model)
    if cached and time.monotonic() - cached[0] < VERIFIER_MODEL_CHECK_TTL_S:
        return cached[1], cached[2], cached[3]
    loaded = await loaded_models(provider)
    chosen, reuses_chat, reason = _residency_choice(model, loaded)
    if loaded is None:
        _residency[model] = (time.monotonic(), chosen, reuses_chat, reason)
    logger.debug("pre_action_verifier model: %s (%s)", chosen, reason)
    return chosen, reuses_chat, reason


async def resolve_verifier_model(provider: Any, decision: dict[str, Any] | None = None) -> str | None:
    """The model to request: the configured one when installed AND resident-or-fitting, else None / the chat model.

    *decision*, when given, receives ``reason`` and ``reuses_chat`` so the caller can record and act on the choice.
    """
    model = configured_verifier_model(provider)
    if model is None:
        return None
    if await verifier_model_available(provider, model) is False:
        logger.error(
            "pre_action_verifier: configured verifier model %r is NOT installed on the provider -- using the "
            "provider default; pull the model or change AUTOBOT_VERIFIER_MODEL",
            model,
        )
        return None
    chosen, reuses_chat, reason = await residency_decision(provider, model)
    if decision is not None:
        decision.update(reason=reason, reuses_chat=reuses_chat)
    return chosen


async def resolve_and_chat(
    provider: Any, system_prompt: str, user_prompt: str, tool_name: str, max_tokens: int, attempt: dict[str, Any]
) -> tuple[Any, Any]:
    """Resolve the model, record it in *attempt*, chat, and record the spend; returns (request, response)."""
    from autobot_shared.ssot_constants import CategoryDefaults, ModelConfig
    from llm_shared.models import LLMRequest

    decision: dict[str, Any] = {}
    attempt["model"] = await resolve_verifier_model(provider, decision)
    attempt["model_reason"] = decision.get("reason")
    # The chat model is asked with the chat's own context size: a different num_ctx makes Ollama reload the runner.
    options = {"num_ctx": ModelConfig.CHAT_NUM_CTX} if decision.get("reuses_chat") else {}
    request = LLMRequest(
        model_name=attempt["model"],
        messages=[
            {"role": CategoryDefaults.ROLE_SYSTEM, "content": system_prompt},
            {"role": CategoryDefaults.ROLE_USER, "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.1,  # Low temperature for adversarial consistency
        metadata={"purpose": "pre_action_verifier", "tool": tool_name, **options},
    )
    try:
        response = await provider.chat_completion(request)
    except BaseException:
        _residency.pop(configured_verifier_model(provider) or "", None)  # a failed call forgets the remembered reading
        raise
    if getattr(response, "error", None):
        _residency.pop(configured_verifier_model(provider) or "", None)
    # #16924 the call records itself. Not awaited: the completed reply is returned even when the verifier deadline
    # expires during accounting (awaiting would let the deadline cancel the caller and discard a reply that may block
    # the action, which fail-open then lets through). A strong reference keeps the task from being collected mid-run.
    task = asyncio.ensure_future(report_spend(response, site=VERIFIER_SPEND_SITE, metadata=request.metadata))
    _spend_tasks.add(task)
    task.add_done_callback(_spend_tasks.discard)
    return request, response


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
