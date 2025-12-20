# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base ML-Based Suggestions Module

Issue #413: Implements embedding-based suggestions for tags and categories.

Uses existing embeddings to find similar documents and extract suggestions
from them weighted by similarity score.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


class SuggestionsMixin:
    """
    ML-based suggestions mixin for knowledge base.

    Issue #413: Provides intelligent tag and category suggestions using
    embedding-based similarity search.

    Approach:
    - Find similar documents using vector embeddings
    - Extract tags/categories from similar documents
    - Weight suggestions by document similarity scores
    - Return suggestions with confidence scores

    Key Features:
    - No additional model needed - uses existing embeddings
    - Confidence scores based on similarity and frequency
    - Configurable minimum confidence thresholds
    - Support for auto-application of high-confidence suggestions
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"
    vector_store: "ChromaVectorStore"
    initialized: bool

    # Configuration constants
    DEFAULT_SIMILARITY_LIMIT = 20  # Number of similar docs to analyze
    DEFAULT_MIN_CONFIDENCE = 0.3  # Minimum confidence to include
    DEFAULT_AUTO_APPLY_THRESHOLD = 0.85  # Auto-apply if >= this confidence

    def _validate_content(self, content: str) -> Dict[str, Any]:
        """Validate content input for suggestions (Issue #398: extracted)."""
        if not content or not content.strip():
            return {"success": False, "suggestions": [], "error": "Content is required"}
        return None

    def _no_similar_docs_response(self) -> Dict[str, Any]:
        """Return response when no similar docs found (Issue #398: extracted)."""
        return {
            "success": True,
            "suggestions": [],
            "similar_docs_analyzed": 0,
            "message": "No similar documents found for analysis",
        }

    async def suggest_tags(
        self, content: str, limit: int = 5, min_confidence: float = 0.3,
        similarity_limit: int = 20
    ) -> Dict[str, Any]:
        """Suggest tags for content based on similar documents (Issue #398: refactored)."""
        self.ensure_initialized()

        error_response = self._validate_content(content)
        if error_response:
            return error_response

        try:
            similar_docs = await self._find_similar_documents(content, similarity_limit)
            if not similar_docs:
                return self._no_similar_docs_response()

            tag_scores = await self._extract_weighted_tags(similar_docs)
            suggestions = self._build_suggestions_list(tag_scores, limit, min_confidence)

            logger.info(
                "Generated %d tag suggestions from %d similar documents",
                len(suggestions), len(similar_docs),
            )
            return {
                "success": True,
                "suggestions": suggestions,
                "similar_docs_analyzed": len(similar_docs),
            }

        except Exception as e:
            logger.error("Failed to suggest tags: %s", e)
            return {"success": False, "suggestions": [], "error": str(e)}

    async def suggest_categories(
        self, content: str, limit: int = 3, min_confidence: float = 0.3,
        similarity_limit: int = 20
    ) -> Dict[str, Any]:
        """Suggest categories based on similar documents (Issue #398: refactored)."""
        self.ensure_initialized()

        error_response = self._validate_content(content)
        if error_response:
            return error_response

        try:
            similar_docs = await self._find_similar_documents(content, similarity_limit)
            if not similar_docs:
                return self._no_similar_docs_response()

            category_scores = await self._extract_weighted_categories(similar_docs)
            suggestions = self._build_category_suggestions_list(
                category_scores, limit, min_confidence
            )

            logger.info(
                "Generated %d category suggestions from %d similar documents",
                len(suggestions), len(similar_docs),
            )
            return {
                "success": True,
                "suggestions": suggestions,
                "similar_docs_analyzed": len(similar_docs),
            }

        except Exception as e:
            logger.error("Failed to suggest categories: %s", e)
            return {"success": False, "suggestions": [], "error": str(e)}

    def _empty_suggestion_response(self, error: str = None) -> Dict[str, Any]:
        """Build empty suggestion response (Issue #398: extracted)."""
        return {
            "success": error is None,
            "tag_suggestions": [],
            "category_suggestions": [],
            "error": error,
        } if error else {
            "success": True,
            "tag_suggestions": [],
            "category_suggestions": [],
            "similar_docs_analyzed": 0,
            "message": "No similar documents found for analysis",
        }

    async def suggest_all(
        self,
        content: str,
        tag_limit: int = 5,
        category_limit: int = 3,
        min_confidence: float = 0.3,
        similarity_limit: int = 20,
    ) -> Dict[str, Any]:
        """Suggest both tags and categories in a single call (Issue #398: refactored)."""
        self.ensure_initialized()

        if not content or not content.strip():
            return self._empty_suggestion_response("Content is required")

        try:
            similar_docs = await self._find_similar_documents(content, similarity_limit)
            if not similar_docs:
                return self._empty_suggestion_response()

            tag_scores, category_scores = await asyncio.gather(
                self._extract_weighted_tags(similar_docs),
                self._extract_weighted_categories(similar_docs),
            )

            tag_suggestions = self._build_suggestions_list(
                tag_scores, tag_limit, min_confidence
            )
            category_suggestions = self._build_category_suggestions_list(
                category_scores, category_limit, min_confidence
            )

            logger.info(
                "Generated %d tag and %d category suggestions from %d similar docs",
                len(tag_suggestions), len(category_suggestions), len(similar_docs),
            )

            return {
                "success": True,
                "tag_suggestions": tag_suggestions,
                "category_suggestions": category_suggestions,
                "similar_docs_analyzed": len(similar_docs),
            }

        except Exception as e:
            logger.error("Failed to suggest tags and categories: %s", e)
            return self._empty_suggestion_response(str(e))

    async def _apply_tag_suggestions(
        self, fact_id: str, suggestions: List[Dict], min_confidence: float, result: Dict
    ) -> None:
        """Apply tag suggestions to a fact (Issue #398: extracted)."""
        high_conf_tags = [
            s["tag"] for s in suggestions if s["confidence"] >= min_confidence
        ]
        if high_conf_tags:
            add_result = await self.add_tags_to_fact(fact_id, high_conf_tags)
            if add_result.get("status") == "success":
                result["applied_tags"] = high_conf_tags
            else:
                result["tag_error"] = add_result.get("message")
        result["skipped_tags"] = [
            {"tag": s["tag"], "confidence": s["confidence"]}
            for s in suggestions if s["confidence"] < min_confidence
        ]

    async def _apply_category_suggestion(
        self, fact_id: str, suggestions: List[Dict], min_confidence: float, result: Dict
    ) -> None:
        """Apply category suggestion to a fact (Issue #398: extracted)."""
        top_category = suggestions[0]
        if top_category["confidence"] >= min_confidence:
            assign_result = await self.assign_fact_to_category(
                fact_id, top_category["category_path"]
            )
            if assign_result.get("status") == "success":
                result["applied_category"] = top_category["category_path"]
            else:
                result["category_error"] = assign_result.get("message")
        result["skipped_categories"] = [
            {"category_path": s["category_path"], "confidence": s["confidence"]}
            for s in suggestions if s["confidence"] < min_confidence
        ]

    async def auto_apply_suggestions(
        self,
        fact_id: str,
        content: str,
        apply_tags: bool = True,
        apply_category: bool = True,
        min_confidence: float = 0.85,
    ) -> Dict[str, Any]:
        """Auto-apply high-confidence suggestions to a fact (Issue #398: refactored)."""
        self.ensure_initialized()

        result = {
            "success": True, "fact_id": fact_id, "applied_tags": [],
            "applied_category": None, "skipped_tags": [], "skipped_categories": [],
        }

        try:
            suggestions = await self.suggest_all(
                content, tag_limit=10, category_limit=3, min_confidence=min_confidence
            )

            if not suggestions.get("success"):
                return {
                    "success": False, "fact_id": fact_id,
                    "error": suggestions.get("error", "Failed to get suggestions"),
                }

            if apply_tags and suggestions.get("tag_suggestions"):
                await self._apply_tag_suggestions(
                    fact_id, suggestions["tag_suggestions"], min_confidence, result
                )

            if apply_category and suggestions.get("category_suggestions"):
                await self._apply_category_suggestion(
                    fact_id, suggestions["category_suggestions"], min_confidence, result
                )

            return result

        except Exception as e:
            logger.error("Failed to auto-apply suggestions: %s", e)
            return {"success": False, "fact_id": fact_id, "error": str(e)}

    async def _find_similar_documents(
        self, content: str, limit: int
    ) -> List[Dict[str, Any]]:
        """
        Find similar documents using embedding similarity.

        Args:
            content: Content to find similar documents for
            limit: Maximum number of similar documents

        Returns:
            List of similar documents with scores and metadata
        """
        try:
            # Use existing search method with vector mode
            results = await self.search(
                query=content,
                top_k=limit,
                mode="vector",
            )

            # Filter to only include results with decent similarity
            min_similarity = 0.3
            return [r for r in results if r.get("score", 0) >= min_similarity]

        except Exception as e:
            logger.error("Failed to find similar documents: %s", e)
            return []

    async def _extract_weighted_tags(
        self, similar_docs: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[float, int]]:
        """
        Extract tags from similar documents weighted by similarity.

        Args:
            similar_docs: List of similar documents with scores

        Returns:
            Dict mapping tag -> (weighted_score, source_count)
        """
        tag_weights: Dict[str, float] = defaultdict(float)
        tag_counts: Dict[str, int] = defaultdict(int)

        for doc in similar_docs:
            similarity_score = doc.get("score", 0.5)
            metadata = doc.get("metadata", {})

            # Get tags from metadata
            tags = metadata.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, TypeError):
                    tags = [tags] if tags else []

            # Also try to get tags from fact in Redis
            fact_id = metadata.get("fact_id")
            if fact_id and not tags:
                tags = await self._get_fact_tags(fact_id)

            for tag in tags:
                if tag and isinstance(tag, str):
                    normalized_tag = tag.lower().strip()
                    if normalized_tag:
                        tag_weights[normalized_tag] += similarity_score
                        tag_counts[normalized_tag] += 1

        # Combine into final scores
        result = {}
        for tag, weight in tag_weights.items():
            count = tag_counts[tag]
            # Normalize: average weight, boosted by frequency
            avg_weight = weight / count
            frequency_boost = min(1.0, count / 5)  # Cap at 5 occurrences
            final_score = avg_weight * (0.7 + 0.3 * frequency_boost)
            result[tag] = (final_score, count)

        return result

    async def _extract_weighted_categories(
        self, similar_docs: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[float, int]]:
        """
        Extract categories from similar documents weighted by similarity.

        Args:
            similar_docs: List of similar documents with scores

        Returns:
            Dict mapping category_path -> (weighted_score, source_count)
        """
        category_weights: Dict[str, float] = defaultdict(float)
        category_counts: Dict[str, int] = defaultdict(int)

        for doc in similar_docs:
            similarity_score = doc.get("score", 0.5)
            metadata = doc.get("metadata", {})

            # Get category from metadata
            category = metadata.get("category", "")
            category_path = metadata.get("category_path", category)

            # Also try to get category from fact in Redis
            fact_id = metadata.get("fact_id")
            if fact_id and not category_path:
                category_path = await self._get_fact_category(fact_id)

            if category_path and isinstance(category_path, str):
                category_path = category_path.strip()
                if category_path:
                    category_weights[category_path] += similarity_score
                    category_counts[category_path] += 1

        # Combine into final scores
        result = {}
        for category, weight in category_weights.items():
            count = category_counts[category]
            avg_weight = weight / count
            frequency_boost = min(1.0, count / 3)  # Cap at 3 occurrences
            final_score = avg_weight * (0.6 + 0.4 * frequency_boost)
            result[category] = (final_score, count)

        return result

    async def _get_fact_tags(self, fact_id: str) -> List[str]:
        """Get tags for a fact from Redis."""
        try:
            fact_key = f"fact:{fact_id}"
            metadata_json = await asyncio.to_thread(
                self.redis_client.hget, fact_key, "metadata"
            )
            if metadata_json:
                metadata = json.loads(metadata_json)
                return metadata.get("tags", [])
        except Exception as e:
            logger.debug("Failed to get tags for fact %s: %s", fact_id, e)
        return []

    async def _get_fact_category(self, fact_id: str) -> str:
        """Get category for a fact from Redis."""
        try:
            fact_key = f"fact:{fact_id}"
            metadata_json = await asyncio.to_thread(
                self.redis_client.hget, fact_key, "metadata"
            )
            if metadata_json:
                metadata = json.loads(metadata_json)
                return metadata.get("category_path", metadata.get("category", ""))
        except Exception as e:
            logger.debug("Failed to get category for fact %s: %s", fact_id, e)
        return ""

    def _build_suggestions_list(
        self,
        tag_scores: Dict[str, Tuple[float, int]],
        limit: int,
        min_confidence: float,
    ) -> List[Dict[str, Any]]:
        """
        Build sorted list of tag suggestions.

        Args:
            tag_scores: Dict mapping tag -> (score, count)
            limit: Maximum suggestions to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of suggestion dicts sorted by confidence
        """
        suggestions = []
        for tag, (score, count) in tag_scores.items():
            if score >= min_confidence:
                suggestions.append({
                    "tag": tag,
                    "confidence": round(score, 3),
                    "source_count": count,
                })

        # Sort by confidence descending
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        return suggestions[:limit]

    def _build_category_suggestions_list(
        self,
        category_scores: Dict[str, Tuple[float, int]],
        limit: int,
        min_confidence: float,
    ) -> List[Dict[str, Any]]:
        """
        Build sorted list of category suggestions.

        Args:
            category_scores: Dict mapping category_path -> (score, count)
            limit: Maximum suggestions to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of suggestion dicts sorted by confidence
        """
        suggestions = []
        for category_path, (score, count) in category_scores.items():
            if score >= min_confidence:
                suggestions.append({
                    "category_path": category_path,
                    "confidence": round(score, 3),
                    "source_count": count,
                })

        # Sort by confidence descending
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        return suggestions[:limit]

    def ensure_initialized(self):
        """Ensure the knowledge base is initialized. Implemented in composed class."""
        raise NotImplementedError("Should be implemented in composed class")
