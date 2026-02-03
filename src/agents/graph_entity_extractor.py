#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Graph Entity Extractor - Automatic graph population from conversations.

This agent automatically extracts entities and relationships from conversation
text and populates the AutoBot Memory Graph. It uses composition to reuse
existing KnowledgeExtractionAgent and AutoBotMemoryGraph components.

Architecture:
- Composes KnowledgeExtractionAgent (reuses fact extraction)
- Composes AutoBotMemoryGraph (reuses entity management)
- Maps atomic facts → graph entities
- Infers relationships from co-occurrence and context
- Zero code duplication - pure composition pattern

Key Features:
- Automatic entity extraction from conversations
- Fact-to-entity type classification
- Relationship inference based on context
- Co-occurrence relationship detection
- Temporal awareness (static vs. dynamic facts)
- Batch processing for efficiency
- Duplicate detection and merging

Usage:
    from src.agents.knowledge_extraction_agent import KnowledgeExtractionAgent
    from src.autobot_memory_graph import AutoBotMemoryGraph
    from src.agents.graph_entity_extractor import GraphEntityExtractor

    # Initialize dependencies
    extractor = KnowledgeExtractionAgent()
    memory_graph = AutoBotMemoryGraph()
    await memory_graph.initialize()

    # Create entity extractor via composition
    entity_extractor = GraphEntityExtractor(extractor, memory_graph)

    # Extract and populate from conversation
    result = await entity_extractor.extract_and_populate(
        conversation_id="abc-123",
        messages=[
            {"role": "user", "content": "How do I configure Redis timeout?"},
            {"role": "assistant", "content": "Set timeout to 30s in redis.conf..."}
        ]
    )

    logger.info(f"Created {result['entities_created']} entities, "
                f"{result['relations_created']} relationships")
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.agents.knowledge_extraction_agent import KnowledgeExtractionAgent
from src.autobot_memory_graph import AutoBotMemoryGraph
from src.models.atomic_fact import AtomicFact, FactType, TemporalType
from src.utils.error_boundaries import error_boundary
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("graph_entity_extractor")


@dataclass
class EntityCandidate:
    """
    Candidate entity extracted from facts.

    Attributes:
        name: Entity name (human-readable)
        entity_type: Type of entity (bug_fix, feature, decision, task, etc.)
        observations: List of observation strings
        facts: Source facts that generated this entity
        confidence: Confidence score (0.0-1.0)
        tags: Classification tags
        temporal_type: Temporal classification (static, dynamic, future, past)
    """

    name: str
    entity_type: str
    observations: List[str] = field(default_factory=list)
    facts: List[AtomicFact] = field(default_factory=list)
    confidence: float = 0.0
    tags: Set[str] = field(default_factory=set)
    temporal_type: Optional[TemporalType] = None


@dataclass
class RelationCandidate:
    """
    Candidate relationship between entities.

    Attributes:
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Type of relationship
        confidence: Confidence score (0.0-1.0)
        evidence: Supporting evidence for the relationship
    """

    from_entity: str
    to_entity: str
    relation_type: str
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """
    Result of entity extraction and graph population.

    Attributes:
        conversation_id: Source conversation identifier
        entities_created: Number of entities created
        relations_created: Number of relationships created
        processing_time: Total processing time in seconds
        facts_analyzed: Number of facts analyzed
        entities_merged: Number of entities merged with existing
        errors: List of errors encountered
    """

    conversation_id: str
    entities_created: int = 0
    relations_created: int = 0
    processing_time: float = 0.0
    facts_analyzed: int = 0
    entities_merged: int = 0
    errors: List[str] = field(default_factory=list)


class GraphEntityExtractor:
    """
    Reusable agent for automatic graph population from text.

    This agent extracts entities and relationships from conversation text
    using composition of existing KnowledgeExtractionAgent and
    AutoBotMemoryGraph components.

    Extraction Strategy:
    1. Extract facts: Use KnowledgeExtractionAgent (REUSE)
    2. Classify facts: Map fact types → entity types
    3. Group facts: Merge related facts into entities
    4. Infer relationships: Detect co-occurrence and context
    5. Create entities: Use AutoBotMemoryGraph (REUSE)
    6. Create relationships: Use AutoBotMemoryGraph (REUSE)

    Design Principles:
    - Composition over inheritance
    - Dependency injection for testability
    - No code duplication
    - Configurable thresholds
    - Batch processing for efficiency
    """

    def __init__(
        self,
        extraction_agent: KnowledgeExtractionAgent,
        memory_graph: AutoBotMemoryGraph,
        confidence_threshold: float = 0.6,
        enable_relationship_inference: bool = True,
    ):
        """
        Initialize Graph Entity Extractor via composition.

        Args:
            extraction_agent: Existing knowledge extraction agent (DI)
            memory_graph: Existing memory graph instance (DI)
            confidence_threshold: Minimum confidence for entity creation (0.0-1.0)
            enable_relationship_inference: Whether to infer relationships

        Design Notes:
        - No inheritance - uses composition for flexibility
        - Dependencies injected - easy to test with mocks
        - Configuration external - no hardcoded values
        """
        self.extractor = extraction_agent
        self.graph = memory_graph
        self.confidence_threshold = confidence_threshold
        self.enable_relationship_inference = enable_relationship_inference

        # Fact type → Entity type mapping
        # Note: FactType enum only has: FACT, OPINION, PREDICTION, INSTRUCTION, DEFINITION
        # We map these to semantic entity types based on content analysis
        self.fact_to_entity_mapping = {
            FactType.FACT: "fact",
            FactType.INSTRUCTION: "task",
            FactType.DEFINITION: "insight",
            FactType.OPINION: "opinion",
            FactType.PREDICTION: "prediction",
        }

        # Relationship inference keywords
        self.relationship_keywords = {
            "fixes": ["fix", "resolve", "repair", "correct", "address"],
            "implements": ["implement", "add", "create", "build", "develop"],
            "depends_on": ["require", "need", "depend", "prerequisite"],
            "relates_to": ["related", "similar", "like", "associated"],
            "informs": ["inform", "guide", "suggest", "recommend"],
            "blocks": ["block", "prevent", "stop", "hinder"],
        }

        logger.info(
            f"GraphEntityExtractor initialized "
            f"(confidence_threshold={confidence_threshold}, "
            f"relationship_inference={enable_relationship_inference})"
        )

    @error_boundary(
        component="graph_entity_extractor",
        function="extract_and_populate",
    )
    async def extract_and_populate(
        self,
        conversation_id: str,
        messages: List[Dict[str, str]],
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Extract entities from conversation and populate graph.

        This method processes conversation messages, extracts facts using
        KnowledgeExtractionAgent, maps facts to entities, and creates them
        in AutoBotMemoryGraph.

        Args:
            conversation_id: Unique conversation identifier
            messages: List of message dicts with 'role' and 'content'
            session_metadata: Optional metadata about the conversation

        Returns:
            ExtractionResult with statistics and errors

        Issue #281: Refactored to use extracted helpers.
        """
        start_time = time.perf_counter()
        result = ExtractionResult(conversation_id=conversation_id)

        try:
            logger.info(
                f"Extracting entities from conversation {conversation_id} "
                f"({len(messages)} messages)"
            )

            # Step 1: Combine messages into text for extraction
            combined_text = self._combine_messages(messages)

            if not combined_text.strip():
                logger.warning("No content to extract from conversation %s", conversation_id)
                return result

            # Step 2: Extract and filter facts (Issue #281 - uses helper)
            high_confidence_facts = await self._extract_facts_from_messages(
                combined_text, conversation_id, result
            )

            # Step 3: Process entity candidates (Issue #281 - uses helper)
            entity_candidates = self._facts_to_entity_candidates(
                high_confidence_facts, conversation_id, session_metadata
            )
            created_entities = await self._process_entity_candidates(
                high_confidence_facts, conversation_id, session_metadata, result
            )

            # Step 4: Process relationships (Issue #281 - uses helper)
            await self._process_relationships(
                entity_candidates, high_confidence_facts, created_entities, result
            )

            result.processing_time = time.perf_counter() - start_time

            logger.info(
                f"Entity extraction complete: {result.entities_created} entities, "
                f"{result.relations_created} relations in {result.processing_time:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(
                f"Entity extraction failed for conversation {conversation_id}: {e}",
                exc_info=True,
            )
            result.errors.append(str(e))
            result.processing_time = time.perf_counter() - start_time
            return result

    def _combine_messages(self, messages: List[Dict[str, str]]) -> str:
        """
        Combine conversation messages into single text for extraction.

        Args:
            messages: List of message dictionaries

        Returns:
            Combined text string
        """
        combined = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if content.strip():
                # Prefix with role for context
                combined.append(f"[{role.upper()}]: {content}")

        return "\n\n".join(combined)

    def _facts_to_entity_candidates(
        self,
        facts: List[AtomicFact],
        conversation_id: str,
        session_metadata: Optional[Dict[str, Any]],
    ) -> List[EntityCandidate]:
        """
        Convert atomic facts to entity candidates.

        This method maps fact types to entity types and groups related facts
        into coherent entity candidates.

        Args:
            facts: List of extracted atomic facts
            conversation_id: Source conversation ID
            session_metadata: Optional session metadata

        Returns:
            List of EntityCandidate objects

        Issue #281: Refactored to use _build_entity_candidate_from_group helper.
        """
        entity_candidates = []
        facts_by_type: Dict[str, List[AtomicFact]] = defaultdict(list)

        # Group facts by entity type
        for fact in facts:
            entity_type = self.fact_to_entity_mapping.get(fact.fact_type, "context")
            facts_by_type[entity_type].append(fact)

        # Create entity candidates for each type (Issue #281 - uses helper)
        for entity_type, type_facts in facts_by_type.items():
            grouped_facts = self._group_similar_facts(type_facts)

            for fact_group in grouped_facts:
                candidate = self._build_entity_candidate_from_group(
                    fact_group, entity_type, conversation_id
                )
                entity_candidates.append(candidate)

        return entity_candidates

    def _group_similar_facts(
        self, facts: List[AtomicFact], similarity_threshold: float = 0.7
    ) -> List[List[AtomicFact]]:
        """
        Group similar facts together for entity creation.

        Args:
            facts: List of facts to group
            similarity_threshold: Minimum similarity for grouping (0.0-1.0)

        Returns:
            List of fact groups (each group becomes one entity)

        Strategy:
            - Use content similarity (Jaccard similarity on words)
            - Group facts that share significant vocabulary
            - Keep groups small (max 5 facts per entity)
        """
        if not facts:
            return []

        groups = []
        used_indices = set()

        for i, fact in enumerate(facts):
            if i in used_indices:
                continue

            # Start new group with this fact
            group = [fact]
            used_indices.add(i)

            # Find similar facts
            for j, other_fact in enumerate(facts):
                if j in used_indices or i == j:
                    continue

                # Calculate similarity (simple word overlap)
                similarity = self._calculate_fact_similarity(fact, other_fact)

                if similarity >= similarity_threshold:
                    group.append(other_fact)
                    used_indices.add(j)

                    # Limit group size
                    if len(group) >= 5:
                        break

            groups.append(group)

        return groups

    def _calculate_fact_similarity(self, fact1: AtomicFact, fact2: AtomicFact) -> float:
        """
        Calculate similarity between two facts using Jaccard similarity.

        Args:
            fact1: First fact
            fact2: Second fact

        Returns:
            Similarity score (0.0-1.0)
        """
        words1 = set(fact1.original_text.lower().split())
        words2 = set(fact2.original_text.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _generate_entity_name(
        self, fact: AtomicFact, entity_type: str, conversation_id: str
    ) -> str:
        """
        Generate entity name from fact content.

        Args:
            fact: Primary fact for this entity
            entity_type: Type of entity being created
            conversation_id: Source conversation

        Returns:
            Human-readable entity name

        Strategy:
            - Extract key nouns/entities from fact content
            - Format as readable name
            - Include entity type prefix for clarity
        """
        # Use extracted entities from fact if available
        if fact.entities:
            primary_entity = fact.entities[0]
            return f"{entity_type.replace('_', ' ').title()}: {primary_entity}"

        # Otherwise, use first few words of content
        words = fact.original_text.split()[:5]
        truncated = " ".join(words)

        # Add conversation reference
        conv_suffix = conversation_id[:8]

        return f"{entity_type.replace('_', ' ').title()}: {truncated}... ({conv_suffix})"

    async def _create_entities_in_graph(
        self, candidates: List[EntityCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Create entities in memory graph.

        Uses AutoBotMemoryGraph.create_entity() for each candidate (REUSE).

        Args:
            candidates: List of entity candidates

        Returns:
            List of created entity data dictionaries
        """
        created_entities = []

        for candidate in candidates:
            try:
                # Use existing memory_graph.create_entity() (REUSE)
                entity = await self.graph.create_entity(
                    entity_type=candidate.entity_type,
                    name=candidate.name,
                    observations=candidate.observations,
                    metadata={
                        "confidence": candidate.confidence,
                        "temporal_type": (
                            candidate.temporal_type.value
                            if candidate.temporal_type
                            else "unknown"
                        ),
                        "priority": "medium",
                        "status": "active",
                    },
                    tags=list(candidate.tags),
                )

                created_entities.append(entity)
                logger.debug("Created entity: %s", candidate.name)

            except Exception as e:
                logger.warning("Failed to create entity '%s': %s", candidate.name, e)
                continue

        return created_entities

    def _infer_relationships(
        self, entity_candidates: List[EntityCandidate], facts: List[AtomicFact]
    ) -> List[RelationCandidate]:
        """
        Infer relationships between entities.

        Strategy:
            - Co-occurrence: Entities mentioned in same fact
            - Keyword matching: Relationship keywords in facts
            - Temporal ordering: Earlier entities inform later ones

        Args:
            entity_candidates: List of entity candidates
            facts: Original facts for context

        Returns:
            List of RelationCandidate objects
        """
        relation_candidates = []

        # Strategy 1: Co-occurrence relationships
        for i, entity_a in enumerate(entity_candidates):
            for entity_b in entity_candidates[i + 1 :]:
                # Check if entities co-occur in facts
                co_occurrence_evidence = self._check_co_occurrence(
                    entity_a, entity_b, facts
                )

                if co_occurrence_evidence:
                    relation_candidates.append(
                        RelationCandidate(
                            from_entity=entity_a.name,
                            to_entity=entity_b.name,
                            relation_type="relates_to",
                            confidence=0.7,
                            evidence=co_occurrence_evidence,
                        )
                    )

        # Strategy 2: Keyword-based relationships
        for entity in entity_candidates:
            for fact in entity.facts:
                keyword_relations = self._extract_keyword_relations(entity, fact, entity_candidates)
                relation_candidates.extend(keyword_relations)

        # Deduplicate relationships
        unique_relations = self._deduplicate_relations(relation_candidates)

        return unique_relations

    def _check_co_occurrence(
        self, entity_a: EntityCandidate, entity_b: EntityCandidate, facts: List[AtomicFact]
    ) -> List[str]:
        """
        Check if two entities co-occur in the same facts.

        Args:
            entity_a: First entity
            entity_b: Second entity
            facts: All facts to check

        Returns:
            List of evidence strings (co-occurring fact contents)
        """
        evidence = []

        # Get entity keywords (tags)
        keywords_a = entity_a.tags
        keywords_b = entity_b.tags

        if not keywords_a or not keywords_b:
            return evidence

        # Check each fact for co-occurrence
        for fact in facts:
            content_lower = fact.original_text.lower()

            # Check if both entity keywords appear in fact
            has_a = any(kw.lower() in content_lower for kw in keywords_a)
            has_b = any(kw.lower() in content_lower for kw in keywords_b)

            if has_a and has_b:
                evidence.append(fact.original_text[:100])  # Truncate for brevity

        return evidence[:3]  # Limit evidence

    def _extract_keyword_relations(
        self, entity: EntityCandidate, fact: AtomicFact, all_candidates: List[EntityCandidate]
    ) -> List[RelationCandidate]:
        """
        Extract relationships based on keyword matching.

        Args:
            entity: Source entity
            fact: Fact to analyze
            all_candidates: All entity candidates

        Returns:
            List of RelationCandidate objects
        """
        relations = []
        content_lower = fact.original_text.lower()

        # Check for relationship keywords
        for relation_type, keywords in self.relationship_keywords.items():
            if any(kw in content_lower for kw in keywords):
                # Find target entities mentioned in fact
                for candidate in all_candidates:
                    if candidate.name == entity.name:
                        continue

                    # Check if candidate's tags appear in fact
                    if any(tag.lower() in content_lower for tag in candidate.tags):
                        relations.append(
                            RelationCandidate(
                                from_entity=entity.name,
                                to_entity=candidate.name,
                                relation_type=relation_type,
                                confidence=0.8,
                                evidence=[fact.original_text[:100]],
                            )
                        )

        return relations

    def _deduplicate_relations(
        self, relations: List[RelationCandidate]
    ) -> List[RelationCandidate]:
        """
        Remove duplicate relationship candidates.

        Args:
            relations: List of relation candidates

        Returns:
            Deduplicated list keeping highest confidence versions
        """
        unique_map: Dict[Tuple[str, str, str], RelationCandidate] = {}

        for relation in relations:
            key = (relation.from_entity, relation.to_entity, relation.relation_type)

            if key not in unique_map or relation.confidence > unique_map[key].confidence:
                unique_map[key] = relation

        return list(unique_map.values())

    async def _create_relations_in_graph(
        self, candidates: List[RelationCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Create relationships in memory graph.

        Uses AutoBotMemoryGraph.create_relation() for each candidate (REUSE).

        Args:
            candidates: List of relation candidates

        Returns:
            List of created relation data dictionaries
        """
        created_relations = []

        for candidate in candidates:
            try:
                # Use existing memory_graph.create_relation() (REUSE)
                relation = await self.graph.create_relation(
                    from_entity=candidate.from_entity,
                    to_entity=candidate.to_entity,
                    relation_type=candidate.relation_type,
                    bidirectional=False,
                    strength=candidate.confidence,
                    metadata={"evidence": candidate.evidence[:2]},  # Limit evidence
                )

                created_relations.append(relation)
                logger.debug(
                    f"Created relation: {candidate.from_entity} "
                    f"--[{candidate.relation_type}]--> {candidate.to_entity}"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to create relation "
                    f"{candidate.from_entity} -> {candidate.to_entity}: {e}"
                )
                continue

        return created_relations

    # -------------------------------------------------------------------------
    # Issue #281 - Extracted helper methods for extract_and_populate refactoring
    # -------------------------------------------------------------------------

    async def _extract_facts_from_messages(
        self, combined_text: str, conversation_id: str, result: ExtractionResult
    ) -> List[AtomicFact]:
        """
        Extract facts from combined message text (Issue #281 - extracted helper).

        Args:
            combined_text: Combined conversation text
            conversation_id: Conversation identifier
            result: Result object to update

        Returns:
            List of high-confidence facts
        """
        extraction_result = await self.extractor.extract_facts_from_text(
            text=combined_text,
            source=f"Conversation {conversation_id}",
            max_facts=50,
        )

        result.facts_analyzed = len(extraction_result.facts)
        logger.info("Extracted %s facts from conversation", result.facts_analyzed)

        # Filter facts by confidence
        high_confidence_facts = [
            fact
            for fact in extraction_result.facts
            if fact.confidence >= self.confidence_threshold
        ]

        logger.info(
            f"Filtered to {len(high_confidence_facts)} high-confidence facts "
            f"(threshold={self.confidence_threshold})"
        )

        return high_confidence_facts

    async def _process_entity_candidates(
        self, high_confidence_facts: List[AtomicFact], conversation_id: str,
        session_metadata: Optional[Dict[str, Any]], result: ExtractionResult,
    ) -> List[Dict[str, Any]]:
        """
        Process facts into entity candidates and create in graph (Issue #281 - extracted helper).

        Args:
            high_confidence_facts: Filtered facts
            conversation_id: Conversation identifier
            session_metadata: Optional metadata
            result: Result object to update

        Returns:
            List of created entities
        """
        entity_candidates = self._facts_to_entity_candidates(
            high_confidence_facts, conversation_id, session_metadata
        )
        logger.info("Generated %s entity candidates", len(entity_candidates))

        created_entities = await self._create_entities_in_graph(entity_candidates)
        result.entities_created = len(created_entities)
        logger.info("Created %s entities in graph", result.entities_created)

        return created_entities

    async def _process_relationships(
        self, entity_candidates: List[EntityCandidate], high_confidence_facts: List[AtomicFact],
        created_entities: List[Dict[str, Any]], result: ExtractionResult,
    ) -> None:
        """
        Infer and create relationships between entities (Issue #281 - extracted helper).

        Args:
            entity_candidates: Entity candidates for relationship inference
            high_confidence_facts: Facts for context
            created_entities: Created entity list (for count check)
            result: Result object to update
        """
        if not self.enable_relationship_inference or len(created_entities) <= 1:
            return

        relation_candidates = self._infer_relationships(
            entity_candidates, high_confidence_facts
        )
        logger.info("Inferred %s relationship candidates", len(relation_candidates))

        created_relations = await self._create_relations_in_graph(relation_candidates)
        result.relations_created = len(created_relations)
        logger.info("Created %s relationships in graph", result.relations_created)

    def _build_entity_candidate_from_group(
        self, fact_group: List[AtomicFact], entity_type: str, conversation_id: str
    ) -> EntityCandidate:
        """
        Build an entity candidate from a group of related facts (Issue #281 - extracted helper).

        Args:
            fact_group: Group of related facts
            entity_type: Type of entity
            conversation_id: Conversation identifier

        Returns:
            EntityCandidate object
        """
        primary_fact = fact_group[0]
        entity_name = self._generate_entity_name(primary_fact, entity_type, conversation_id)

        # Collect observations from all facts in group
        observations = [fact.original_text for fact in fact_group]

        # Calculate average confidence
        avg_confidence = sum(f.confidence for f in fact_group) / len(fact_group)

        # Extract tags from entities
        tags: Set[str] = set()
        for fact in fact_group:
            if fact.entities:
                tags.update(fact.entities[:3])

        return EntityCandidate(
            name=entity_name,
            entity_type=entity_type,
            observations=observations,
            facts=fact_group,
            confidence=avg_confidence,
            tags=tags,
            temporal_type=primary_fact.temporal_type,
        )
