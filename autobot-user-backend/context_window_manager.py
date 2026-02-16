# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Centralized context window management for LLM interactions."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from backend.constants.model_constants import ModelConfig, ModelConstants

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """Manages context window budgeting for LLM models."""

    def __init__(self, config_path: str = "config/llm_models.yaml"):
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
            with open(path, "r") as f:
                config = yaml.safe_load(f)

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
            "token_estimation": {"chars_per_token": 4, "safety_margin": 0.9},
        }

    def set_model(self, model_name: str):
        """Set active model for context management.

        Args:
            model_name: Name of the LLM model to use
        """
        if model_name not in self.config["models"]:
            logger.warning("Unknown model %s, using default", model_name)
            self.current_model = self.config["models"]["default"]["name"]
        else:
            self.current_model = model_name

        logger.info("Active model: %s", self.current_model)

    def get_message_limit(self, model_name: Optional[str] = None) -> int:
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

    def get_max_history_tokens(self, model_name: Optional[str] = None) -> int:
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

    def calculate_retrieval_limit(self, model_name: Optional[str] = None) -> int:
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

    def should_truncate_history(
        self, messages: List[Dict], model_name: Optional[str] = None
    ) -> bool:
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
        estimated_tokens = (
            total_chars // self.config["token_estimation"]["chars_per_token"]
        )

        max_tokens = self.get_max_history_tokens(model_name)
        return estimated_tokens > max_tokens

    def get_model_info(self, model_name: Optional[str] = None) -> Dict:
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
