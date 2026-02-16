# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Extractor Cognifier - Extract named entities from text chunks.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import json
import logging
from typing import Any, Dict, List
from uuid import UUID

from llm_interface_pkg import LLMInterface

from backend.knowledge.pipeline.base import BaseCognifier, PipelineContext
from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.entity import Entity, EntityType
from backend.knowledge.pipeline.registry import TaskRegistry

logger = logging.getLogger(__name__)


ENTITY_EXTRACTION_PROMPT = """Extract named entities from the following text.
For each entity, provide:
- name: The entity name as mentioned in text
- type: One of PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION, EVENT, DOCUMENT
- description: Brief description
- confidence: Score 0.0-1.0

Return JSON array of entities:
[{"name": "...", "type": "...", "description": "...", "confidence": 0.9}, ...]

Text:
{text}
"""


@TaskRegistry.register_cognifier("extract_entities")
class EntityExtractor(BaseCognifier):
    """Extract named entities from text chunks using LLM."""

    def __init__(self, batch_size: int = 5) -> None:
        """
        Initialize entity extractor.

        Args:
            batch_size: Number of chunks to process per batch
        """
        self.batch_size = batch_size
        self.llm = LLMInterface()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract entities from chunks in context.

        Args:
            context: Pipeline context with chunks

        Returns:
            Updated context with entities
        """
        chunks: List[ProcessedChunk] = context.chunks
        all_entities: List[Entity] = []

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_entities = await self._process_batch(batch, context)
            all_entities.extend(batch_entities)

        merged_entities = self._merge_entities(all_entities)
        context.entities = merged_entities
        logger.info("Extracted %s entities", len(merged_entities))
        return context

    async def _process_batch(
        self, chunks: List[ProcessedChunk], context: PipelineContext
    ) -> List[Entity]:
        """Process a batch of chunks."""
        entities = []
        for chunk in chunks:
            chunk_entities = await self._extract_from_chunk(chunk, context)
            entities.extend(chunk_entities)
        return entities

    async def _extract_from_chunk(
        self, chunk: ProcessedChunk, context: PipelineContext
    ) -> List[Entity]:
        """Extract entities from a single chunk."""
        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=chunk.content)
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            raw_entities = self._parse_llm_response(response.content)
            return self._convert_to_entities(raw_entities, chunk, context.document_id)
        except Exception as e:
            logger.error("Entity extraction failed: %s", e)
            return []

    def _parse_llm_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON response."""
        try:
            # Try parsing as JSON array
            return json.loads(content)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            logger.warning("Could not parse LLM response as JSON")
            return []

    def _convert_to_entities(
        self,
        raw_entities: List[Dict[str, Any]],
        chunk: ProcessedChunk,
        document_id: UUID | None,
    ) -> List[Entity]:
        """Convert raw entity dicts to Entity objects."""
        entities = []
        for raw in raw_entities:
            try:
                entity_type = raw.get("type", "CONCEPT")
                if entity_type not in EntityType.__args__:
                    entity_type = "CONCEPT"

                entity = Entity(
                    name=raw["name"],
                    canonical_name=self._normalize_name(raw["name"]),
                    entity_type=entity_type,
                    description=raw.get("description", ""),
                    confidence=float(raw.get("confidence", 0.8)),
                    source_chunk_ids=[chunk.id],
                    source_document_id=document_id or chunk.document_id,
                )
                entities.append(entity)
            except Exception as e:
                logger.warning("Failed to create entity: %s", e)
        return entities

    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for deduplication."""
        return name.lower().strip()

    def _merge_entities(self, entities: List[Entity]) -> List[Entity]:
        """Merge duplicate entities by canonical name."""
        entity_map: Dict[str, Entity] = {}

        for entity in entities:
            canonical = entity.canonical_name
            if canonical in entity_map:
                existing = entity_map[canonical]
                existing.source_chunk_ids.extend(entity.source_chunk_ids)
                existing.extraction_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.1)
            else:
                entity_map[canonical] = entity

        return list(entity_map.values())
