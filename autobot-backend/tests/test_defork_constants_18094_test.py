# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094 slice A: one owner per constant, pinned by identity."""

import inspect

from autobot_shared.ssot_constants import ModelConfig, QueryDefaults


def test_rag_default_results_is_an_alias_of_the_canonical():
    assert QueryDefaults.RAG_DEFAULT_RESULTS is ModelConfig.RAG_DEFAULT_MAX_RESULTS
    assert "RAG_DEFAULT_MAX_RESULTS" in inspect.getsource(QueryDefaults)


def test_advanced_rag_optimizer_reads_the_hybrid_weights_from_model_config():
    from advanced_rag_optimizer import AdvancedRAGOptimizer
    from constants.model_constants import model_config

    opt = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    opt._init_search_config()

    assert opt.hybrid_weight_semantic == model_config.RAG_HYBRID_WEIGHT_SEMANTIC
    assert opt.hybrid_weight_keyword == model_config.RAG_HYBRID_WEIGHT_KEYWORD
    assert opt.max_results_per_stage == model_config.RAG_MAX_RESULTS_PER_STAGE
    assert opt.diversity_threshold == model_config.RAG_DIVERSITY_THRESHOLD
    src = inspect.getsource(AdvancedRAGOptimizer._init_search_config)
    assert "0.7" not in src and "0.85" not in src


def test_global_user_sentinel_has_one_owner():
    from constants import user_scope_constants as owner
    from knowledge import rag_benchmarks
    from knowledge.search_components import retrieval_learner
    from services import feedback_aggregator

    assert retrieval_learner.GLOBAL_USER is owner.GLOBAL_USER
    assert rag_benchmarks._BENCHMARK_USER is owner.GLOBAL_USER
    assert feedback_aggregator.GLOBAL_USER is owner.GLOBAL_USER
