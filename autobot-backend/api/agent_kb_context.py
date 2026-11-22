# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""KB context for the orchestrated-goal route, split out of ``api/agent.py`` (#16665)."""

from autobot_shared.logging_manager import get_logger
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.search_filters import filter_for_user_id

logger = get_logger(__name__)


async def _enhance_context_with_kb(payload, knowledge_base, user_id: str | None) -> str | None:
    """Enhance context with the KB facts *user_id* may read (Issue #398: extracted; #16665: scoped).

    Args:
        payload: Goal payload with context and KB settings
        knowledge_base: Knowledge base instance or None
        user_id: The calling user; none yields no KB context

    Returns:
        Augmented context string or original context
    """
    if not (payload.use_knowledge_base and knowledge_base):
        return payload.context

    try:
        # Issue #13009: exclude quarantined research facts (#12622).
        kb_results = await knowledge_base.search(query=payload.goal, top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
        kb_results = await filter_for_user_id(kb_results, knowledge_base, user_id)
        if kb_results:
            kb_context = "\n".join([f"- {item.get('content', '')[:200]}..." for item in kb_results[:3]])
            return f"{payload.context or ''}\n\nRelevant knowledge:\n{kb_context}"
    except Exception as e:
        logger.warning("Knowledge base context enhancement failed: %s", e)
    return payload.context
