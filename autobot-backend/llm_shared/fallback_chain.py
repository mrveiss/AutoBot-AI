# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Model fallback chain manager — auto-route to backup models on quota/rate limit.

GH#8998: When a primary model returns 429 or quota exceeded, automatically
try fallback models in sequence before failing.

Design:
  - Fallback chains are configurable per provider
  - Chains can span multiple providers (e.g., Claude → OpenAI → Ollama)
  - Exhausted chains fall back to the existing retry-with-backoff logic
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

logger = get_logger(__name__)


@dataclass
class FallbackChain:
    """Defines a fallback chain for a primary model."""

    primary_model: str
    fallback_models: List[str]
    primary_provider: Optional[str] = None
    fallback_providers: Optional[List[str]] = None

    def get_next_fallback(self, current_model: str) -> Optional[tuple[str, Optional[str]]]:
        """
        Get the next fallback model after the current one.

        Args:
            current_model: The model that just failed.

        Returns:
            Tuple of (next_model, next_provider) or None if chain exhausted.
        """
        if current_model == self.primary_model:
            # Primary failed, try first fallback
            if self.fallback_models:
                next_model = self.fallback_models[0]
                next_provider = self.fallback_providers[0] if self.fallback_providers else None
                return next_model, next_provider
            return None

        # Check if we're in the fallback chain
        try:
            idx = self.fallback_models.index(current_model)
            if idx < len(self.fallback_models) - 1:
                # There's a next fallback
                next_model = self.fallback_models[idx + 1]
                next_provider = (
                    self.fallback_providers[idx + 1]
                    if self.fallback_providers and idx + 1 < len(self.fallback_providers)
                    else None
                )
                return next_model, next_provider
        except ValueError:
            # Current model not in chain
            pass

        return None


class FallbackChainManager:
    """
    Manages fallback chains for LLM models.

    Fallback chains allow graceful degradation when a primary model hits
    rate limits or quota caps.
    """

    def __init__(self) -> None:
        self._chains: Dict[str, FallbackChain] = {}
        self._load_default_chains()
        self._load_env_chains()

    def _load_default_chains(self) -> None:
        """Load default fallback chains for common models."""
        # Anthropic Claude fallback chain
        self.register_chain(
            FallbackChain(
                primary_model="claude-opus-4",
                fallback_models=["claude-sonnet-4", "claude-haiku-4"],
                primary_provider="anthropic",
                fallback_providers=["anthropic", "anthropic"],
            )
        )

        self.register_chain(
            FallbackChain(
                primary_model="claude-sonnet-4",
                fallback_models=["claude-haiku-4"],
                primary_provider="anthropic",
                fallback_providers=["anthropic"],
            )
        )

        # OpenAI GPT fallback chain
        self.register_chain(
            FallbackChain(
                primary_model="gpt-4",
                fallback_models=["gpt-4o", "gpt-4o-mini"],
                primary_provider="openai",
                fallback_providers=["openai", "openai"],
            )
        )

        self.register_chain(
            FallbackChain(
                primary_model="gpt-4o",
                fallback_models=["gpt-4o-mini"],
                primary_provider="openai",
                fallback_providers=["openai"],
            )
        )

        # Cross-provider fallback: expensive cloud → cheaper cloud → local
        self.register_chain(
            FallbackChain(
                primary_model="claude-opus-4-cross",
                fallback_models=["gpt-4o", "ollama/llama3"],
                primary_provider="anthropic",
                fallback_providers=["openai", "ollama"],
            )
        )

        logger.info("Loaded %d default fallback chains", len(self._chains))

    def _load_env_chains(self) -> None:
        """
        Load fallback chains from environment variables.

        Env format:
          AUTOBOT_FALLBACK_CHAIN_<PRIMARY_MODEL>=fallback1,fallback2,fallback3

        Provider can be specified with provider:model format:
          AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS=anthropic:claude-sonnet-4,openai:gpt-4o
        """
        for key, value in os.environ.items():
            if not key.startswith("AUTOBOT_FALLBACK_CHAIN_"):
                continue

            primary_model_key = key.replace("AUTOBOT_FALLBACK_CHAIN_", "").lower().replace("_", "-")
            fallback_spec = value.strip()

            if not fallback_spec:
                continue

            # Parse fallback spec: "provider1:model1,provider2:model2,model3"
            fallback_models = []
            fallback_providers = []

            for part in fallback_spec.split(","):
                part = part.strip()
                if ":" in part:
                    provider, model = part.split(":", 1)
                    fallback_providers.append(provider.strip())
                    fallback_models.append(model.strip())
                else:
                    fallback_providers.append(None)  # type: ignore[arg-type]
                    fallback_models.append(part)

            chain = FallbackChain(
                primary_model=primary_model_key,
                fallback_models=fallback_models,
                fallback_providers=fallback_providers if any(fallback_providers) else None,
            )

            self.register_chain(chain)
            logger.info(
                "Loaded env fallback chain for %s: %s",
                primary_model_key,
                " → ".join(fallback_models),
            )

    def register_chain(self, chain: FallbackChain) -> None:
        """Register a fallback chain."""
        self._chains[chain.primary_model.lower()] = chain

    def get_chain(self, model: str) -> Optional[FallbackChain]:
        """Get fallback chain for a model."""
        return self._chains.get(model.lower())

    def get_next_fallback(
        self, current_model: str, current_provider: Optional[str] = None
    ) -> Optional[tuple[str, Optional[str]]]:
        """
        Get the next fallback model for the given current model.

        Args:
            current_model: The model that just failed with rate limit.
            current_provider: The provider of the current model (optional).

        Returns:
            Tuple of (next_model, next_provider) or None if no fallback available.
        """
        # Try exact match first
        chain = self.get_chain(current_model)
        if chain:
            return chain.get_next_fallback(current_model)

        # Try provider:model format
        if current_provider:
            qualified_name = f"{current_provider}:{current_model}"
            chain = self.get_chain(qualified_name)
            if chain:
                return chain.get_next_fallback(qualified_name)

        return None

    def list_chains(self) -> Dict[str, List[str]]:
        """List all registered fallback chains."""
        return {primary: chain.fallback_models for primary, chain in self._chains.items()}


# Global singleton instance
get_fallback_chain_manager = lazy_singleton(FallbackChainManager)


__all__ = ["FallbackChain", "FallbackChainManager", "get_fallback_chain_manager"]
