# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source Router (#12625, design §4.4) — topic-based provider selection.

Maps a sub-question's inferred topic to a preferred provider in the existing
``SearchProviderRegistry`` (``agent_loop/search/registry.py``): a specialized
source (config-declared or a Python provider that declares
``supported_categories``) is preferred when one is registered for that topic;
otherwise the registry's normal credential-gated, graceful-fallback provider
order is used unchanged (design: "Preserve the registry's credential-gating
+ graceful fallback"). This module never re-implements that logic — it only
supplies the registry's existing ``provider=`` preferred-candidate parameter.

Topic-inference scope note (#12625 premise finding): the merged Planner
(#12624, PR #13014) does not tag sub-questions with a topic —
``services.research.planner.SubQuestion`` carries only ``text`` /
``expected_value``. Expanding the Planner's LLM decomposition prompt to also
classify topic is out of scope here (a larger, already-merged/tested module,
and an LLM round-trip per sub-question the design's efficiency goal argues
against). Design §4.4 asks the Router to map a sub-question's *inferred*
topic to providers — this module does that inference itself, cheaply and
deterministically (keyword match, see ``config/research_topics.yaml``), which
is a legitimate, narrower reading of "inferred" than "pre-tagged by the
Planner". See the discovered-gap issue filed alongside this PR for wiring
topic-tagging into the Planner directly.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import yaml

from agent_loop.search.base import CATEGORY_ACADEMIC, CATEGORY_CODE, CATEGORY_GENERAL, CATEGORY_NEWS, SearchResult
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_DEFAULT_TOPICS_CONFIG = os.path.join(os.path.dirname(__file__), "..", "..", "config", "research_topics.yaml")

# Built-in fallback when config/research_topics.yaml is missing/empty/malformed
# (never blocks startup — matches agent_loop.search.registry's population style).
_BUILTIN_TOPIC_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    CATEGORY_ACADEMIC: ("study", "research", "paper", "journal", "theorem", "hypothesis", "experiment"),
    CATEGORY_CODE: ("code", "function", "library", "programming", "framework", "compile", "syntax"),
    CATEGORY_NEWS: ("news", "today", "yesterday", "breaking", "announced", "latest"),
}

_topic_keywords_cache: Optional[Dict[str, Tuple[str, ...]]] = None


def _load_topic_keywords(config_path: Optional[str] = None) -> Dict[str, Tuple[str, ...]]:
    """Load the topic->keyword map from ``research_topics.yaml`` (never raises)."""
    path = config_path or _DEFAULT_TOPICS_CONFIG
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return _BUILTIN_TOPIC_KEYWORDS
    except Exception as exc:  # noqa: BLE001 — a broken config file must never block startup
        logger.warning("research_topics.yaml: failed to load %s: %s", path, exc)
        return _BUILTIN_TOPIC_KEYWORDS
    topics = raw.get("topics", {})
    if not isinstance(topics, dict) or not topics:
        return _BUILTIN_TOPIC_KEYWORDS
    parsed = {
        str(topic): tuple(str(w).lower() for w in words)
        for topic, words in topics.items()
        if isinstance(words, list) and words
    }
    return parsed or _BUILTIN_TOPIC_KEYWORDS


def _topic_keywords() -> Dict[str, Tuple[str, ...]]:
    """Return the process-wide topic->keyword map, loading it once lazily."""
    global _topic_keywords_cache
    if _topic_keywords_cache is None:
        _topic_keywords_cache = _load_topic_keywords()
    return _topic_keywords_cache


def infer_topic(text: str) -> str:
    """Infer a coarse topic for *text* from keyword substring match.

    Deterministic and never raises — an unmatched or empty question always
    degrades to ``CATEGORY_GENERAL`` (the unchanged default fallback path).
    """
    lowered = text.lower()
    for topic, keywords in _topic_keywords().items():
        if any(keyword in lowered for keyword in keywords):
            return topic
    return CATEGORY_GENERAL


def _preferred_provider_for_topic(topic: str) -> Optional[str]:
    """Return the first registered provider whose ``supported_categories``
    contains *topic*, or None (the registry's default order applies unchanged).
    """
    if topic == CATEGORY_GENERAL:
        return None

    from agent_loop.search.registry import get_search_registry  # noqa: PLC0415

    registry = get_search_registry()
    for name in registry.list_providers():
        provider = registry.get_provider(name)
        if provider is not None and topic in getattr(provider, "supported_categories", ()):
            return name
    return None


async def route_search(query: str, *, count: int) -> List[SearchResult]:
    """Route *query* to its specialized provider (if any) via the shared registry.

    Registry credential-gating + graceful per-provider fallback (#9022/#9023)
    are entirely unchanged: this only supplies the *preferred* provider name.
    ``SearchProviderRegistry.search`` still tries the full fallback chain if
    the preferred provider is unavailable or errors, and falls back to the
    default order untouched when no specialization matches (design: "default
    to general web when nothing matches").
    """
    from agent_loop.search.registry import search as registry_search  # noqa: PLC0415

    topic = infer_topic(query)
    preferred = _preferred_provider_for_topic(topic)
    if preferred:
        logger.debug("router.route_search: topic=%r routed to specialized provider=%r", topic, preferred)
    return await registry_search(query, provider=preferred, category=topic, count=count)
