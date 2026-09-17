# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Category Count Computation - Extracted from knowledge.py (#16665) to
keep that file's own growth within its grandfathered line-count ceiling (#14236).

Computes and caches the per-category fact counts shown by GET /categories/main
(Issue #398). The counts are cached under one Redis key per category, shared by
every caller (1h TTL) -- so only facts visible to every authenticated user may be
counted; a per-caller filtered count would leak through the shared cache key to
every other caller (#16665).
"""

from autobot_shared.logging_manager import get_logger
from autobot_shared.scoping import ScopeLevel
from knowledge.ownership import AccessLevel

logger = get_logger(__name__)

# Cache TTL constants (seconds)
CATEGORY_CACHE_TTL = 3600  # 1 hour for category counts (expensive to compute with 5k+ facts)


def _get_fact_source(fact: dict) -> str:
    """Extract source identifier from fact for categorization (Issue #315: extracted).

    Args:
        fact: Fact dictionary with metadata

    Returns:
        Source string for category lookup
    """
    source = fact.get("metadata", {}).get("source", "") or fact.get("source", "")
    if not source:
        # Try filename or title as fallback
        source = fact.get("metadata", {}).get("filename", "") or fact.get("title", "")
    return source


async def _compute_category_counts(all_facts: list, get_category_for_source, category_counts: dict) -> None:
    """Compute category counts from facts (Issue #315: extracted).

    Args:
        all_facts: List of fact dictionaries
        get_category_for_source: Function to map source to category
        category_counts: Dict to update with counts (mutated in place)
    """
    for fact in all_facts:
        source = _get_fact_source(fact)
        main_category = get_category_for_source(source)
        if main_category in category_counts:
            category_counts[main_category] += 1


def _get_category_cache_keys(KnowledgeCategory) -> dict:
    """Get cache keys for category counts (Issue #398: extracted)."""
    return {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: "kb:stats:category:autobot-documentation",
        KnowledgeCategory.SYSTEM_KNOWLEDGE: "kb:stats:category:system-knowledge",
        KnowledgeCategory.USER_KNOWLEDGE: "kb:stats:category:user-knowledge",
    }


_UNIVERSAL_ACCESS_LEVELS = (AccessLevel.GENERAL, AccessLevel.AUTOBOT)
_UNIVERSAL_VISIBILITY_SCOPES = (ScopeLevel.SYSTEM, ScopeLevel.PUBLIC)


def _visible_to_every_authenticated_user(fact: dict) -> bool:
    """True if fact_metadata grants access to any signed-in caller, mirroring the
    caller-independent half of KnowledgeOwnership.check_access (#16665): the
    access_level bypass (GENERAL, or AUTOBOT while authenticated), else the
    visibility scope (SYSTEM/PUBLIC). Owner/org/group/shared_with grants are
    caller-specific and excluded -- they can't be true for every caller.
    """
    metadata = fact.get("metadata", {})
    access_level = metadata.get("access_level", AccessLevel.USER)
    if access_level in _UNIVERSAL_ACCESS_LEVELS:
        return True
    visibility = metadata.get("visibility", ScopeLevel.PRIVATE)
    return visibility in _UNIVERSAL_VISIBILITY_SCOPES


async def _get_or_compute_category_counts(kb, cache_keys: dict, get_category_for_source, category_counts: dict) -> None:
    """Get cached counts or compute from facts (Issue #398: extracted).

    Issue #16665: the computed counts are cached under one shared key per
    category (1h TTL) regardless of caller, so only facts visible to every
    authenticated user are counted -- otherwise the single cache entry would
    leak one caller's private/shared/group fact counts to every other caller.
    #910 already promises the 3 top-level categories are non-sensitive public
    metadata; this makes that literally true for the counts too.
    """
    cached_values = await kb.redis().mget(list(cache_keys.values()))
    if all(v is not None for v in cached_values):
        # Use cached values
        for i, cat_id in enumerate(cache_keys.keys()):
            category_counts[cat_id] = int(cached_values[i])
        logger.debug("Using cached category counts: %s", category_counts)
    else:
        # Cache miss - compute counts
        logger.info("Cache miss - computing category counts from all facts")
        all_facts = await kb.get_all_facts()
        public_facts = [fact for fact in all_facts if _visible_to_every_authenticated_user(fact)]
        logger.info("Categorizing %s facts into main categories", len(public_facts))
        await _compute_category_counts(public_facts, get_category_for_source, category_counts)
        logger.info("Category counts: %s", category_counts)
        # Cache for 1 hour
        for cat_id, cache_key in cache_keys.items():
            await kb.redis().set(cache_key, category_counts[cat_id], ex=CATEGORY_CACHE_TTL)
