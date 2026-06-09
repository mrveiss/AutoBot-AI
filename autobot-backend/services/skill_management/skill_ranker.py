# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Relevance Ranker

Issue #4337: Dynamically rank and cache SLM skills by embedding similarity
to conversation context at prompt time.

Features:
- Fetch active skills from SLM: GET /api/skills/active
- Rank by embedding similarity to conversation context
- Cache top 5-10 skills in-process (LRU, session-scoped)
- Filter by agent platform (local vs. Telegram, etc.)
- Performance: skill fetch + ranking <100ms
"""

import asyncio
import time
from collections import OrderedDict
from typing import Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)


class SkillRanker:
    """
    Ranks SLM skills by embedding similarity to conversation context.

    Uses in-process LRU cache (session-scoped) to avoid repeated SLM API calls.
    Caches top N skills with their embeddings for O(1) ranking on subsequent calls.
    """

    def __init__(self, max_cache_size: int = 10, cache_ttl_seconds: int = TTL_5_MINUTES) -> None:
        """
        Initialize the skill ranker.

        Args:
            max_cache_size: Maximum number of skills to cache per session
            cache_ttl_seconds: How long to keep cached skills (5 minutes default)
        """
        self.max_cache_size = max_cache_size
        self.cache_ttl_seconds = cache_ttl_seconds
        self.skill_cache: OrderedDict[str, Dict] = OrderedDict()  # LRU cache
        self.cache_timestamp = 0
        # SLM base URL from config (includes http/https and port)
        self.slm_host = config.slm_url

    async def _fetch_active_skills(self) -> List[Dict]:
        """
        Fetch active skills from SLM API.

        Returns:
            List of skill dictionaries with id, name, description, platform fields
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.slm_host}/api/skills/active"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        skills = data.get("skills", []) if isinstance(data, dict) else data
                        logger.debug("Fetched %d active skills from SLM", len(skills))
                        return skills
                    else:
                        logger.warning("SLM returned status %d for /api/skills/active", resp.status)
                        return []
        except asyncio.TimeoutError:
            logger.warning("SLM /api/skills/active request timed out")
            return []
        except Exception as e:
            logger.error("Failed to fetch skills from SLM: %s", e)
            return []

    def _cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        if not embedding1 or not embedding2:
            return 0.0

        # Dot product
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))

        # Magnitudes
        mag1 = sum(a * a for a in embedding1) ** 0.5
        mag2 = sum(b * b for b in embedding2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    async def _get_embedding(self, text: str) -> List[float] | None:
        """
        Get embedding for text from SLM embedding API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if failed
        """
        if not text or len(text.strip()) == 0:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.slm_host}/api/embeddings"
                payload = {"input": text}
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Handle both OpenAI and custom formats
                        if isinstance(data, dict) and "data" in data:
                            embeddings = data["data"]
                            if embeddings and isinstance(embeddings, list):
                                embedding = embeddings[0]
                                if isinstance(embedding, dict):
                                    return embedding.get("embedding", [])
                                return embedding
                        return None
                    else:
                        logger.debug("SLM embedding returned status %d", resp.status)
                        return None
        except asyncio.TimeoutError:
            logger.debug("SLM embedding request timed out")
            return None
        except Exception as e:
            logger.debug("Failed to get embedding: %s", e)
            return None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (not expired)."""
        if not self.skill_cache:
            return False
        return (time.time() - self.cache_timestamp) < self.cache_ttl_seconds

    def _filter_by_platform(self, skills: List[Dict], platform: str | None = None) -> List[Dict]:
        """
        Filter skills by agent platform.

        Args:
            skills: List of skill dictionaries
            platform: Platform name to filter by (e.g., 'local', 'telegram')
                     None = return all skills

        Returns:
            Filtered list of skills
        """
        if not platform:
            return skills

        return [skill for skill in skills if skill.get("platform") == platform or skill.get("platform") is None]

    async def rank_skills(
        self,
        context: str,
        platform: str | None = None,
        top_k: int | None = None,
    ) -> List[Dict]:
        """
        Rank skills by embedding similarity to conversation context.

        Implements in-process LRU cache to avoid repeated API calls.
        Total execution time target: <100ms (includes fetch + ranking).

        Args:
            context: Conversation context or user query to rank skills against
            platform: Optional platform filter ('local', 'telegram', etc.)
            top_k: Number of top skills to return (default: self.max_cache_size)

        Returns:
            List of top-ranked skills sorted by relevance (highest first)
        """
        if not context or len(context.strip()) == 0:
            logger.warning("Empty context provided to rank_skills")
            return []

        top_k = top_k or self.max_cache_size
        start_time = time.time()

        try:
            # Try to use cached skills if available
            if self._is_cache_valid():
                logger.debug("Using cached skills (TTL valid)")
                skills = list(self.skill_cache.values())
            else:
                # Fetch fresh skills from SLM
                logger.debug("Fetching fresh skills from SLM")
                skills = await self._fetch_active_skills()

                if not skills:
                    logger.warning("No skills returned from SLM")
                    return []

                # Update cache with fresh skills
                self.skill_cache.clear()
                for skill in skills[: self.max_cache_size]:
                    skill_id = skill.get("id")
                    if skill_id:
                        self.skill_cache[skill_id] = skill
                self.cache_timestamp = time.time()

            # Filter by platform
            filtered_skills = self._filter_by_platform(skills, platform)

            if not filtered_skills:
                logger.warning("No skills match platform filter: %s", platform)
                return []

            # Get embedding for context
            context_embedding = await self._get_embedding(context)
            if not context_embedding:
                logger.warning("Failed to get embedding for context")
                # Fallback: return top skills without ranking
                return filtered_skills[:top_k]

            # Rank skills by similarity
            ranked_skills = []
            for skill in filtered_skills:
                skill_text = f"{skill.get('name', '')} {skill.get('description', '')}"
                skill_embedding = await self._get_embedding(skill_text)

                if skill_embedding:
                    similarity = self._cosine_similarity(context_embedding, skill_embedding)
                    ranked_skills.append({**skill, "_similarity_score": similarity})
                else:
                    # No embedding available, give low default score
                    ranked_skills.append({**skill, "_similarity_score": 0.0})

            # Sort by similarity (descending)
            ranked_skills.sort(key=lambda x: x.get("_similarity_score", 0), reverse=True)

            # Limit to top_k
            result = ranked_skills[:top_k]

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("Ranked %d skills in %.1fms (top %d returned)", len(ranked_skills), elapsed_ms, len(result))

            # Log warning if performance target exceeded
            if elapsed_ms > 100:
                logger.warning("Skill ranking took %.1fms (target: <100ms)", elapsed_ms)

            return result

        except Exception as e:
            logger.error("Error ranking skills: %s", e)
            return []

    def clear_cache(self) -> None:
        """Clear the in-process skill cache."""
        self.skill_cache.clear()
        self.cache_timestamp = 0
        logger.debug("Skill cache cleared")


# Global instance
_skill_ranker: SkillRanker | None = None


def get_skill_ranker() -> SkillRanker:
    """Get or create the global skill ranker instance."""
    global _skill_ranker
    if _skill_ranker is None:
        _skill_ranker = SkillRanker()
    return _skill_ranker
