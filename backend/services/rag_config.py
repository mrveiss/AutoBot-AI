#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RAG Configuration Manager - Externalized configuration for advanced RAG features.

Loads configuration from config/complete.yaml under knowledge.rag section.
All reranking parameters are configurable without code changes.
"""

from dataclasses import dataclass
from typing import Any, Optional

from backend.type_defs.common import Metadata
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("rag_config")


@dataclass
class RAGConfig:
    """Configuration for Advanced RAG Optimizer."""

    # Hybrid search weights
    hybrid_weight_semantic: float = 0.7
    hybrid_weight_keyword: float = 0.3

    # Search parameters
    max_results_per_stage: int = 20
    diversity_threshold: float = 0.85
    default_max_results: int = 5

    # Context optimization
    default_context_length: int = 2000
    max_context_length: int = 5000

    # Reranking
    enable_reranking: bool = True
    reranking_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Performance
    cache_ttl_seconds: int = 300
    timeout_seconds: float = 30.0

    # Feature flags
    enable_advanced_rag: bool = True
    fallback_to_basic_search: bool = True

    def __post_init__(self):
        """Validate configuration values."""
        self._validate()

    def _validate(self):
        """Validate configuration parameters."""
        # Validate weights sum to 1.0 (or close to it)
        weight_sum = self.hybrid_weight_semantic + self.hybrid_weight_keyword
        if not (0.99 <= weight_sum <= 1.01):
            logger.warning(
                f"Hybrid weights sum to {weight_sum:.2f}, normalizing to 1.0"
            ),
            total = weight_sum
            self.hybrid_weight_semantic /= total
            self.hybrid_weight_keyword /= total

        # Validate ranges
        if not 0 <= self.hybrid_weight_semantic <= 1:
            raise ValueError(
                f"hybrid_weight_semantic must be 0-1, got {self.hybrid_weight_semantic}"
            )

        if not 0 <= self.hybrid_weight_keyword <= 1:
            raise ValueError(
                f"hybrid_weight_keyword must be 0-1, got {self.hybrid_weight_keyword}"
            )

        if not 0 <= self.diversity_threshold <= 1:
            raise ValueError(
                f"diversity_threshold must be 0-1, got {self.diversity_threshold}"
            )

        if self.max_results_per_stage < 1:
            raise ValueError(
                f"max_results_per_stage must be >= 1, got {self.max_results_per_stage}"
            )

        if self.default_max_results < 1:
            raise ValueError(
                f"default_max_results must be >= 1, got {self.default_max_results}"
            )

        if self.cache_ttl_seconds < 0:
            raise ValueError(
                f"cache_ttl_seconds must be >= 0, got {self.cache_ttl_seconds}"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {self.timeout_seconds}")

    @classmethod
    def from_dict(cls, config_dict: Metadata) -> "RAGConfig":
        """
        Create RAGConfig from dictionary.

        Args:
            config_dict: Configuration dictionary from YAML

        Returns:
            RAGConfig instance
        """
        # Extract only known fields
        known_fields = {field.name for field in cls.__dataclass_fields__.values()}
        filtered_config = {k: v for k, v in config_dict.items() if k in known_fields}

        return cls(**filtered_config)

    def to_dict(self) -> Metadata:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of config
        """
        return {
            "hybrid_weight_semantic": self.hybrid_weight_semantic,
            "hybrid_weight_keyword": self.hybrid_weight_keyword,
            "max_results_per_stage": self.max_results_per_stage,
            "diversity_threshold": self.diversity_threshold,
            "default_max_results": self.default_max_results,
            "default_context_length": self.default_context_length,
            "max_context_length": self.max_context_length,
            "enable_reranking": self.enable_reranking,
            "reranking_model": self.reranking_model,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "timeout_seconds": self.timeout_seconds,
            "enable_advanced_rag": self.enable_advanced_rag,
            "fallback_to_basic_search": self.fallback_to_basic_search,
        }


def load_rag_config_from_yaml(config_manager: Any) -> RAGConfig:
    """
    Load RAG configuration from AutoBot's config manager.

    Args:
        config_manager: AutoBot config manager instance

    Returns:
        RAGConfig instance with loaded settings
    """
    try:
        # Try to get knowledge.rag configuration
        rag_config_dict = {}

        # Get configuration with fallback to defaults
        if hasattr(config_manager, "get"):
            rag_config_dict = config_manager.get("knowledge", {}).get("rag", {})
        elif hasattr(config_manager, "config"):
            rag_config_dict = config_manager.config.get("knowledge", {}).get("rag", {})

        if rag_config_dict:
            logger.info("Loaded RAG configuration from config manager")
            return RAGConfig.from_dict(rag_config_dict)
        else:
            logger.info("No RAG configuration found, using defaults")
            return RAGConfig()

    except Exception as e:
        logger.warning("Failed to load RAG config from YAML: %s, using defaults", e)
        return RAGConfig()


# Singleton instance with thread-safe access
import threading as _threading_rag_config

_rag_config_instance: Optional[RAGConfig] = None
_rag_config_lock = _threading_rag_config.Lock()


def get_rag_config(config_manager: Optional[Any] = None) -> RAGConfig:
    """
    Get the global RAG configuration instance (thread-safe).

    Args:
        config_manager: Optional config manager to reload from

    Returns:
        RAGConfig instance
    """
    global _rag_config_instance

    if _rag_config_instance is None or config_manager is not None:
        with _rag_config_lock:
            # Double-check after acquiring lock
            if _rag_config_instance is None or config_manager is not None:
                if config_manager:
                    _rag_config_instance = load_rag_config_from_yaml(config_manager)
                else:
                    _rag_config_instance = RAGConfig()

    return _rag_config_instance


def update_rag_config(updates: Metadata) -> RAGConfig:
    """
    Update RAG configuration at runtime (thread-safe).

    Args:
        updates: Dictionary of configuration updates

    Returns:
        Updated RAGConfig instance
    """
    global _rag_config_instance

    with _rag_config_lock:
        if _rag_config_instance is None:
            _rag_config_instance = RAGConfig()

        # Update configuration
        current_config = _rag_config_instance.to_dict()
        current_config.update(updates)

        # Create new instance with updated values
        _rag_config_instance = RAGConfig.from_dict(current_config)

        logger.info("RAG configuration updated: %s", list(updates.keys()))
        return _rag_config_instance
