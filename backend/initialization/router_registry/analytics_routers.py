# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Router Loader

This module handles loading of analytics-related API routers.
These routers provide code analytics, performance analysis, and AI-powered insights.
"""

import logging

logger = logging.getLogger(__name__)


def load_analytics_routers():
    """
    Dynamically load analytics API routers with graceful fallback.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # Main Analytics router
    try:
        from backend.api.analytics import router as analytics_router

        optional_routers.append(
            (analytics_router, "/analytics", ["analytics"], "analytics")
        )
        logger.info("✅ Optional router loaded: analytics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics - {e}")

    # Codebase Analytics router
    try:
        from backend.api.codebase_analytics import router as codebase_analytics_router

        optional_routers.append(
            (
                codebase_analytics_router,
                "/analytics",
                ["codebase-analytics"],
                "codebase_analytics",
            )
        )
        logger.info("✅ Optional router loaded: codebase_analytics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: codebase_analytics - {e}")

    # Code Evolution Timeline router (Issue #247)
    try:
        from backend.api.analytics_evolution import router as evolution_router

        optional_routers.append(
            (
                evolution_router,
                "",
                ["code-evolution", "analytics"],
                "analytics_evolution",
            )
        )
        logger.info("✅ Optional router loaded: analytics_evolution")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_evolution - {e}")

    # Technical Debt Calculator router (Issue #231)
    try:
        from backend.api.analytics_debt import router as debt_router

        optional_routers.append(
            (
                debt_router,
                "",
                ["technical-debt", "analytics"],
                "analytics_debt",
            )
        )
        logger.info("✅ Optional router loaded: analytics_debt")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_debt - {e}")

    # Real-time Code Quality Dashboard router (Issue #230)
    try:
        from backend.api.analytics_quality import router as quality_router

        optional_routers.append(
            (
                quality_router,
                "",
                ["code-quality", "analytics"],
                "analytics_quality",
            )
        )
        logger.info("✅ Optional router loaded: analytics_quality")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_quality - {e}")

    # Bug Prediction System router (Issue #224)
    try:
        from backend.api.analytics_bug_prediction import router as bug_prediction_router

        optional_routers.append(
            (
                bug_prediction_router,
                "",
                ["bug-prediction", "analytics"],
                "analytics_bug_prediction",
            )
        )
        logger.info("✅ Optional router loaded: analytics_bug_prediction")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_bug_prediction - {e}")

    # AI-Powered Code Review router (Issue #225)
    try:
        from backend.api.analytics_code_review import router as code_review_router

        optional_routers.append(
            (
                code_review_router,
                "",
                ["code-review", "analytics"],
                "analytics_code_review",
            )
        )
        logger.info("✅ Optional router loaded: analytics_code_review")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_code_review - {e}")

    # Git Pre-commit Hook Analyzer router (Issue #223)
    try:
        from backend.api.analytics_precommit import router as precommit_router

        optional_routers.append(
            (
                precommit_router,
                "",
                ["precommit", "analytics"],
                "analytics_precommit",
            )
        )
        logger.info("✅ Optional router loaded: analytics_precommit")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_precommit - {e}")

    # Performance Pattern Analysis router (Issue #222)
    try:
        from backend.api.analytics_performance import router as performance_router

        optional_routers.append(
            (
                performance_router,
                "",
                ["performance", "analytics"],
                "analytics_performance",
            )
        )
        logger.info("✅ Optional router loaded: analytics_performance")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_performance - {e}")

    # Dynamic Pattern Mining from Logs router (Issue #226)
    try:
        from backend.api.analytics_log_patterns import router as log_patterns_router

        optional_routers.append(
            (
                log_patterns_router,
                "",
                ["log-patterns", "analytics"],
                "analytics_log_patterns",
            )
        )
        logger.info("✅ Optional router loaded: analytics_log_patterns")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_log_patterns - {e}")

    # Conversation Flow Analyzer router (Issue #227)
    try:
        from backend.api.analytics_conversation import router as conversation_router

        optional_routers.append(
            (
                conversation_router,
                "",
                ["conversation-flow", "analytics"],
                "analytics_conversation",
            )
        )
        logger.info("✅ Optional router loaded: analytics_conversation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_conversation - {e}")

    # LLM-Powered Code Generation router (Issue #228)
    try:
        from backend.api.analytics_code_generation import router as code_generation_router

        optional_routers.append(
            (
                code_generation_router,
                "",
                ["code-generation", "analytics"],
                "analytics_code_generation",
            )
        )
        logger.info("✅ Optional router loaded: analytics_code_generation")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_code_generation - {e}")

    # LLM Pattern Analyzer router (Issue #229)
    try:
        from backend.api.analytics_llm_patterns import router as llm_patterns_router

        optional_routers.append(
            (
                llm_patterns_router,
                "",
                ["llm-patterns", "analytics"],
                "analytics_llm_patterns",
            )
        )
        logger.info("✅ Optional router loaded: analytics_llm_patterns")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_llm_patterns - {e}")

    # Embedding Pattern Analyzer router (Issue #285)
    try:
        from backend.api.analytics_embedding_patterns import (
            router as embedding_patterns_router,
        )

        optional_routers.append(
            (
                embedding_patterns_router,
                "/embedding-analytics",
                ["embedding-analytics", "analytics"],
                "analytics_embedding_patterns",
            )
        )
        logger.info("✅ Optional router loaded: analytics_embedding_patterns")
    except ImportError as e:
        logger.warning(
            f"⚠️ Optional router not available: analytics_embedding_patterns - {e}"
        )

    # Unified Analytics Report router (Issue #271)
    try:
        from backend.api.analytics_unified import router as unified_router

        optional_routers.append(
            (
                unified_router,
                "",
                ["unified-analytics", "analytics"],
                "analytics_unified",
            )
        )
        logger.info("✅ Optional router loaded: analytics_unified")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_unified - {e}")

    # Control Flow Graph Analyzer router (Issue #233)
    try:
        from backend.api.analytics_cfg import router as cfg_router

        optional_routers.append(
            (
                cfg_router,
                "/cfg-analytics",
                ["cfg", "analytics"],
                "analytics_cfg",
            )
        )
        logger.info("✅ Optional router loaded: analytics_cfg")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_cfg - {e}")

    # Data Flow Analysis Engine router (Issue #234)
    try:
        from backend.api.analytics_dfa import router as dfa_router

        optional_routers.append(
            (
                dfa_router,
                "/dfa-analytics",
                ["dfa", "analytics"],
                "analytics_dfa",
            )
        )
        logger.info("✅ Optional router loaded: analytics_dfa")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_dfa - {e}")

    # Pattern Learning Engine router (Issue #235)
    try:
        from backend.api.analytics_pattern_learning import (
            router as pattern_learning_router,
        )

        optional_routers.append(
            (
                pattern_learning_router,
                "/pattern-learning",
                ["pattern-learning", "analytics", "self-improving"],
                "analytics_pattern_learning",
            )
        )
        logger.info("✅ Optional router loaded: analytics_pattern_learning")
    except ImportError as e:
        logger.warning(
            f"⚠️ Optional router not available: analytics_pattern_learning - {e}"
        )

    # Architectural Pattern Recognition router (Issue #238)
    try:
        from backend.api.analytics_architecture import router as architecture_router

        optional_routers.append(
            (
                architecture_router,
                "/architecture",
                ["architecture", "analytics", "patterns"],
                "analytics_architecture",
            )
        )
        logger.info("✅ Optional router loaded: analytics_architecture")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: analytics_architecture - {e}")

    # Continuous Pattern Learning System router (Issue #239)
    try:
        from backend.api.analytics_continuous_learning import (
            router as continuous_learning_router,
        )

        optional_routers.append(
            (
                continuous_learning_router,
                "/continuous-learning",
                ["continuous-learning", "analytics", "learning"],
                "analytics_continuous_learning",
            )
        )
        logger.info("✅ Optional router loaded: analytics_continuous_learning")
    except ImportError as e:
        logger.warning(
            f"⚠️ Optional router not available: analytics_continuous_learning - {e}"
        )

    return optional_routers
