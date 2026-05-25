# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Provider-agnostic model tier resolution (GH#8487).

Resolves the correct cheap (assistant) model for a given senior agent based on
provider, using a three-level precedence chain:

  1. adapterConfig.model_tier  (per-agent override)
  2. company model_tier_overrides (per-company override, stored in org settings)
  3. llc/config/model-tiers.yml (platform defaults)

Usage::

    from llc.services.model_tiers import ModelTierService

    svc = ModelTierService()
    provider = svc.detect_provider(senior_model_name)
    assistant_model = svc.resolve_assistant_model(
        senior_agent_adapter_config=adapter_cfg,
        company_overrides=company_settings.get("model_tier_overrides"),
    )
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_TIERS_YAML_PATH = Path(__file__).parent.parent / "config" / "model-tiers.yml"

# Model name prefix → provider key mapping used by detect_provider().
_MODEL_PREFIX_TO_PROVIDER: list[tuple[str, str]] = [
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("gemini-", "google"),
    ("mistral-", "mistral"),
    ("mixtral-", "mistral"),
    ("llama-", "groq"),  # Groq serves Llama by default
    ("meta-llama/", "together"),
]


@lru_cache(maxsize=1)
def _load_platform_defaults() -> Dict[str, Dict[str, str]]:
    """Load model-tiers.yml once; returns provider→{senior, assistant} dict."""
    try:
        import yaml  # PyYAML — available in autobot-backend

        with open(_TIERS_YAML_PATH) as fh:
            data = yaml.safe_load(fh) or {}
        # Keep only entries that have both senior and assistant keys.
        tiers = {}
        for provider, entry in data.items():
            if isinstance(entry, dict) and "senior" in entry and "assistant" in entry:
                tiers[provider] = {"senior": entry["senior"], "assistant": entry["assistant"]}
        return tiers
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load model-tiers.yml, using empty defaults: %s", exc)
        return {}


class ModelTierService:
    """Resolves senior / assistant model pairs for any configured provider."""

    def detect_provider(self, model: str) -> Optional[str]:
        """Infer provider key from *model* name prefix.

        Returns the provider string (e.g. ``"anthropic"``) or ``None`` when the
        model name doesn't match any known prefix.
        """
        if not model:
            return None
        model_lower = model.lower()
        for prefix, provider in _MODEL_PREFIX_TO_PROVIDER:
            if model_lower.startswith(prefix.lower()):
                return provider
        return None

    def _platform_tiers(self) -> Dict[str, Dict[str, str]]:
        return _load_platform_defaults()

    def resolve_assistant_model(
        self,
        *,
        senior_agent_adapter_config: Optional[Dict[str, Any]] = None,
        company_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Return the cheapest assistant model for the senior agent.

        Precedence:
          1. adapterConfig.model_tier.assistant  (per-agent)
          2. company_overrides[provider].assistant  (per-company)
          3. platform defaults from model-tiers.yml

        Returns ``None`` when no configuration can be found for the provider.
        """
        adapter_cfg = senior_agent_adapter_config or {}

        # Level 1: per-agent override
        agent_tier = adapter_cfg.get("model_tier") or {}
        if isinstance(agent_tier, dict) and agent_tier.get("assistant"):
            return agent_tier["assistant"]

        # Detect provider from the agent's configured model
        senior_model: str = adapter_cfg.get("model", "")
        provider = self.detect_provider(senior_model)

        if not provider:
            logger.warning("Cannot detect provider from senior model %r — no assistant model resolved", senior_model)
            return None

        # Level 2: per-company override
        if company_overrides and provider in company_overrides:
            entry = company_overrides[provider]
            if isinstance(entry, dict) and entry.get("assistant"):
                return entry["assistant"]

        # Level 3: platform defaults
        platform = self._platform_tiers()
        if provider in platform:
            return platform[provider]["assistant"]

        logger.warning("No assistant model configured for provider %r", provider)
        return None

    def resolve_senior_model(
        self,
        *,
        provider: str,
        company_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Return the senior model for *provider*.

        Uses the same precedence as resolve_assistant_model but for the senior
        slot.  Mainly used when creating a new agent from scratch.
        """
        if company_overrides and provider in company_overrides:
            entry = company_overrides[provider]
            if isinstance(entry, dict) and entry.get("senior"):
                return entry["senior"]

        platform = self._platform_tiers()
        return platform.get(provider, {}).get("senior")

    def get_tier_map(self, company_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, str]]:
        """Return the merged tier map (platform defaults + company overrides).

        Company overrides are merged on top of platform defaults per-provider.
        """
        merged = dict(self._platform_tiers())
        if company_overrides:
            for provider, entry in company_overrides.items():
                if isinstance(entry, dict):
                    merged[provider] = {**merged.get(provider, {}), **entry}
        return merged


# Module-level singleton — callers can import and use directly.
_default_service: Optional[ModelTierService] = None


def get_model_tier_service() -> ModelTierService:
    """Return the process-level ModelTierService singleton."""
    global _default_service
    if _default_service is None:
        _default_service = ModelTierService()
    return _default_service


__all__ = [
    "ModelTierService",
    "get_model_tier_service",
]
