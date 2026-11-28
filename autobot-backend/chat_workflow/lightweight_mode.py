# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a turn qualifies for lightweight mode (MVA-1992).

Split out of ``ChatWorkflowManager._prepare_llm_workflow_params`` (#20195) to keep ``manager.py`` under
its size ceiling; the decision is unchanged.
"""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def decide_lightweight_mode(messages: list[dict]) -> bool:
    """True when the complexity tier marks the turn (*messages*) trivial, or simple with no trivial tier.

    Trivial tier (GH#9050, score < trivial_threshold) is the primary signal; simple tier (score <
    complexity_threshold) is the fallback when trivial tier is not configured. Non-fatal: a routing failure
    means full mode.
    """
    lightweight_mode = False
    try:
        from llm_shared.tiered_routing.complexity_router import ComplexityRouter
        from llm_shared.tiered_routing.tier_config import TierConfig

        tier_config = TierConfig.from_config()
        if tier_config.enabled:
            router = ComplexityRouter(config=tier_config)
            _, complexity_result = router.route(messages)
            # Trivial tier is the canonical lightweight signal (GH#9050).
            # Fall back to simple tier when trivial is not configured.
            is_trivial = complexity_result.tier == "trivial"
            is_simple_fallback = complexity_result.tier == "simple" and not getattr(tier_config.models, "trivial", "")
            lightweight_mode = is_trivial or is_simple_fallback
            if lightweight_mode:
                logger.info(
                    "[MVA-1992] Lightweight mode enabled (tier=%s, score=%.1f)",
                    complexity_result.tier,
                    complexity_result.score,
                )
    except Exception as e:
        logger.warning("[MVA-1992] Complexity routing failed, defaulting to full mode: %s", e)
    return lightweight_mode
