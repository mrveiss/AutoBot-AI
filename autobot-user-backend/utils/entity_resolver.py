# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Resolver for AutoBot RAG Optimization

Provides semantic similarity-based entity resolution to reduce duplicates
and normalize entity names across the knowledge base.
"""

import json
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.config import config_manager
from src.models.atomic_fact import AtomicFact
from src.models.entity_mapping import (
    EntityMapping,
    EntityResolutionResult,
    EntityType,
    SimilarityMethod,
)
from src.utils.logging_manager import get_llm_logger
from src.utils.redis_client import get_redis_client

logger = get_llm_logger("entity_resolver")

# Entity classification patterns (Issue #315 - module-level constant)
_ENTITY_PATTERNS = {
    EntityType.TECHNOLOGY: [
        "api",
        "sdk",
        "framework",
        "library",
        "database",
        "server",
        "client",
        "python",
        "javascript",
        "java",
        "redis",
        "chromadb",
        "openai",
        "model",
        "algorithm",
        "neural",
        "transformer",
        "gpt",
        "llm",
    ],
    EntityType.PRODUCT: [
        "autobot",
        "system",
        "platform",
        "application",
        "service",
        "tool",
        "bot",
        "agent",
        "interface",
        "dashboard",
        "ui",
        "gui",
    ],
    EntityType.VERSION: ["v", "version", ".", "beta", "alpha", "rc"],
    EntityType.CONFIGURATION: ["config", "setting", "parameter", "option", "flag"],
}


def _check_version_pattern(name_lower: str, entity_name: str) -> bool:
    """Check if entity name matches version pattern. (Issue #315 - extracted)"""
    return any(p in name_lower for p in _ENTITY_PATTERNS[EntityType.VERSION]) and any(
        c.isdigit() for c in entity_name
    )


class EntityResolver:
    """
    Service for resolving and normalizing entity names using semantic similarity.

    This resolver identifies duplicate entities and creates canonical mappings
    to improve knowledge base consistency and retrieval accuracy.
    """

    def __init__(self):
        """Initialize the entity resolver."""
        # Configuration
        self.similarity_threshold = config_manager.get(
            "entity_resolution.similarity_threshold", 0.85
        )
        self.fuzzy_threshold = config_manager.get(
            "entity_resolution.fuzzy_threshold", 0.8
        )
        self.enable_semantic_similarity = config_manager.get(
            "entity_resolution.enable_semantic", True
        )
        self.enable_fuzzy_matching = config_manager.get(
            "entity_resolution.enable_fuzzy", True
        )

        # Models and clients
        self.embedding_model = None
        self.redis_client = get_redis_client(async_client=True)

        # Storage keys
        self.entity_mappings_key = "entity_mappings"
        self.entity_embeddings_key = "entity_embeddings"
        self.resolution_history_key = "entity_resolution_history"

        logger.info("Entity Resolver initialized")

    def _get_embedding_model(self):
        """Lazy load the sentence transformer model."""
        if self.embedding_model is None and self.enable_semantic_similarity:
            try:
                # Import only when needed to avoid startup delay
                from sentence_transformers import SentenceTransformer

                model_name = config_manager.get(
                    "entity_resolution.embedding_model", "all-MiniLM-L6-v2"
                )
                self.embedding_model = SentenceTransformer(model_name)
                logger.info("Loaded embedding model: %s", model_name)
            except Exception as e:
                logger.warning("Failed to load embedding model: %s", e)
                self.enable_semantic_similarity = False

        return self.embedding_model

    async def _process_entity_batches(
        self,
        unique_entities: List[str],
        existing_mappings: Dict[str, "EntityMapping"],
    ) -> tuple:
        """Process entities in batches and collect results (Issue #665: extracted helper)."""
        resolved_mappings = {}
        canonical_entities = []

        batch_size = config_manager.get("entity_resolution.batch_size", 50)

        for i in range(0, len(unique_entities), batch_size):
            batch = unique_entities[i : i + batch_size]
            batch_results = await self._resolve_entity_batch(batch, existing_mappings)

            for original, mapping in batch_results.items():
                resolved_mappings[original] = mapping.canonical_id

                if not any(
                    c.canonical_id == mapping.canonical_id for c in canonical_entities
                ):
                    canonical_entities.append(mapping)

        return resolved_mappings, canonical_entities

    def _create_fallback_result(
        self, entity_names: List[str], start_time: datetime
    ) -> "EntityResolutionResult":
        """Create fallback result when resolution fails (Issue #665: extracted helper)."""
        return EntityResolutionResult(
            original_entities=entity_names,
            resolved_mappings={name: name for name in entity_names},
            canonical_entities=[],
            processing_time=(datetime.now() - start_time).total_seconds(),
        )

    async def resolve_entities(
        self, entity_names: List[str], context: Optional[Dict[str, Any]] = None
    ) -> EntityResolutionResult:
        """
        Resolve a list of entity names to canonical entities.

        Args:
            entity_names: List of entity names to resolve
            context: Optional context for resolution

        Returns:
            EntityResolutionResult with resolved mappings
        """
        start_time = datetime.now()
        logger.info("Starting entity resolution for %s entities", len(entity_names))

        try:
            unique_entities = list(dict.fromkeys(entity_names))
            existing_mappings = await self._load_entity_mappings()

            resolved_mappings, canonical_entities = await self._process_entity_batches(
                unique_entities, existing_mappings
            )

            processing_time = (datetime.now() - start_time).total_seconds()

            result = EntityResolutionResult(
                original_entities=entity_names,
                resolved_mappings=resolved_mappings,
                canonical_entities=canonical_entities,
                processing_time=processing_time,
                similarity_method=SimilarityMethod.HYBRID,
                confidence_threshold=self.similarity_threshold,
            )

            await self._store_entity_mappings(canonical_entities)
            await self._record_resolution_history(result, context)

            logger.info(
                f"Entity resolution completed: {result.resolution_rate:.1f}% reduction"
            )
            return result

        except Exception as e:
            logger.error("Error in entity resolution: %s", e)
            return self._create_fallback_result(entity_names, start_time)

    async def _resolve_entity_batch(
        self, entity_names: List[str], existing_mappings: Dict[str, EntityMapping]
    ) -> Dict[str, EntityMapping]:
        """
        Resolve a batch of entity names.

        Args:
            entity_names: Batch of entity names to resolve
            existing_mappings: Existing entity mappings

        Returns:
            Dictionary mapping original names to EntityMapping objects
        """
        batch_results = {}

        for entity_name in entity_names:
            # First check for exact matches in existing mappings
            exact_match = await self._find_exact_match(entity_name, existing_mappings)
            if exact_match:
                batch_results[entity_name] = exact_match
                continue

            # Look for similar entities
            similar_mapping = await self._find_similar_entity(
                entity_name, existing_mappings
            )
            if similar_mapping:
                # Add this entity as an alias to the similar mapping
                similar_mapping.add_alias(entity_name, confidence=0.8)
                batch_results[entity_name] = similar_mapping
            else:
                # Create new entity mapping
                new_mapping = EntityMapping(
                    canonical_id=str(uuid.uuid4()),
                    canonical_name=entity_name.strip(),
                    entity_type=self._classify_entity_type(entity_name),
                    confidence_score=1.0,
                    mentions=[entity_name],
                    sources=set(),
                )
                batch_results[entity_name] = new_mapping
                existing_mappings[new_mapping.canonical_id] = new_mapping

        return batch_results

    async def _find_exact_match(
        self, entity_name: str, existing_mappings: Dict[str, EntityMapping]
    ) -> Optional[EntityMapping]:
        """Find exact match for entity name in existing mappings."""
        entity_name_normalized = entity_name.lower().strip()

        for mapping in existing_mappings.values():
            if mapping.canonical_name.lower().strip() == entity_name_normalized:
                return mapping

            # Check aliases
            for alias in mapping.aliases:
                if alias.lower().strip() == entity_name_normalized:
                    return mapping

        return None

    async def _find_similar_entity(
        self, entity_name: str, existing_mappings: Dict[str, EntityMapping]
    ) -> Optional[EntityMapping]:
        """Find similar entity using various similarity methods."""
        best_mapping = None
        best_score = 0.0

        for mapping in existing_mappings.values():
            # Fuzzy string similarity
            if self.enable_fuzzy_matching:
                fuzzy_score = await self._calculate_fuzzy_similarity(
                    entity_name, mapping
                )
                if fuzzy_score > best_score and fuzzy_score >= self.fuzzy_threshold:
                    best_score = fuzzy_score
                    best_mapping = mapping

            # Semantic similarity
            if self.enable_semantic_similarity and self._get_embedding_model():
                semantic_score = await self._calculate_semantic_similarity(
                    entity_name, mapping
                )
                if (
                    semantic_score > best_score
                    and semantic_score >= self.similarity_threshold
                ):
                    best_score = semantic_score
                    best_mapping = mapping

        return best_mapping if best_score >= self.similarity_threshold else None

    async def _calculate_fuzzy_similarity(
        self, entity_name: str, mapping: EntityMapping
    ) -> float:
        """Calculate fuzzy string similarity between entity and mapping."""
        entity_name_normalized = entity_name.lower().strip()
        max_similarity = 0.0

        # Check canonical name
        canonical_similarity = SequenceMatcher(
            None, entity_name_normalized, mapping.canonical_name.lower().strip()
        ).ratio()
        max_similarity = max(max_similarity, canonical_similarity)

        # Check aliases
        for alias in mapping.aliases:
            alias_similarity = SequenceMatcher(
                None, entity_name_normalized, alias.lower().strip()
            ).ratio()
            max_similarity = max(max_similarity, alias_similarity)

        return max_similarity

    async def _calculate_semantic_similarity(
        self, entity_name: str, mapping: EntityMapping
    ) -> float:
        """Calculate semantic similarity using embeddings."""
        try:
            model = self._get_embedding_model()
            if not model:
                return 0.0

            # Get embedding for the new entity
            entity_embedding = model.encode([entity_name])

            # Get embeddings for canonical name and aliases
            comparison_texts = [mapping.canonical_name] + list(mapping.aliases)
            comparison_embeddings = model.encode(comparison_texts)

            # Calculate cosine similarities
            similarities = cosine_similarity(entity_embedding, comparison_embeddings)[0]

            return float(np.max(similarities))

        except Exception as e:
            logger.error("Error calculating semantic similarity: %s", e)
            return 0.0

    def _classify_entity_type(self, entity_name: str) -> EntityType:
        """Classify entity type based on name patterns. (Issue #315 - uses module patterns)"""
        name_lower = entity_name.lower()

        # Check technology patterns
        if any(p in name_lower for p in _ENTITY_PATTERNS[EntityType.TECHNOLOGY]):
            return EntityType.TECHNOLOGY
        # Check product patterns
        if any(p in name_lower for p in _ENTITY_PATTERNS[EntityType.PRODUCT]):
            return EntityType.PRODUCT
        # Check version patterns (requires digits)
        if _check_version_pattern(name_lower, entity_name):
            return EntityType.VERSION
        # Check configuration patterns
        if any(p in name_lower for p in _ENTITY_PATTERNS[EntityType.CONFIGURATION]):
            return EntityType.CONFIGURATION
        # Acronyms
        if entity_name.isupper() and len(entity_name) <= 10:
            return EntityType.ORGANIZATION
        return EntityType.CONCEPT

    async def _load_entity_mappings(self) -> Dict[str, EntityMapping]:
        """Load existing entity mappings from Redis."""
        try:
            if not self.redis_client:
                return {}

            mapping_data = await self.redis_client.hgetall(self.entity_mappings_key)
            mappings = {}

            for mapping_id, mapping_json in mapping_data.items():
                try:
                    # Use json.loads instead of eval for security
                    mapping_dict = json.loads(mapping_json)
                    mapping = EntityMapping.from_dict(mapping_dict)
                    mappings[mapping_id] = mapping
                except (json.JSONDecodeError, Exception) as e:
                    logger.error("Error loading mapping %s: %s", mapping_id, e)
                    continue

            logger.debug("Loaded %s existing entity mappings", len(mappings))
            return mappings

        except Exception as e:
            logger.error("Error loading entity mappings: %s", e)
            return {}

    async def _store_entity_mappings(self, mappings: List[EntityMapping]):
        """Store entity mappings to Redis."""
        try:
            if not self.redis_client or not mappings:
                return

            # Store mappings in batch
            pipe = self.redis_client.pipeline()

            for mapping in mappings:
                mapping_dict = mapping.to_dict()
                pipe.hset(
                    self.entity_mappings_key,
                    mapping.canonical_id,
                    str(mapping_dict),  # Convert to string for storage
                )

            await pipe.execute()
            logger.debug("Stored %s entity mappings", len(mappings))

        except Exception as e:
            logger.error("Error storing entity mappings: %s", e)

    async def _record_resolution_history(
        self, result: EntityResolutionResult, context: Optional[Dict[str, Any]]
    ):
        """Record entity resolution history for analytics."""
        try:
            if not self.redis_client:
                return

            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "total_original": result.total_original,
                "total_canonical": result.total_canonical,
                "resolution_rate": result.resolution_rate,
                "processing_time": result.processing_time,
                "similarity_method": result.similarity_method.value,
                "confidence_threshold": result.confidence_threshold,
                "quality_metrics": {
                    "high_confidence": result.high_confidence_resolutions,
                    "low_confidence": result.low_confidence_resolutions,
                    "exact_matches": result.exact_matches,
                    "semantic_matches": result.semantic_matches,
                },
                "context": context or {},
            }

            # Store in history list (keep last 500 entries)
            await self.redis_client.lpush(
                self.resolution_history_key, str(history_entry)
            )
            await self.redis_client.ltrim(self.resolution_history_key, 0, 499)

            logger.debug("Recorded entity resolution history")

        except Exception as e:
            logger.error("Error recording resolution history: %s", e)

    def _extract_entities_from_facts(self, facts: List[AtomicFact]) -> set:
        """
        Extract all unique entities from a list of atomic facts.

        Collects entities from the entities list, subject, and object of each fact.

        Args:
            facts: List of atomic facts to extract entities from.

        Returns:
            Set of unique entity strings.

        Issue #620.
        """
        all_entities = set()
        for fact in facts:
            all_entities.update(fact.entities)
            all_entities.add(fact.subject)
            all_entities.add(fact.object)
        return all_entities

    def _apply_resolution_to_fact(
        self, fact: AtomicFact, resolution_result: EntityResolutionResult
    ) -> AtomicFact:
        """
        Apply entity resolution to a single atomic fact.

        Args:
            fact: The atomic fact to update.
            resolution_result: Resolution result containing canonical mappings.

        Returns:
            Updated atomic fact with resolved entities.

        Issue #620.
        """
        resolved_entities = [
            resolution_result.get_canonical_name(entity) for entity in fact.entities
        ]
        resolved_subject = resolution_result.get_canonical_name(fact.subject)
        resolved_object = resolution_result.get_canonical_name(fact.object)

        return fact.with_resolved_entities(
            resolved_subject=resolved_subject,
            resolved_object=resolved_object,
            resolved_entities=resolved_entities,
        )

    async def resolve_facts_entities(self, facts: List[AtomicFact]) -> List[AtomicFact]:
        """
        Resolve entities within atomic facts.

        Args:
            facts: List of atomic facts to process

        Returns:
            List of facts with resolved entities
        """
        if not facts:
            return facts

        logger.info("Resolving entities in %s facts", len(facts))

        try:
            all_entities = self._extract_entities_from_facts(facts)

            resolution_result = await self.resolve_entities(
                list(all_entities),
                context={"source": "atomic_facts", "fact_count": len(facts)},
            )

            updated_facts = [
                self._apply_resolution_to_fact(fact, resolution_result)
                for fact in facts
            ]

            logger.info(
                f"Entity resolution completed: {resolution_result.resolution_rate:.1f}% reduction"
            )
            return updated_facts

        except Exception as e:
            logger.error("Error resolving fact entities: %s", e)
            return facts

    def _parse_resolution_history(self, recent_history: List[str]) -> Dict[str, float]:
        """
        Parse resolution history entries and calculate totals.

        Args:
            recent_history: List of JSON-encoded history entries.

        Returns:
            Dict with total_processing_time, total_entities_processed,
            and total_entities_resolved.

        Issue #620.
        """
        totals = {
            "processing_time": 0.0,
            "entities_processed": 0,
            "entities_resolved": 0,
        }
        for history_str in recent_history:
            try:
                history = json.loads(history_str)
                totals["processing_time"] += history.get("processing_time", 0)
                totals["entities_processed"] += history.get("total_original", 0)
                totals["entities_resolved"] += history.get("total_canonical", 0)
            except Exception:  # nosec B112 - skip malformed JSON entries
                continue
        return totals

    def _build_statistics_response(
        self,
        total_mappings: int,
        total_resolutions: int,
        totals: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Build statistics response dictionary.

        Args:
            total_mappings: Number of entity mappings in Redis.
            total_resolutions: Number of recent resolution operations.
            totals: Parsed totals from resolution history.

        Returns:
            Dictionary containing all resolution statistics.

        Issue #620.
        """
        avg_processing_time = (
            totals["processing_time"] / total_resolutions
            if total_resolutions > 0
            else 0
        )
        avg_resolution_rate = (
            (totals["entities_processed"] - totals["entities_resolved"])
            / totals["entities_processed"]
            * 100
            if totals["entities_processed"] > 0
            else 0
        )
        return {
            "total_entity_mappings": total_mappings,
            "recent_resolutions": total_resolutions,
            "total_entities_processed": totals["entities_processed"],
            "total_entities_resolved": totals["entities_resolved"],
            "average_processing_time": round(avg_processing_time, 3),
            "average_resolution_rate": round(avg_resolution_rate, 1),
            "similarity_threshold": self.similarity_threshold,
            "fuzzy_threshold": self.fuzzy_threshold,
            "semantic_similarity_enabled": self.enable_semantic_similarity,
            "fuzzy_matching_enabled": self.enable_fuzzy_matching,
        }

    async def get_resolution_statistics(self) -> Dict[str, Any]:
        """Get entity resolution statistics."""
        try:
            if not self.redis_client:
                return {"error": "Redis client not available"}

            total_mappings = await self.redis_client.hlen(self.entity_mappings_key)
            recent_history = await self.redis_client.lrange(
                self.resolution_history_key, 0, 99
            )

            totals = self._parse_resolution_history(recent_history)
            return self._build_statistics_response(
                total_mappings, len(recent_history), totals
            )

        except Exception as e:
            logger.error("Error getting resolution statistics: %s", e)
            return {"error": str(e)}


# Singleton instance for global access
entity_resolver = EntityResolver()
