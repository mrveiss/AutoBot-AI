# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared LLM utilities for ECL pipeline cognifiers.

Issue #1074: Extract duplicated parse/build helpers from cognifiers (ARCH-3/4).
"""

import json
import logging
from typing import Any, Dict, List

from knowledge.pipeline.models.entity import Entity

logger = logging.getLogger(__name__)


def parse_llm_json_response(
    content: str,
    *,
    fallback_dict: bool = False,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """Parse LLM response as JSON, handling markdown code fences.

    Args:
        content: Raw LLM response text.
        fallback_dict: If True, return a dict fallback on parse failure
                       (used by summarizer). Otherwise return empty list.

    Returns:
        Parsed JSON (list or dict depending on LLM output).
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        if "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        logger.warning("Could not parse LLM response as JSON")
        if fallback_dict:
            return {"summary": content, "key_topics": [], "key_entities": []}
        return []


def build_entity_map(
    entities: List[Entity],
    *,
    include_canonical: bool = True,
) -> Dict[str, Entity]:
    """Build name-to-entity lookup mapping.

    Args:
        entities: Entity list to index.
        include_canonical: Also index by canonical_name (relationship
                          extractor needs this; summarizer does not).

    Returns:
        Mapping of lowercase name -> Entity.
    """
    entity_map: Dict[str, Entity] = {}
    for entity in entities:
        entity_map[entity.name.lower()] = entity
        if include_canonical:
            entity_map[entity.canonical_name] = entity
    return entity_map
