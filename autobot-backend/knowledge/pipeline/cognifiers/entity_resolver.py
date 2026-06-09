# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Entity Resolver Cognifier - Resolve and deduplicate entities across documents.

Issue #3395: RAG optimization — semantic chunking, fact extraction, entity resolution.
Phase 3 — Entity Resolution: Deduplicate entities across documents (e.g., "AutoBot" =
"AutoBot AI" = "the system") and build entity synonym map for improved recall.
"""

from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Set

from autobot_shared.logging_manager import get_logger
from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.registry import TaskRegistry

logger = get_logger(__name__)

# Synonym mappings for common entity variations (Issue #3395)
# Maps canonical forms to known synonyms and variations
DEFAULT_SYNONYMS: Dict[str, Set[str]] = {
    "autobot": {"autobot ai", "the system", "autobot platform"},
    "chromadb": {"chroma", "vector database"},
    "entity resolution": {
        "entity linking",
        "entity disambiguation",
        "coreference resolution",
    },
    "knowledge base": {"knowledge graph", "knowledge management system"},
    "rag": {"retrieval-augmented generation", "rag system"},
    "llm": {"large language model", "language model"},
    "nlp": {"natural language processing"},
}

# Minimum string similarity threshold for merging entities (0.0-1.0)
SIMILARITY_THRESHOLD = 0.85


@TaskRegistry.register_cognifier("resolve_entities")
class EntityResolver(BaseCognifier):
    """Resolve and deduplicate entities across documents using multiple strategies."""

    def __init__(
        self,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        use_synonyms: bool = True,
        use_fuzzy_matching: bool = True,
    ) -> None:
        """
        Initialize entity resolver.

        Args:
            similarity_threshold: Threshold for fuzzy matching (0.0-1.0)
            use_synonyms: Whether to use predefined synonym mappings
            use_fuzzy_matching: Whether to use string similarity for entity matching
        """
        self.similarity_threshold = similarity_threshold
        self.use_synonyms = use_synonyms
        self.use_fuzzy_matching = use_fuzzy_matching
        self.synonyms = DEFAULT_SYNONYMS.copy()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Resolve and deduplicate entities in context (Issue #3395).

        Applies multiple strategies to identify equivalent entities:
        1. Exact canonical name matching
        2. Predefined synonym mappings
        3. Fuzzy string matching for entity names

        Args:
            context: Pipeline context with entities

        Returns:
            Updated context with resolved entities
        """
        entities = context.entities
        if not entities:
            logger.info("No entities to resolve")
            return context

        logger.info("Resolving %d entities", len(entities))

        resolved = self._resolve_entities(entities)
        context.entities = resolved

        logger.info("Resolved to %d unique entities", len(resolved))
        return context

    def _resolve_entities(self, entities: List[Entity]) -> List[Entity]:
        """
        Resolve entities using multiple strategies (Issue #3395).

        Args:
            entities: Entities to resolve

        Returns:
            Deduplicated list of resolved entities
        """
        entity_map: Dict[str, Entity] = {}

        for entity in entities:
            canonical = entity.canonical_name
            merged_with = self._find_equivalent_entity(canonical, entity_map.keys())

            if merged_with:
                existing = entity_map[merged_with]
                existing.source_chunk_ids.extend(entity.source_chunk_ids)
                existing.source_chunk_ids = list(set(existing.source_chunk_ids))
                existing.extraction_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.1)
                logger.debug("Merged entity %r with %r", entity.name, existing.name)
            else:
                entity_map[canonical] = entity

        return list(entity_map.values())

    def _find_equivalent_entity(self, canonical_name: str, existing_keys: Iterable[str]) -> str | None:
        """
        Find an equivalent entity in existing entities (Issue #3395).

        Tries multiple strategies:
        1. Exact match on canonical name
        2. Synonym match using predefined mapping
        3. Fuzzy string similarity matching

        Args:
            canonical_name: Canonical form of entity to find match for
            existing_keys: Existing canonical names to search against

        Returns:
            Canonical name of matching entity, or None
        """
        existing_list = list(existing_keys)

        # Strategy 1: Exact match
        if canonical_name in existing_list:
            return canonical_name

        # Strategy 2: Synonym match
        if self.use_synonyms:
            match = self._find_synonym_match(canonical_name, existing_list)
            if match:
                return match

        # Strategy 3: Fuzzy matching
        if self.use_fuzzy_matching:
            match = self._find_fuzzy_match(canonical_name, existing_list)
            if match:
                return match

        return None

    def _find_synonym_match(self, canonical_name: str, existing_names: List[str]) -> str | None:
        """
        Find entity match using predefined synonyms (Issue #3395).

        Args:
            canonical_name: Canonical form of entity
            existing_names: Existing canonical names to search

        Returns:
            Canonical name of matching entity, or None
        """
        # Check if canonical_name is a known synonym
        for root, synonyms in self.synonyms.items():
            if canonical_name in synonyms or canonical_name == root:
                for existing in existing_names:
                    if existing in synonyms or existing == root or existing in {root} | synonyms:
                        return existing

        return None

    def _find_fuzzy_match(self, canonical_name: str, existing_names: List[str]) -> str | None:
        """
        Find entity match using string similarity (Issue #3395).

        Args:
            canonical_name: Canonical form of entity
            existing_names: Existing canonical names to search

        Returns:
            Canonical name of best fuzzy match, or None if threshold not met
        """
        best_match = None
        best_ratio = 0.0

        for existing in existing_names:
            ratio = self._string_similarity(canonical_name, existing)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = existing

        if best_ratio >= self.similarity_threshold:
            return best_match

        return None

    @staticmethod
    def _string_similarity(s1: str, s2: str) -> float:
        """
        Calculate string similarity ratio (Issue #3395).

        Uses SequenceMatcher to compute normalized similarity.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity ratio from 0.0 to 1.0
        """
        return SequenceMatcher(None, s1, s2).ratio()

    def add_synonyms(self, root: str, synonyms: Set[str]) -> None:
        """
        Add custom synonym mappings (Issue #3395).

        Args:
            root: Root canonical form
            synonyms: Set of synonym strings
        """
        if root not in self.synonyms:
            self.synonyms[root] = set()
        self.synonyms[root].update(synonyms)
        logger.info("Added %d synonyms for %r", len(synonyms), root)
