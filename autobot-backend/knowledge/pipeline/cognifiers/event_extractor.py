# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Event Extractor Cognifier - Extract temporal events from text.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import (
    batched_chunk_extract,
    build_entity_map,
    parse_llm_json_response,
)
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.event import EventType, TemporalEvent, TemporalType
from knowledge.pipeline.registry import TaskRegistry
from services.llm_service import get_llm_service

logger = get_logger(__name__)


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

EVENT_EXTRACTION_BATCH_PROMPT = """Extract temporal events from each of the following text chunks.

Each chunk is labeled "Chunk N:". For each event provide:
- name: Event title
- description: Brief description
- temporal_expression: Time phrase (e.g., "yesterday", "2024-01-15")
- temporal_type: point, range, relative, recurring
- event_type: action, decision, change, milestone, occurrence
- participants: Entity names involved
- location: Where it happened (if mentioned)
- confidence: 0.0-1.0

Return a JSON object mapping each chunk index (as a string) to its array of
events (same fields as above); use an empty array for chunks with no events.
Example for two chunks:
{{
  "0": [{{"name": "...", "description": "...", "temporal_expression": "...", "temporal_type": "point", "event_type": "occurrence", "participants": [], "confidence": 0.9}}],
  "1": []
}}

Chunks:
{chunks}
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
        self.llm = get_llm_service()

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
        entity_map = build_entity_map(entities)
        all_events: List[TemporalEvent] = []

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_events = await self._process_batch(batch, entity_map, context)
            all_events.extend(batch_events)

        context.events = all_events
        logger.info("Extracted %s events", len(all_events))
        return context

    async def _process_batch(
        self,
        chunks: List[ProcessedChunk],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[TemporalEvent]:
        """Extract events for a batch in ONE LLM call when batching is on (#10598).

        Routes through ``batched_chunk_extract`` (index-keyed prompt, per-chunk
        fallback) so K chunks cost one round-trip instead of K. Falls back to the
        legacy per-chunk loop when the config flag is disabled.
        """
        if not config.cognifier_multichunk_batching:
            events = []
            for chunk in chunks:
                events.extend(await self._extract_from_chunk(chunk, entity_map, context))
            return events
        return await batched_chunk_extract(
            chunks,
            llm=self.llm,
            batch_prompt_template=EVENT_EXTRACTION_BATCH_PROMPT,
            llm_type="extraction",
            max_chunk_chars=config.cognifier_batch_max_chunk_chars,
            convert=lambda raw, chunk: self._convert_to_events(raw, chunk, entity_map, context),
            extract_one=lambda chunk: self._extract_from_chunk(chunk, entity_map, context),
        )

    async def _extract_from_chunk(
        self,
        chunk: ProcessedChunk,
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[TemporalEvent]:
        """Extract events from a single chunk.

        Transient LLM errors are caught and return an empty list.
        Format and parse errors are re-raised (#10645).
        """
        prompt = EVENT_EXTRACTION_PROMPT.format(text=chunk.content)
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}], llm_type="extraction", structured_output=True
            )
        except Exception as e:
            logger.error("Event extraction LLM call failed (transient): %s", e)
            return []
        parsed = parse_llm_json_response(response.content, strict=True)
        raw_events = parsed if isinstance(parsed, list) else []
        return self._convert_to_events(raw_events, chunk, entity_map, context)

    def _parse_llm_response(self, content: str) -> list:
        """
        Parse LLM JSON response for event extraction. Delegates to shared util.

        Args:
            content: Raw LLM response text

        Returns:
            Parsed list of event dicts, or empty list on failure
        """
        parsed = parse_llm_json_response(content)
        return parsed if isinstance(parsed, list) else []

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
                    entity_map[name.lower()].id for name in participant_names if name.lower() in entity_map
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
                    source_document_id=(context.document_id or chunk.document_id),
                    confidence=float(raw.get("confidence", 0.8)),
                )
                events.append(event)
            except Exception as e:
                logger.warning("Failed to create event: %s", e)
        return events

    def _parse_temporal(self, expression: str) -> datetime | None:
        """Parse temporal expression to datetime."""
        if not expression:
            return None

        # ISO format: 2024-01-15 — return naive datetime to match test expectations
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

        # Relative patterns — naive local date for consistency with ISO path
        now = datetime.now(tz=timezone.utc)
        if "today" in expression.lower():
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if "yesterday" in expression.lower():
            return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        return None
