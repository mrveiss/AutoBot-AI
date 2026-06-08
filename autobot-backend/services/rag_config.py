#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RAG Configuration Manager - Externalized configuration for advanced RAG features.

Loads configuration from config/complete.yaml under knowledge.rag section.
All reranking parameters are configurable without code changes.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from autobot_shared.logging_manager import get_llm_logger
from constants.model_constants import model_config
from knowledge.search_components.reranking import RerankWeights
from type_defs.common import Metadata

logger = get_llm_logger("rag_config")


@dataclass
class RAGConfig:
    """
    Configuration for Advanced RAG Optimizer.

    Issue #611: Values now reference model_config constants.
    """

    # Hybrid search weights (from model_config)
    hybrid_weight_semantic: float = model_config.RAG_HYBRID_WEIGHT_SEMANTIC
    hybrid_weight_keyword: float = model_config.RAG_HYBRID_WEIGHT_KEYWORD

    # Search parameters (from model_config)
    max_results_per_stage: int = model_config.RAG_MAX_RESULTS_PER_STAGE
    diversity_threshold: float = model_config.RAG_DIVERSITY_THRESHOLD
    default_max_results: int = model_config.RAG_DEFAULT_MAX_RESULTS

    # Context optimization (from model_config)
    default_context_length: int = model_config.RAG_DEFAULT_CONTEXT_LENGTH
    max_context_length: int = model_config.RAG_MAX_CONTEXT_LENGTH

    # Reranking
    enable_reranking: bool = True
    reranking_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Issue #2004: Configurable blend weights; defaults preserve legacy 0.8/0.2 behaviour.
    rerank_weights: RerankWeights = field(default_factory=RerankWeights)
    # Issue #2090: MMR diversity pass lambda (0.0 = disabled, backward-compatible).
    mmr_lambda: float = model_config.RAG_MMR_LAMBDA

    # Performance (from model_config)
    cache_ttl_seconds: int = model_config.DEFAULT_CACHE_TTL
    timeout_seconds: float = float(model_config.DEFAULT_TIMEOUT)

    # Feature flags
    enable_advanced_rag: bool = True
    fallback_to_basic_search: bool = True

    # Neural Mesh RAG feature flags (Phase 3, Issue #2059)
    mesh_retriever_enabled: bool = False
    mesh_seed_edges: bool = True
    mesh_edge_learner: bool = False
    mesh_edge_discoverer: bool = False
    mesh_pruner: bool = False
    mesh_node_promoter: bool = False

    # EWC++ catastrophic forgetting prevention for EdgeLearner (Issue #2097)
    ewc_lambda: float = 0.4
    ewc_consolidation_interval: int = 100

    # Neural Mesh staleness propagation (Issue #2111)
    mesh_staleness_propagation: bool = False
    mesh_staleness_max_depth: int = 3
    mesh_staleness_decay: float = 0.7
    mesh_staleness_threshold: float = 0.3
    mesh_staleness_ttl: int = 3600

    # Issue #556: Category-based filtering for chat RAG
    # Default categories to search when no specific categories are specified
    # Available categories: system_knowledge, user_knowledge, autobot_knowledge
    default_chat_categories: list | None = None
    enable_smart_category_selection: bool = True

    # Issue #1718: Agentic RAG — search exposed as LLM tool
    enable_agentic_search: bool = True
    rewrite_enabled: bool = True
    max_search_iterations: int = 3

    # Issue #4696: RLM-driven refinement loop via advanced_search_with_refinement()
    enable_rlm_refinement: bool = False

    # Issue #4674: UCB1 exploration constant for RetrievalLearner pattern selection.
    # Higher values → more exploration of under-sampled patterns.
    # sqrt(2) ≈ 1.414 is the classic UCB1 constant.
    ucb1_exploration_constant: float = 1.414

    # Issue #4677: MAP-Elites structured diversity grid (opt-in, default preserves cosine behaviour)
    diversity_strategy: Literal["cosine", "map_elites"] = "cosine"

    # Issue #4678: Inject AnalyzerService lessons as supplemental RAG context
    enable_analyzer_lessons: bool = True

    # Issue #4690: Session-scoped adaptive reranking — feed per-session retrieval
    # hit/miss signals back into hybrid weights for subsequent queries in the same
    # session.  Default off for safety; enable via config or runtime update.
    enable_session_adaptive_reranking: bool = False

    # Issue #4680: Autonomous improvement loop configuration
    autonomous_loop_enabled: bool = False  # opt-in; false by default for safety
    autonomous_loop_cron: str = "0 2 * * *"  # 2 am nightly
    autonomous_loop_dry_run: bool = True  # dry-run until explicitly disabled
    autonomous_loop_promotion_threshold: float = 0.05  # 5 % improvement required

    def __post_init__(self) -> None:
        """Validate configuration values and propagate mmr_lambda to rerank_weights.

        Issue #2090: top-level mmr_lambda is the canonical knob for the MMR pass.
        When it differs from rerank_weights.mmr_lambda (i.e. user set it at the
        top level only), propagate it into rerank_weights so ResultReranker sees it.
        """
        if self.mmr_lambda != 0.0 and self.rerank_weights.mmr_lambda == 0.0:
            self.rerank_weights.mmr_lambda = self.mmr_lambda
        self._validate()

    def _validate(self) -> None:
        """Validate configuration parameters."""
        # Validate weights sum to 1.0 (or close to it)
        weight_sum = self.hybrid_weight_semantic + self.hybrid_weight_keyword
        if not (0.99 <= weight_sum <= 1.01):
            logger.warning("Hybrid weights sum to %.2f, normalizing to 1.0", weight_sum)
            self.hybrid_weight_semantic /= weight_sum
            self.hybrid_weight_keyword /= weight_sum

        # Validate ranges
        if not 0 <= self.hybrid_weight_semantic <= 1:
            raise ValueError(f"hybrid_weight_semantic must be 0-1, got {self.hybrid_weight_semantic}")

        if not 0 <= self.hybrid_weight_keyword <= 1:
            raise ValueError(f"hybrid_weight_keyword must be 0-1, got {self.hybrid_weight_keyword}")

        if not 0 <= self.diversity_threshold <= 1:
            raise ValueError(f"diversity_threshold must be 0-1, got {self.diversity_threshold}")

        if self.max_results_per_stage < 1:
            raise ValueError(f"max_results_per_stage must be >= 1, got {self.max_results_per_stage}")

        if self.default_max_results < 1:
            raise ValueError(f"default_max_results must be >= 1, got {self.default_max_results}")

        if self.cache_ttl_seconds < 0:
            raise ValueError(f"cache_ttl_seconds must be >= 0, got {self.cache_ttl_seconds}")

        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {self.timeout_seconds}")

        if self.ewc_lambda < 0:
            raise ValueError(f"ewc_lambda must be >= 0, got {self.ewc_lambda}")

        if self.ewc_consolidation_interval < 1:
            raise ValueError(f"ewc_consolidation_interval must be >= 1, got {self.ewc_consolidation_interval}")

        if not 0.0 <= self.mmr_lambda <= 1.0:
            raise ValueError(f"mmr_lambda must be in [0, 1], got {self.mmr_lambda}")

        # Issue #1718: Agentic search iteration guard
        if self.max_search_iterations < 1:
            raise ValueError(f"max_search_iterations must be >= 1, got {self.max_search_iterations}")

    @classmethod
    def from_dict(cls, config_dict: Metadata) -> "RAGConfig":
        """
        Create RAGConfig from dictionary.

        Issue #2004: Deserialises the nested ``rerank_weights`` sub-dict into
        a RerankWeights dataclass so callers can pass plain YAML structures.

        Args:
            config_dict: Configuration dictionary from YAML

        Returns:
            RAGConfig instance
        """
        # Extract only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_config = {k: v for k, v in config_dict.items() if k in known_fields}

        # Deserialise nested RerankWeights when the value is a plain dict.
        if isinstance(filtered_config.get("rerank_weights"), dict):
            filtered_config["rerank_weights"] = RerankWeights(**filtered_config["rerank_weights"])

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
            # Issue #2004: serialise as a plain dict for YAML round-trips.
            # Issue #2111: staleness weight added.
            "rerank_weights": {
                "reranker": self.rerank_weights.reranker,
                "vector": self.rerank_weights.vector,
                "edge": self.rerank_weights.edge,
                "recency": self.rerank_weights.recency,
                "staleness": self.rerank_weights.staleness,
                "mmr_lambda": self.rerank_weights.mmr_lambda,
            },
            # Issue #2090: top-level MMR lambda (mirrors rerank_weights.mmr_lambda).
            "mmr_lambda": self.mmr_lambda,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "timeout_seconds": self.timeout_seconds,
            "enable_advanced_rag": self.enable_advanced_rag,
            "fallback_to_basic_search": self.fallback_to_basic_search,
            "default_chat_categories": self.default_chat_categories,
            "enable_smart_category_selection": self.enable_smart_category_selection,
            # Issue #1718: Agentic RAG feature flags
            "enable_agentic_search": self.enable_agentic_search,
            "rewrite_enabled": self.rewrite_enabled,
            "max_search_iterations": self.max_search_iterations,
            # Issue #4696: RLM-driven refinement loop
            "enable_rlm_refinement": self.enable_rlm_refinement,
            # Issue #4674: UCB1 exploration constant for RetrievalLearner
            "ucb1_exploration_constant": self.ucb1_exploration_constant,
            # Neural Mesh RAG feature flags (Issue #2059)
            "mesh_retriever_enabled": self.mesh_retriever_enabled,
            "mesh_seed_edges": self.mesh_seed_edges,
            "mesh_edge_learner": self.mesh_edge_learner,
            "mesh_edge_discoverer": self.mesh_edge_discoverer,
            "mesh_pruner": self.mesh_pruner,
            "mesh_node_promoter": self.mesh_node_promoter,
            # EWC++ catastrophic forgetting prevention (Issue #2097)
            "ewc_lambda": self.ewc_lambda,
            "ewc_consolidation_interval": self.ewc_consolidation_interval,
            # Neural Mesh staleness propagation (Issue #2111)
            "mesh_staleness_propagation": self.mesh_staleness_propagation,
            "mesh_staleness_max_depth": self.mesh_staleness_max_depth,
            "mesh_staleness_decay": self.mesh_staleness_decay,
            "mesh_staleness_threshold": self.mesh_staleness_threshold,
            "mesh_staleness_ttl": self.mesh_staleness_ttl,
            # Issue #4677: MAP-Elites diversity strategy
            "diversity_strategy": self.diversity_strategy,
            # Issue #4678: AnalyzerService lesson injection
            "enable_analyzer_lessons": self.enable_analyzer_lessons,
            # Issue #4690: Session-scoped adaptive reranking
            "enable_session_adaptive_reranking": self.enable_session_adaptive_reranking,
            # Issue #4680: Autonomous improvement loop
            "autonomous_loop_enabled": self.autonomous_loop_enabled,
            "autonomous_loop_cron": self.autonomous_loop_cron,
            "autonomous_loop_dry_run": self.autonomous_loop_dry_run,
            "autonomous_loop_promotion_threshold": self.autonomous_loop_promotion_threshold,
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

_rag_config_instance: RAGConfig | None = None
_rag_config_lock = _threading_rag_config.Lock()


def get_rag_config(config_manager: Any | None = None) -> RAGConfig:
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
