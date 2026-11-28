# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner-stamped entity creation for ``GraphEntityExtractor`` (split out in #18825)."""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("graph_entity_extractor")


async def create_entities_in_graph(graph: Any, candidates: List[Any], owner: Any) -> List[Dict[str, Any]]:
    """Create each candidate via ``graph.create_entity`` (REUSE), stamped with ``owner``.

    A candidate that fails is logged and skipped; the rest are still written.

    Args:
        graph: AutoBotMemoryGraph
        candidates: EntityCandidate objects
        owner: REQUIRED OwnerScope -- the authenticated principal that supplied the text

    Returns:
        List of created entity data dictionaries
    """
    created_entities = []
    for candidate in candidates:
        try:
            entity = await graph.create_entity(
                entity_type=candidate.entity_type,
                name=candidate.name,
                observations=candidate.observations,
                metadata={
                    "confidence": candidate.confidence,
                    "temporal_type": (candidate.temporal_type.value if candidate.temporal_type else "unknown"),
                    "priority": "medium",
                    "status": "active",
                },
                tags=list(candidate.tags),
                owner=owner,
            )
            created_entities.append(entity)
            logger.debug("Created entity: %s", candidate.name)
        except Exception as e:
            logger.warning("Failed to create entity '%s': %s", candidate.name, e)
    return created_entities
