# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Relationship Extractor Cognifier - Extract entity relationships.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from typing import Any, Dict, List

from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import (
    build_entity_map,
    parse_llm_json_response,
)
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.relationship import Relationship, RelationType
from knowledge.pipeline.registry import TaskRegistry
from llm_interface_pkg import LLMInterface

logger = logging.getLogger(__name__)


RELATIONSHIP_EXTRACTION_PROMPT = """Extract relationships between entities.

Known entities:
{entities}

Relationship types: CAUSES, ENABLES, PREVENTS, TRIGGERS, CONTAINS, PART_OF,
COMPOSED_OF, RELATES_TO, SIMILAR_TO, CONTRASTS_WITH, PRECEDES, FOLLOWS,
DURING, IS_A, INSTANCE_OF, SUBTYPE_OF, CREATED_BY, AUTHORED_BY, OWNED_BY,
IMPLEMENTS, EXTENDS, DEPENDS_ON, USES

Return JSON array:
[{{"source": "Entity1", "target": "Entity2", "type": "CAUSES",
"description": "...", "bidirectional": false, "confidence": 0.9}}, ...]

Text:
{text}
"""


SYMMETRIC_RELATIONS = {"SIMILAR_TO", "RELATES_TO", "CONTRASTS_WITH"}


@TaskRegistry.register_cognifier("extract_relationships")
class RelationshipExtractor(BaseCognifier):
    """Extract relationships between entities using LLM."""

    def __init__(self, batch_size: int = 5) -> None:
        """
        Initialize relationship extractor.

        Args:
            batch_size: Number of chunks to process per batch
        """
        self.batch_size = batch_size
        self.llm = LLMInterface()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract relationships from chunks with entity context.

        Args:
            context: Pipeline context with chunks and entities

        Returns:
            Updated context with relationships
        """
        chunks: List[ProcessedChunk] = context.chunks
        entities: List[Entity] = context.entities

        if not entities:
            logger.warning("No entities for relationship extraction")
            return context

        entity_map = build_entity_map(entities)
        all_relationships: List[Relationship] = []

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_rels = await self._process_batch(batch, entities, entity_map)
            all_relationships.extend(batch_rels)

        context.relationships = all_relationships
        logger.info("Extracted %s relationships", len(all_relationships))
        return context

    async def _process_batch(
        self,
        chunks: List[ProcessedChunk],
        entities: List[Entity],
        entity_map: Dict[str, Entity],
    ) -> List[Relationship]:
        """Process batch of chunks for relationships."""
        relationships = []
        for chunk in chunks:
            chunk_rels = await self._extract_from_chunk(chunk, entities, entity_map)
            relationships.extend(chunk_rels)
        return relationships

    async def _extract_from_chunk(
        self,
        chunk: ProcessedChunk,
        entities: List[Entity],
        entity_map: Dict[str, Entity],
    ) -> List[Relationship]:
        """Extract relationships from a single chunk."""
        try:
            entity_list = self._format_entity_list(entities, chunk)
            prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
                entities=entity_list, text=chunk.content
            )
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            raw_rels = parse_llm_json_response(response.content)
            return self._convert_to_relationships(raw_rels, chunk, entity_map)
        except Exception as e:
            logger.error("Relationship extraction failed: %s", e)
            return []

    def _format_entity_list(self, entities: List[Entity], chunk: ProcessedChunk) -> str:
        """Format entity list for prompt (chunk-relevant only)."""
        relevant = [e for e in entities if chunk.id in e.source_chunk_ids]
        if not relevant:
            relevant = entities[:20]
        return "\n".join([f"- {e.name} ({e.entity_type})" for e in relevant])

    def _convert_to_relationships(
        self,
        raw_rels: List[Dict[str, Any]],
        chunk: ProcessedChunk,
        entity_map: Dict[str, Entity],
    ) -> List[Relationship]:
        """Convert raw relationship dicts to Relationship objects."""
        relationships = []
        for raw in raw_rels:
            try:
                source_name = raw["source"].lower()
                target_name = raw["target"].lower()
                source_entity = entity_map.get(source_name)
                target_entity = entity_map.get(target_name)

                if not source_entity or not target_entity:
                    continue

                rel_type = raw.get("type", "RELATES_TO")
                if rel_type not in RelationType.__args__:
                    rel_type = "RELATES_TO"

                bidirectional = (
                    raw.get("bidirectional", False) or rel_type in SYMMETRIC_RELATIONS
                )

                rel = Relationship(
                    source_entity_id=source_entity.id,
                    target_entity_id=target_entity.id,
                    relationship_type=rel_type,
                    description=raw.get("description", ""),
                    bidirectional=bidirectional,
                    confidence=float(raw.get("confidence", 0.8)),
                    source_chunk_ids=[chunk.id],
                )
                relationships.append(rel)
            except Exception as e:
                logger.warning("Failed to create relationship: %s", e)
        return relationships
