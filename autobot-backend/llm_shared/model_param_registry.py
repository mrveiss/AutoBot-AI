"""
YAML-driven per-model parameter registry (#3257).

Loads ``config/llm_models.yaml`` (``models:`` section) once at startup and
exposes a thin API for resolving per-model api_kwargs that are merged into
outgoing LLM requests.

Lookup precedence for api_kwargs (highest wins):
  caller-supplied metadata["api_kwargs"] > YAML provider-specific > YAML default

The YAML also records ``api_name`` (provider→model-id mapping) and ``aliases``
(alternative names resolved to the canonical ``display_name``).

Usage::

    from llm_shared.model_param_registry import get_model_kwargs, resolve_model_name

    kwargs = get_model_kwargs("claude-sonnet", provider="anthropic")
    # {"temperature": 1, "max_tokens": 8192}

    canonical = resolve_model_name("gpt4o")
    # "gpt-4o"

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss



logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YAML_PATH = Path(__file__).parent.parent / "config" / "llm_models.yaml"

# Fallback defaults applied when a model is not listed in the YAML.
_FALLBACK_KWARGS: Dict[str, Any] = {
    "temperature": 0.7,
    "max_tokens": 2048,
}

# OpenAI reasoning models reject the ``temperature`` parameter with HTTP 400.
# These canonical display_names must never receive the temperature fallback.
_NO_TEMPERATURE_MODELS: frozenset[str] = frozenset({"o1", "o1-mini", "o3", "o3-mini", "o4-mini"})

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yaml_path() -> Path:
    """Return the path to llm_models.yaml (overridable in tests via env var)."""
    override = config.llm_models_yaml
    return Path(override) if override else _YAML_PATH


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, Any]:
    """
    Load and parse the ``models:`` section from llm_models.yaml.

    Returns a dict keyed by ``display_name`` with the raw entry dict as value.
    An alias → display_name index is stored under the ``"_aliases"`` key.

    The result is memoized; call ``_load_registry.cache_clear()`` in tests.
    """
    import yaml  # PyYAML — always available in autobot-backend

    path = _yaml_path()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.warning("llm_models.yaml not found at %s — using fallback kwargs", path)
        return {"_aliases": {}}
    except Exception as exc:
        logger.error("Failed to load llm_models.yaml: %s", exc)
        return {"_aliases": {}}

    entries = raw.get("models") or []
    registry: Dict[str, Any] = {"_aliases": {}}
    for entry in entries:
        name = entry.get("display_name")
        if not name:
            logger.warning("Skipping llm_models.yaml entry without display_name: %s", entry)
            continue
        registry[name] = entry
        for alias in entry.get("aliases") or []:
            registry["_aliases"][alias] = name

    logger.debug("Loaded %d model entries from %s", len(registry) - 1, path)
    return registry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_model_name(model: str) -> str:
    """
    Resolve an alias or provider-specific name to the canonical display_name.

    If *model* is already a canonical name or is unknown, it is returned
    unchanged.
    """
    reg = _load_registry()
    aliases: Dict[str, str] = reg.get("_aliases", {})
    return aliases.get(model, model)


def get_model_kwargs(
    model: str,
    provider: str | None = None,
) -> Dict[str, Any]:
    """
    Return the merged api_kwargs for *model* from the YAML registry.

    Merge order (each layer overrides the previous):
    1. ``_FALLBACK_KWARGS`` — hardcoded baseline
    2. YAML ``api_kwargs.default`` for the model
    3. YAML ``api_kwargs.<provider>`` for the model (when *provider* given)

    Caller-supplied overrides are NOT applied here; the caller is responsible
    for merging its own values on top of the dict returned by this function.

    Args:
        model:    Canonical display_name or an alias.
        provider: Optional provider name (e.g. ``"anthropic"``, ``"openai"``).

    Returns:
        A shallow-copied dict of merged kwargs; never raises.
    """
    canonical = resolve_model_name(model)
    reg = _load_registry()
    entry = reg.get(canonical)

    if entry is None:
        logger.debug("Model %r not in registry — using fallback kwargs", model)
        return dict(_FALLBACK_KWARGS)

    api_kwargs: Dict[str, Any] = entry.get("api_kwargs") or {}
    merged: Dict[str, Any] = dict(_FALLBACK_KWARGS)
    merged.update(api_kwargs.get("default") or {})
    if provider:
        merged.update(api_kwargs.get(provider) or {})
    # Reasoning models reject the temperature parameter — strip it after merge.
    if canonical in _NO_TEMPERATURE_MODELS:
        merged.pop("temperature", None)
    return merged


def get_provider_model_id(
    model: str,
    provider: str,
) -> str:
    """
    Return the provider-specific model identifier for *model*.

    Falls back to *model* unchanged when not listed in the YAML.

    Args:
        model:    Canonical display_name or alias.
        provider: Provider name (e.g. ``"anthropic"``).

    Returns:
        The string the provider API expects (e.g. ``"claude-sonnet-4-6"``).
    """
    canonical = resolve_model_name(model)
    reg = _load_registry()
    entry = reg.get(canonical)
    if entry is None:
        return model
    api_name: Dict[str, str] = entry.get("api_name") or {}
    return api_name.get(provider, canonical)


def apply_model_defaults(
    model: str,
    provider: str | None,
    caller_kwargs: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build the final api_kwargs for a request by merging YAML defaults with
    caller-supplied overrides.

    Merge order (highest priority last):
    1. YAML fallback (baseline)
    2. YAML default kwargs for the model
    3. YAML provider-specific kwargs for the model
    4. Caller-supplied *caller_kwargs* (always wins)

    Args:
        model:         Model name or alias.
        provider:      Provider name or None.
        caller_kwargs: Optional dict already set by the caller.

    Returns:
        Merged kwargs dict.
    """
    base = get_model_kwargs(model, provider)
    if caller_kwargs:
        base.update(caller_kwargs)
    return base


def get_prompt_prefix(model: str) -> str | None:
    """
    Return the ``prompt_prefix`` configured for *model* in the YAML registry,
    or ``None`` when the field is absent or empty.
    """
    canonical = resolve_model_name(model)
    reg = _load_registry()
    entry = reg.get(canonical)
    if entry is None:
        return None
    prefix = entry.get("prompt_prefix")
    return str(prefix) if prefix else None


def apply_prompt_prefix(
    model: str,
    messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """
    Prepend the per-model ``prompt_prefix`` to the first user message.

    The list is mutated in-place; a reference to the same list is also
    returned for convenience.  When no prefix is configured, or when there is
    no user message in the list, the list is returned unchanged.
    """
    prefix = get_prompt_prefix(model)
    if not prefix:
        return messages
    for msg in messages:
        if msg.get("role") == "user":
            msg["content"] = prefix + "\n" + msg["content"]
            logger.debug(
                "Prepended prompt_prefix for model %r (%d chars)",
                model,
                len(prefix),
            )
            break
    return messages


__all__ = [
    "resolve_model_name",
    "get_model_kwargs",
    "get_provider_model_id",
    "apply_model_defaults",
    "get_prompt_prefix",
    "apply_prompt_prefix",
]
