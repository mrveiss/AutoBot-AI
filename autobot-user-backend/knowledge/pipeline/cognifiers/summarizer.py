# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hierarchical Summarizer Cognifier - Generate multi-level summaries.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import json
import logging
from typing import Any, Dict, List
from uuid import UUID

from llm_interface_pkg import LLMInterface

from backend.knowledge.pipeline.base import BaseCognifier, PipelineContext
from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.entity import Entity
from backend.knowledge.pipeline.models.summary import Summary, SummaryLevel
from backend.knowledge.pipeline.registry import TaskRegistry

logger = logging.getLogger(__name__)


SUMMARY_PROMPT = """Summarize the following text in {max_words} words or less.

Include:
- key_topics: List of 3-5 main topics
- key_entities: List of entity names mentioned
- summary: The summary text

Return JSON: {{"summary": "...", "key_topics": [...], "key_entities": [...]}}

Text:
{text}
"""


@TaskRegistry.register_cognifier("generate_summaries")
class HierarchicalSummarizer(BaseCognifier):
    """Generate hierarchical summaries at multiple levels."""

    def __init__(
        self,
        chunk_max_words: int = 50,
        section_max_words: int = 150,
        document_max_words: int = 300,
        section_size: int = 5,
    ) -> None:
        """
        Initialize hierarchical summarizer.

        Args:
            chunk_max_words: Max words for chunk-level summaries
            section_max_words: Max words for section-level summaries
            document_max_words: Max words for document-level summaries
            section_size: Number of chunks per section
        """
        self.chunk_max_words = chunk_max_words
        self.section_max_words = section_max_words
        self.document_max_words = document_max_words
        self.section_size = section_size
        self.llm = LLMInterface()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Generate hierarchical summaries.

        Args:
            context: Pipeline context with chunks and entities

        Returns:
            Updated context with summaries
        """
        chunks: List[ProcessedChunk] = context.chunks
        entities: List[Entity] = context.entities
        entity_map = self._build_entity_map(entities)

        # Level 1: Chunk summaries
        chunk_summaries = await self._generate_chunk_summaries(
            chunks, entity_map, context
        )

        # Level 2: Section summaries
        sections = self._group_into_sections(chunks)
        section_summaries = await self._generate_section_summaries(
            sections, chunk_summaries, entity_map, context
        )

        # Level 3: Document summary
        document_summary = await self._generate_document_summary(
            section_summaries, entity_map, context
        )

        all_summaries = chunk_summaries + section_summaries
        if document_summary:
            all_summaries.append(document_summary)

        context.summaries = all_summaries
        logger.info("Generated %s summaries", len(all_summaries))
        return context

    def _build_entity_map(self, entities: List[Entity]) -> Dict[str, Entity]:
        """Build name-to-entity mapping."""
        entity_map: Dict[str, Entity] = {}
        for entity in entities:
            entity_map[entity.name.lower()] = entity
        return entity_map

    def _group_into_sections(
        self, chunks: List[ProcessedChunk]
    ) -> List[List[ProcessedChunk]]:
        """Group chunks into sections."""
        sections = []
        for i in range(0, len(chunks), self.section_size):
            section = chunks[i : i + self.section_size]
            sections.append(section)
        return sections

    async def _generate_chunk_summaries(
        self,
        chunks: List[ProcessedChunk],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[Summary]:
        """Generate chunk-level summaries."""
        summaries = []
        for chunk in chunks:
            summary = await self._summarize_text(
                chunk.content,
                [chunk.id],
                context.document_id or chunk.document_id,
                "chunk",
                self.chunk_max_words,
                entity_map,
            )
            if summary:
                summaries.append(summary)
        return summaries

    async def _generate_section_summaries(
        self,
        sections: List[List[ProcessedChunk]],
        chunk_summaries: List[Summary],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[Summary]:
        """Generate section-level summaries."""
        summaries = []
        chunk_summary_map = {s.source_chunk_ids[0]: s for s in chunk_summaries}

        for section in sections:
            section_text = "\n\n".join([c.content for c in section])
            chunk_ids = [c.id for c in section]

            summary = await self._summarize_text(
                section_text,
                chunk_ids,
                context.document_id or section[0].document_id,
                "section",
                self.section_max_words,
                entity_map,
            )

            if summary:
                # Link to child chunk summaries
                for chunk_id in chunk_ids:
                    if chunk_id in chunk_summary_map:
                        child = chunk_summary_map[chunk_id]
                        child.parent_summary_id = summary.id
                        summary.child_summary_ids.append(child.id)
                summaries.append(summary)

        return summaries

    async def _generate_document_summary(
        self,
        section_summaries: List[Summary],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> Summary | None:
        """Generate document-level summary."""
        if not section_summaries:
            return None

        combined_text = "\n\n".join([s.content for s in section_summaries])
        all_chunk_ids = []
        for s in section_summaries:
            all_chunk_ids.extend(s.source_chunk_ids)

        summary = await self._summarize_text(
            combined_text,
            all_chunk_ids,
            context.document_id or section_summaries[0].source_document_id,
            "document",
            self.document_max_words,
            entity_map,
        )

        if summary:
            # Link to child section summaries
            for section in section_summaries:
                section.parent_summary_id = summary.id
                summary.child_summary_ids.append(section.id)

        return summary

    async def _summarize_text(
        self,
        text: str,
        source_chunk_ids: List[UUID],
        document_id: UUID,
        level: SummaryLevel,
        max_words: int,
        entity_map: Dict[str, Entity],
    ) -> Summary | None:
        """Summarize text using LLM."""
        try:
            prompt = SUMMARY_PROMPT.format(max_words=max_words, text=text)
            response = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}]
            )
            parsed = self._parse_llm_response(response.content)

            key_entity_ids = self._resolve_entity_ids(
                parsed.get("key_entities", []), entity_map
            )

            word_count = len(parsed["summary"].split())
            compression_ratio = word_count / len(text.split())

            return Summary(
                content=parsed["summary"],
                level=level,
                source_chunk_ids=source_chunk_ids,
                source_document_id=document_id,
                key_topics=parsed.get("key_topics", []),
                key_entities=key_entity_ids,
                word_count=word_count,
                compression_ratio=compression_ratio,
            )
        except Exception as e:
            logger.error("Summarization failed: %s", e)
            return None

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
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
            return {"summary": content, "key_topics": [], "key_entities": []}

    def _resolve_entity_ids(
        self, entity_names: List[str], entity_map: Dict[str, Entity]
    ) -> List[UUID]:
        """Resolve entity names to IDs."""
        ids = []
        for name in entity_names:
            entity = entity_map.get(name.lower())
            if entity:
                ids.append(entity.id)
        return ids
