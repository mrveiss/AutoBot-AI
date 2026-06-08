# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Essential Story Generator — always-loaded compact memory summary (#3787).

Produces a short, high-quality fact summary (~300–800 tokens depending on
model tier) that is prepended to every LLM system prompt so every model
has persistent top-memories without requiring a RAG retrieval round-trip.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, List

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_YAML_PATH = Path(__file__).parent.parent / "config" / "context_windows.yaml"

# Fallback budget when model is unknown or YAML is unavailable
_DEFAULT_BUDGET = 600

# Redis cache key template — fingerprint makes any fact change invalidate the cache
_CACHE_KEY = "autobot:essential_story:{model_name}:{fingerprint}"


def _compute_facts_fingerprint(facts: list) -> str:
    """Return a SHA-256 hex digest of fact (id, content, category) tuples.

    Order-independent: sorted before hashing so reordering never invalidates.
    Any add, edit, or delete changes the digest.
    """
    items = sorted(
        (
            str(f.get("id", "")),
            str(f.get("content", "")),
            str((f.get("metadata") or {}).get("category", "")),
        )
        for f in facts
    )
    h = hashlib.sha256()
    for triple in items:
        h.update(("\x1f".join(triple) + "\x1e").encode("utf-8"))
    return h.hexdigest()


class EssentialStoryGenerator:
    """Generate a compact always-loaded memory summary for LLM system prompts."""

    async def generate(self, model_name: str | None = None) -> str:
        """Generate compact memory summary fitting the model's token budget.

        Never raises; returns empty string on any error so callers are
        unaffected when the knowledge base is unavailable.
        """
        try:
            budget = await self._get_token_budget(model_name or "default")
            facts = await self._fetch_top_facts(budget)
            fingerprint = _compute_facts_fingerprint(facts)
            cached = await self._get_cached(model_name or "default", fingerprint)
            if cached is not None:
                return cached
            story = await self._format_output(facts)
            await self._set_cached(model_name or "default", fingerprint, story)
            return story
        except Exception:
            logger.warning(
                "EssentialStoryGenerator.generate failed — returning empty string",
                exc_info=True,
            )
            return ""

    async def _get_token_budget(self, model_name: str) -> int:
        """Read essential_story_tokens from context_windows.yaml for model."""
        try:
            # #7467: was sync `_YAML_PATH.read_text` blocking the event loop.
            text = await asyncio.to_thread(_YAML_PATH.read_text, encoding="utf-8")
            data: Dict[str, Any] = yaml.safe_load(text)
            models: Dict[str, Any] = data.get("models", {})
            entry = models.get(model_name) or {}
            if "essential_story_tokens" in entry:
                return int(entry["essential_story_tokens"])
            context_tokens = int(entry.get("context_window_tokens", 0))
            if context_tokens <= 8192:
                return 300
            if context_tokens <= 32768:
                return 600
            return 800
        except Exception:
            logger.warning(
                "Could not read token budget for %s — using %d",
                model_name,  # codeql[py/clear-text-logging-sensitive-data]
                _DEFAULT_BUDGET,
            )
            return _DEFAULT_BUDGET

    def _estimate_tokens(self, text: str) -> int:
        """Approximate token count: word count * 1.3."""
        return int(len(text.split()) * 1.3)

    async def _fetch_top_facts(self, max_tokens: int) -> List[Dict[str, Any]]:
        """Query KB, sort by quality_score desc, return top facts within budget."""
        from knowledge._composed import get_knowledge_base

        kb = await get_knowledge_base()
        # Issue #3808: limit the Redis scan to 200 facts so we never do a full
        # O(n) scan.  200 provides enough headroom to find the top-quality facts
        # for any model's token budget (max 800 tokens) after sorting.
        all_facts = await kb.get_all_facts(limit=200)

        def _quality(fact: Dict[str, Any]) -> float:
            meta = fact.get("metadata") or {}
            try:
                return float(meta.get("quality_score", 0.0))
            except (TypeError, ValueError):
                return 0.0

        sorted_facts = sorted(all_facts, key=_quality, reverse=True)

        selected: List[Dict[str, Any]] = []
        used_tokens = 0
        for fact in sorted_facts:
            content = fact.get("content", "")
            tokens = self._estimate_tokens(content)
            if used_tokens + tokens > max_tokens:
                break
            selected.append(fact)
            used_tokens += tokens
        return selected

    async def _format_output(self, facts: List[Dict[str, Any]]) -> str:
        """Format facts as a compact ## Essential Context block."""
        if not facts:
            return ""
        lines = ["## Essential Context"]
        for fact in facts:
            meta = fact.get("metadata") or {}
            category = meta.get("category", "general")
            content = fact.get("content", "").strip()
            if content:
                lines.append(f"[{category}] {content}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    async def _get_cached(self, model_name: str, fingerprint: str) -> str | None:
        """Return cached story string from Redis, or None on miss/error."""
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = await get_redis_client(database="knowledge")
            key = _CACHE_KEY.format(model_name=model_name, fingerprint=fingerprint)
            value = await redis.get(key)
            if value is None:
                return None
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception:
            logger.debug("Essential story cache get failed", exc_info=True)
            return None

    async def _set_cached(self, model_name: str, fingerprint: str, story: str) -> None:
        """Write story to Redis cache with TTL_5_MINUTES TTL."""
        try:
            from autobot_shared.redis_client import get_redis_client
            from constants.ttl_constants import TTL_5_MINUTES

            redis = await get_redis_client(database="knowledge")
            key = _CACHE_KEY.format(model_name=model_name, fingerprint=fingerprint)
            await redis.setex(key, TTL_5_MINUTES, story)
        except Exception:
            logger.debug("Essential story cache set failed", exc_info=True)


__all__ = ["EssentialStoryGenerator"]
