# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Essential Story Generator — always-loaded compact memory summary (#3787).

Produces a short, high-quality fact summary (~300–800 tokens depending on
model tier) that is prepended to every LLM system prompt so every model
has persistent top-memories without requiring a RAG retrieval round-trip.
"""

import asyncio
import hashlib
import math
import os
from datetime import datetime, timezone
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

# A2 (#12553): usage-aware reinforcement. The always-loaded facts are ranked by
# an effective score that boosts a fact's static ``quality_score`` by how often
# it is actually recalled (``access_count``, from A1 #12552) and how recently
# (``last_accessed``). Tunable per deployment; **weight 0 (or the flag off)
# reproduces the pre-A2 quality_score ordering** (with a deterministic fact_id
# tiebreaker so equal-quality facts no longer flip on Redis SCAN order).


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() not in ("0", "false", "no")


def _env_float(name: str, default: float) -> float:
    """Parse a float env var, never raising at import — bad values fall back."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r — using default %s", name, raw, default)
        return default
    return val if val == val else default  # reject NaN (NaN != NaN)


_REINFORCE_ENABLED: bool = _env_bool("AUTOBOT_ESSENTIAL_STORY_REINFORCE", True)
_REINFORCE_WEIGHT: float = _env_float("AUTOBOT_ESSENTIAL_STORY_REINFORCE_WEIGHT", 0.3)
_REINFORCE_RECENCY_HALFLIFE_SECONDS: float = _env_float(
    "AUTOBOT_ESSENTIAL_STORY_RECENCY_HALFLIFE_SECONDS", float(30 * 24 * 3600)
)


def _recency_factor(timestamp_iso: str | None, now: datetime) -> float:
    """Exponential-decay recency score in ``[0, 1]`` from an ISO timestamp.

    ``1.0`` for a just-now access, halving every half-life. Returns ``0.0`` when
    the timestamp is missing or unparseable so a never-accessed fact gets no
    recency boost. Mirrors ``verbatim_store._recency_factor`` (GH#11163).
    """
    if not timestamp_iso:
        return 0.0
    try:
        ts = datetime.fromisoformat(timestamp_iso)
    except (ValueError, TypeError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts).total_seconds()
    if age <= 0:
        return 1.0
    return 0.5 ** (age / _REINFORCE_RECENCY_HALFLIFE_SECONDS)


def _fact_id(fact: Dict[str, Any]) -> str:
    """Stable identifier for tie-breaking (facts carry ``fact_id``, not ``id``)."""
    return str(fact.get("fact_id") or fact.get("id") or "")


def _fact_access_count(fact: Dict[str, Any]) -> int:
    """Parsed non-negative ``access_count`` for a fact, 0 on anything unusable."""
    try:
        return max(int((fact.get("metadata") or {}).get("access_count", 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def _effective_score(fact: Dict[str, Any], now: datetime, max_access: int = 0) -> float:
    """Rank key for a fact: static quality boosted by usage + recency (A2).

    ``quality + weight * (usage_boost + recency)`` where both boost terms are
    normalised to ``[0, 1]`` — usage against the busiest fact in the candidate
    set (``max_access``) — so the reinforcement is **bounded** (max ``2*weight``)
    and cannot swamp ``quality_score``: a large quality gap always wins, while
    usage/recency break near-ties. With reinforcement disabled or ``weight <= 0``
    this collapses to the raw ``quality_score`` (pre-A2 ordering).
    """
    meta = fact.get("metadata") or {}
    try:
        quality = float(meta.get("quality_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        quality = 0.0
    if not _REINFORCE_ENABLED or _REINFORCE_WEIGHT <= 0.0:
        return quality
    access = _fact_access_count(fact)
    # Normalise usage into [0,1] against the busiest fact so the boost stays
    # bounded regardless of absolute recall counts (avoids a rich-get-richer
    # runaway where access_count dwarfs quality).
    usage_boost = math.log1p(access) / math.log1p(max_access) if max_access > 0 else 0.0
    recency_boost = _recency_factor(meta.get("last_accessed"), now)
    return quality + _REINFORCE_WEIGHT * (usage_boost + recency_boost)


def _compute_facts_fingerprint(facts: list) -> str:
    """Return a SHA-256 hex digest of the ranked fact (id, content, category) list.

    Order-**sensitive** (A2 #12553): the input is the already-ranked selection,
    so its order is part of the rendered output — a re-rank that changes the
    surfaced order must invalidate the cache. Any add, edit, delete, or reorder
    changes the digest; an identical ranked selection yields an identical digest.
    """
    h = hashlib.sha256()
    for f in facts:
        triple = (
            str(f.get("fact_id", "") or f.get("id", "")),
            str(f.get("content", "")),
            str((f.get("metadata") or {}).get("category", "")),
        )
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
                model_name,
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

        # A2 (#12553): rank by the usage-aware effective score so frequently- and
        # recently-recalled facts rise. Collapses to raw quality_score when
        # reinforcement is disabled / weight 0. A fact_id secondary key makes
        # equal-score ties deterministic (no dependence on Redis SCAN order),
        # so the order-sensitive fingerprint cache never thrashes on ties.
        now = datetime.now(tz=timezone.utc)
        max_access = max(
            (_fact_access_count(f) for f in all_facts),
            default=0,
        )
        sorted_facts = sorted(
            all_facts,
            key=lambda f: (-_effective_score(f, now, max_access), _fact_id(f)),
        )

        selected: List[Dict[str, Any]] = []
        used_tokens = 0
        for fact in sorted_facts:
            content = fact.get("content", "")
            tokens = self._estimate_tokens(content)
            if used_tokens + tokens > max_tokens:
                break
            selected.append(fact)
            used_tokens += tokens

        # A1 (#12552): reinforce the facts we actually surface to the model.
        # Fire-and-forget — never blocks or fails story generation.
        try:
            surfaced_ids = [f.get("fact_id") or f.get("id") for f in selected]
            await kb.record_fact_access([fid for fid in surfaced_ids if fid])
        except Exception:
            logger.debug("essential_story: record_fact_access skipped", exc_info=True)

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
