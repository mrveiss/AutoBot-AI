# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Centralized context window management for LLM interactions.

Issue #7351: architecture_family-aware compression bypass.  Non-transformer
models (state_space, linear_attention, hybrid) carry constant inference memory
and do not face the quadratic attention cost that justifies the 4K/8K
compression trigger.  For those families the model's declared
``context_window_tokens`` is used directly as the compression threshold
instead of hard-capping at 8192.
"""

from pathlib import Path
from typing import Dict, List

_CONTEXT_HEADROOM: float = 0.85
_CONTEXT_HARD_MAX: int = 200_000

import yaml

from autobot_shared.logging_manager import get_logger
from constants.model_constants import ModelConfig, ModelConstants

logger = get_logger(__name__)

# Architecture families whose cost curve does not require transformer caps.
# "ssm" matches llm_shared.ArchitectureFamily.SSM; "state_space" is kept for
# backward-compatible YAML entries written before MVA-1379 standardised the
# enum.  Both string values bypass the 4K/8K compression trigger.
_NON_TRANSFORMER_FAMILIES: frozenset[str] = frozenset({"ssm", "state_space", "linear_attention", "hybrid"})

# Lazy singleton — imported on first call to avoid circular imports.
_compression_service = None


def _get_compression_service():
    """Return the shared ContextCompressionService instance (lazy init)."""
    global _compression_service
    if _compression_service is None:
        from services.memory.compression import ContextCompressionService

        _compression_service = ContextCompressionService()
    return _compression_service


class ContextWindowManager:
    """Manages context window budgeting for LLM models."""

    def __init__(self, config_path: str = "config/context_windows.yaml"):
        """Initialize context window manager with model configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config = self._load_config(config_path)
        self.current_model = self.config["models"]["default"]["name"]

    def _load_config(self, config_path: str) -> Dict:
        """Load model configuration from YAML.

        Args:
            config_path: Path to YAML file

        Returns:
            Configuration dictionary
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning("Config not found: %s, using defaults", config_path)
            return self._get_default_config()

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # If models is a list it's the LLM provider registry (PR #3257 schema),
            # not the context-window config dict this class expects.
            if not isinstance(config.get("models"), dict):
                logger.warning(
                    "Config %s uses list-format model registry; using context-window defaults",
                    config_path,
                )
                return self._get_default_config()

            logger.info("✅ Loaded config for %s models", len(config["models"]))
            return config
        except Exception as e:
            logger.error("Failed to load config: %s, using defaults", e)
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Fallback config if YAML not found.

        Returns:
            Default configuration dictionary
        """
        return {
            "models": {
                "default": {
                    "name": ModelConstants.DEFAULT_OLLAMA_MODEL,
                    "context_window_tokens": 4096,
                    "max_output_tokens": 2048,
                    "message_budget": {
                        "system_prompt": 500,
                        "recent_messages": 20,
                        "max_history_tokens": ModelConfig.MAX_HISTORY_TOKENS,
                    },
                },
                ModelConstants.DEFAULT_OLLAMA_MODEL: {
                    "context_window_tokens": 4096,
                    "max_output_tokens": 2048,
                    "message_budget": {
                        "system_prompt": 500,
                        "recent_messages": 20,
                        "max_history_tokens": ModelConfig.MAX_HISTORY_TOKENS,
                    },
                },
            },
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},  # nosec B105 - config dict; 'token_estimation' refers to LLM token counting, not a credential
        }

    def set_model(self, model_name: str):
        """Set active model for context management.

        Args:
            model_name: Name of the LLM model to use
        """
        if model_name not in self.config["models"]:
            logger.warning(
                "Unknown model %s, using default", model_name
            )  # codeql[py/clear-text-logging-sensitive-data]
            self.current_model = self.config["models"]["default"]["name"]
        else:
            self.current_model = model_name

        logger.info("Active model: %s", self.current_model)  # codeql[py/clear-text-logging-sensitive-data]

    def get_message_limit(self, model_name: str | None = None) -> int:
        """Get recommended message limit for model.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Number of recent messages to use for context
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]["message_budget"]["recent_messages"]

    def get_max_history_tokens(self, model_name: str | None = None) -> int:
        """Get max tokens to allocate for conversation history.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Maximum tokens for conversation history
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]["message_budget"]["max_history_tokens"]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        chars_per_token = self.config["token_estimation"]["chars_per_token"]
        return len(text) // chars_per_token

    def calculate_retrieval_limit(self, model_name: str | None = None) -> int:
        """Calculate how many messages to retrieve from Redis.

        More efficient than fetching 500 when we only use 200.
        Fetches 2x what we plan to use as a buffer for filtering.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Number of messages to retrieve from storage
        """
        message_limit = self.get_message_limit(model_name)
        # Fetch 2x what we plan to use (buffer for filtering)
        return message_limit * 2

    def should_truncate_history(self, messages: List[Dict], model_name: str | None = None) -> bool:
        """Check if message history needs truncation.

        Args:
            messages: List of message dictionaries
            model_name: Optional model name, uses current if not specified

        Returns:
            True if history should be truncated
        """
        # Calculate total characters from all message contents
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        # Estimate tokens based on character count
        estimated_tokens = total_chars // self.config["token_estimation"]["chars_per_token"]

        max_tokens = self.get_max_history_tokens(model_name)
        return estimated_tokens > max_tokens

    @staticmethod
    def _registry_family(model: str) -> str:
        """Look up architecture_family from llm_shared registry (lazy import)."""
        try:
            from llm_shared.model_param_registry import get_architecture_family as _get

            return _get(model)
        except Exception:
            return "transformer"

    def get_architecture_family(self, model_name: str | None = None) -> str:
        """Return the architecture_family for a model (defaults to 'transformer').

        Issue #7351: resolution order:
        1. ``architecture_family`` key from ``context_windows.yaml`` (normalized).
        2. ``llm_shared.get_architecture_family()`` — reads ``llm_models.yaml``
           and, optionally, HuggingFace ``config.json`` (MVA-1379).
        3. ``'transformer'`` safe default.

        Args:
            model_name: Optional model name, uses current if not specified.

        Returns:
            Architecture family string (e.g. ``'transformer'``, ``'ssm'``).
        """
        model = model_name or self.current_model
        # Issue #8360: unknown models must not inherit default model's family.
        if model not in self.config["models"]:
            return self._registry_family(model)
        raw = self.config["models"][model].get("architecture_family")
        if raw is None:
            # Entry exists but omits architecture_family — delegate to registry.
            return self._registry_family(model)
        # Issue #8361: normalize whitespace and case before frozenset check.
        return raw.strip().lower()

    def get_compression_threshold(self, model_name: str | None = None) -> int:
        """Get the compression threshold for a model.

        Issue #3770: transformer models whose context_window_tokens <= 8192
        trigger compression when retrieved content exceeds this value.

        Issue #7351: non-transformer families (state_space, linear_attention,
        hybrid) return the model's declared ``context_window_tokens`` instead of
        the 8192 default so that large-context models are not falsely capped.
        When ``context_window_tokens`` is also absent the fallback is 8192
        (same safe default as before, still transformer-conservative).

        Args:
            model_name: Optional model name, uses current if not specified.

        Returns:
            Token threshold above which compression should be applied.
        """
        model = model_name or self.current_model
        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        entry = self.config["models"][model]
        # Use the method so the llm_shared registry fallback is applied.
        family = self.get_architecture_family(model_name)

        # Issue #8359: explicit compression_threshold always wins, regardless of
        # architecture family.  Only fall back to family-specific defaults when
        # the field is absent.
        if "compression_threshold" in entry:
            return entry["compression_threshold"]

        if family in _NON_TRANSFORMER_FAMILIES:
            # Use the model's declared context window as the threshold —
            # no artificial cap for non-attention architectures.
            threshold = entry.get("context_window_tokens", 8192)
            logger.debug(
                "get_compression_threshold: %s (family=%s) → %d (no cap)",
                model,
                family,
                threshold,
            )
            return threshold

        return 8192

    def _query_known_context_length(self, model_name: str) -> int:
        """Try to get context window from llm_shared model registry. Returns 0 when unknown."""
        try:
            from llm_shared.model_param_registry import get_model_kwargs

            kwargs = get_model_kwargs(model_name)
            return int(kwargs.get("context_window_tokens", 0))
        except Exception:
            return 0

    def get_adaptive_context_length(self, model_name: str | None = None) -> int:
        """Return the effective context length for token budget calculations.

        Resolution order:
        1. Model in YAML config → return declared context_window_tokens exactly.
        2. Not in YAML → query llm_shared registry; scale by _CONTEXT_HEADROOM,
           cap at _CONTEXT_HARD_MAX.
        3. Registry also misses → YAML fallback (4096).
        """
        model = model_name or self.current_model
        if model in self.config["models"]:
            return int(self.config["models"][model].get("context_window_tokens", 4096))

        discovered = self._query_known_context_length(model)
        if discovered > 0:
            return min(int(discovered * _CONTEXT_HEADROOM), _CONTEXT_HARD_MAX)

        default_name = self.config["models"]["default"]["name"]
        return int(self.config["models"].get(default_name, {}).get("context_window_tokens", 4096))

    async def async_should_compress(self, content_tokens: int, model_name: str | None = None) -> bool:
        """Return True when content_tokens exceed the model compression threshold.

        Issue #3770: Delegates to ContextCompressionService which applies the
        large-model guard (threshold > 8192 -> always False).

        Issue #7351: non-transformer families bypass compression entirely —
        their cost curve does not justify the 4K/8K trigger.

        Args:
            content_tokens: Estimated token count of content to evaluate.
            model_name: Optional model name, uses current if not specified.

        Returns:
            True when compression should be applied.
        """
        model = model_name or self.current_model
        family = self.get_architecture_family(model)
        if family in _NON_TRANSFORMER_FAMILIES:
            logger.debug(
                "async_should_compress: %s (family=%s) → False (bypass)",
                model,  # codeql[py/clear-text-logging-sensitive-data]
                family,
            )
            return False
        svc = _get_compression_service()
        return await svc.should_compress(model, content_tokens)

    def get_model_info(self, model_name: str | None = None) -> Dict:
        """Get full model configuration.

        Args:
            model_name: Optional model name, uses current if not specified

        Returns:
            Model configuration dictionary
        """
        model = model_name or self.current_model

        if model not in self.config["models"]:
            model = self.config["models"]["default"]["name"]

        return self.config["models"][model]
