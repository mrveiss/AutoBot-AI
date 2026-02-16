# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Event Extractor Cognifier - Extract temporal events from text.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from llm_interface_pkg import LLMInterface

from backend.knowledge.pipeline.base import BaseCognifier, PipelineContext
from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.entity import Entity
from backend.knowledge.pipeline.models.event import (
    EventType,
    TemporalEvent,
    TemporalType,
)
from backend.knowledge.pipeline.registry import TaskRegistry

logger = logging.getLogger(__name__)


EVENT_EXTRACTION_PROMPT = """Extract temporal events from the text.

For each event:
- name: Event title
- description: Brief description
- temporal_expression: Time phrase (e.g., "yesterday", "2024-01-15")
- temporal_type: point, range, relative, recurring
- event_type: action, decision, change, milestone, occurrence
- participants: Entity names involved
- location: Where it happened (if mentioned)
- confidence: 0.0-1.0

Return JSON: [{{"name": "...", "description": "...", ...}}, ...]

Text:
{text}
"""


@TaskRegistry.register_cognifier("extract_events")
class EventExtractor(BaseCognifier):
    """Extract temporal events from text using LLM."""

    def __init__(self, batch_size: int = 5) -> None:
        """
        Initialize event extractor.

        Args:
            batch_size: Number of chunks to process per batch
        """
        self.batch_size = batch_size
        self.llm = LLMInterface()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract events from chunks.

        Args:
            context: Pipeline context with chunks and entities

        Returns:
            Updated context with events
        """
        chunks: List[ProcessedChunk] = context.chunks
        entities: List[Entity] = context.entities
        entity_map = self._build_entity_map(entities)
        all_events: List[TemporalEvent] = []

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_events = await self._process_batch(batch, entity_map, context)
            all_events.extend(batch_events)

        context.events = all_events
        logger.info("Extracted %s events", len(all_events))
        return context

    def _build_entity_map(self, entities: List[Entity]) -> Dict[str, Entity]:
        """Build name-to-entity mapping."""
        entity_map: Dict[str, Entity] = {}
        for entity in entities:
            entity_map[entity.name.lower()] = entity
            entity_map[entity.canonical_name] = entity
        return entity_map

    async def _process_batch(
        self,
        chunks: List[ProcessedChunk],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[TemporalEvent]:
        """Process batch of chunks for events."""
        events = []
        for chunk in chunks:
            chunk_events = await self._extract_from_chunk(chunk, entity_map, context)
            events.extend(chunk_events)
        return events

    async def _extract_from_chunk(
        self,
        chunk: ProcessedChunk,
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[TemporalEvent]:
        """Extract events from a single chunk."""
        try:
            prompt = EVENT_EXTRACTION_PROMPT.format(text=chunk.content)
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            raw_events = self._parse_llm_response(response.content)
            return self._convert_to_events(raw_events, chunk, entity_map, context)
        except Exception as e:
            logger.error("Event extraction failed: %s", e)
            return []

    def _parse_llm_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON response."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            logger.warning("Could not parse event response")
            return []

    def _convert_to_events(
        self,
        raw_events: List[Dict[str, Any]],
        chunk: ProcessedChunk,
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[TemporalEvent]:
        """Convert raw event dicts to TemporalEvent objects."""
        events = []
        for raw in raw_events:
            try:
                temporal_expr = raw.get("temporal_expression", "")
                timestamp = self._parse_temporal(temporal_expr)

                temporal_type = raw.get("temporal_type", "point")
                if temporal_type not in TemporalType.__args__:
                    temporal_type = "point"

                event_type = raw.get("event_type", "occurrence")
                if event_type not in EventType.__args__:
                    event_type = "occurrence"

                participant_names = raw.get("participants", [])
                participant_ids = [
                    entity_map[name.lower()].id
                    for name in participant_names
                    if name.lower() in entity_map
                ]

                event = TemporalEvent(
                    name=raw["name"],
                    description=raw.get("description", ""),
                    timestamp=timestamp,
                    temporal_expression=temporal_expr,
                    temporal_type=temporal_type,
                    event_type=event_type,
                    participants=participant_ids,
                    location=raw.get("location"),
                    source_chunk_ids=[chunk.id],
                    source_document_id=context.document_id or chunk.document_id,
                    confidence=float(raw.get("confidence", 0.8)),
                )
                events.append(event)
            except Exception as e:
                logger.warning("Failed to create event: %s", e)
        return events

    def _parse_temporal(self, expression: str) -> Optional[datetime]:
        """Parse temporal expression to datetime."""
        if not expression:
            return None

        # ISO format: 2024-01-15
        iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", expression)
        if iso_match:
            try:
                return datetime(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                pass

        # Relative patterns
        if "today" in expression.lower():
            return datetime.now().replace(hour=0, minute=0, second=0)
        if "yesterday" in expression.lower():
            from datetime import timedelta

            return (datetime.now() - timedelta(days=1)).replace(
                hour=0, minute=0, second=0
            )

        return None
