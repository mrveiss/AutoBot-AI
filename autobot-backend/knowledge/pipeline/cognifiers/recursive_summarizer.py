# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RLM-Enhanced Recursive Summarizer — quality-gated summarization.

Wraps the existing HierarchicalSummarizer with RLM quality evaluation.
Each summary is scored; if it falls below the quality threshold the LLM
re-generates with the critique as guidance, up to a configurable depth.

Issue #1383: Follow-up from #1373.
"""

import logging
from typing import Dict, List, Optional
from uuid import UUID

from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import (
    build_entity_map,
    parse_llm_json_response,
)
from knowledge.pipeline.cognifiers.summarizer import SUMMARY_PROMPT
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.summary import Summary, SummaryLevel
from knowledge.pipeline.registry import TaskRegistry
from llm_interface_pkg import LLMInterface
from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import RLMConfig

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Evaluation prompt specialised for summaries
# -----------------------------------------------------------------------

_SUMMARY_EVAL_QUERY = (
    "Summarize the following text accurately, preserving key facts "
    "and source attribution: {source_preview}"
)


@TaskRegistry.register_cognifier("recursive_summarize")
class RecursiveSummarizer(BaseCognifier):
    """RLM-enhanced summarizer with quality-gated refinement.

    Generates summaries at chunk, section, and document levels — same
    hierarchy as ``HierarchicalSummarizer`` — but evaluates each summary
    with ``ResponseQualityEvaluator`` and re-generates up to
    ``max_refinement_depth`` times if the quality score is below
    threshold.
    """

    def __init__(
        self,
        chunk_max_words: int = 50,
        section_max_words: int = 150,
        document_max_words: int = 300,
        section_size: int = 5,
        max_refinement_depth: int = 2,
        rlm_config: Optional[RLMConfig] = None,
    ) -> None:
        self.chunk_max_words = chunk_max_words
        self.section_max_words = section_max_words
        self.document_max_words = document_max_words
        self.section_size = section_size
        self.max_refinement_depth = max_refinement_depth
        self.rlm_config = rlm_config or RLMConfig(
            max_reflections=max_refinement_depth,
            quality_threshold=0.7,
        )
        self.llm = LLMInterface()
        self.evaluator = ResponseQualityEvaluator(config=self.rlm_config)

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Generate quality-gated hierarchical summaries."""
        chunks: List[ProcessedChunk] = context.chunks
        entities: List[Entity] = context.entities
        entity_map = build_entity_map(entities, include_canonical=False)

        chunk_summaries = await self._summarize_chunks(chunks, entity_map, context)

        sections = self._group_into_sections(chunks)
        section_summaries = await self._summarize_sections(
            sections, chunk_summaries, entity_map, context
        )

        doc_summary = await self._summarize_document(
            section_summaries, entity_map, context
        )

        all_summaries = chunk_summaries + section_summaries
        if doc_summary:
            all_summaries.append(doc_summary)

        context.summaries = all_summaries
        logger.info(
            "Recursive summarizer: %d summaries (depth=%d)",
            len(all_summaries),
            self.max_refinement_depth,
        )
        return context

    # ------------------------------------------------------------------
    # Level generators
    # ------------------------------------------------------------------

    async def _summarize_chunks(
        self,
        chunks: List[ProcessedChunk],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[Summary]:
        summaries = []
        for chunk in chunks:
            summary = await self._summarize_with_refinement(
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

    async def _summarize_sections(
        self,
        sections: List[List[ProcessedChunk]],
        chunk_summaries: List[Summary],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> List[Summary]:
        summaries = []
        chunk_map = {
            s.source_chunk_ids[0]: s for s in chunk_summaries if s.source_chunk_ids
        }

        for section in sections:
            text = "\n\n".join(c.content for c in section)
            chunk_ids = [c.id for c in section]

            summary = await self._summarize_with_refinement(
                text,
                chunk_ids,
                context.document_id or section[0].document_id,
                "section",
                self.section_max_words,
                entity_map,
            )
            if summary:
                for cid in chunk_ids:
                    if cid in chunk_map:
                        child = chunk_map[cid]
                        child.parent_summary_id = summary.id
                        summary.child_summary_ids.append(child.id)
                summaries.append(summary)
        return summaries

    async def _summarize_document(
        self,
        section_summaries: List[Summary],
        entity_map: Dict[str, Entity],
        context: PipelineContext,
    ) -> Optional[Summary]:
        if not section_summaries:
            return None

        text = "\n\n".join(s.content for s in section_summaries)
        all_ids: List[UUID] = []
        for s in section_summaries:
            all_ids.extend(s.source_chunk_ids)

        summary = await self._summarize_with_refinement(
            text,
            all_ids,
            context.document_id or section_summaries[0].source_document_id,
            "document",
            self.document_max_words,
            entity_map,
        )
        if summary:
            for sec in section_summaries:
                sec.parent_summary_id = summary.id
                summary.child_summary_ids.append(sec.id)
        return summary

    # ------------------------------------------------------------------
    # Core: summarize → evaluate → refine loop
    # ------------------------------------------------------------------

    async def _summarize_with_refinement(
        self,
        text: str,
        source_chunk_ids: List[UUID],
        document_id: UUID,
        level: SummaryLevel,
        max_words: int,
        entity_map: Dict[str, Entity],
    ) -> Optional[Summary]:
        """Generate a summary, evaluate quality, refine if needed."""
        prompt = SUMMARY_PROMPT.format(max_words=max_words, text=text)
        source_preview = text[:200]
        best_summary: Optional[Summary] = None
        best_score = 0.0

        for attempt in range(self.max_refinement_depth + 1):
            try:
                parsed = await self._generate_and_parse(prompt)
                summary_text = parsed.get("summary", "")
                if not summary_text:
                    continue

                result = await self.evaluator.evaluate(
                    query=_SUMMARY_EVAL_QUERY.format(source_preview=source_preview),
                    response=summary_text,
                    iteration=attempt + 1,
                )

                candidate = self._build_summary(
                    parsed,
                    text,
                    level,
                    source_chunk_ids,
                    document_id,
                    entity_map,
                )
                if result.quality_score > best_score:
                    best_score = result.quality_score
                    best_summary = candidate

                if result.quality_score >= self.rlm_config.quality_threshold:
                    logger.debug(
                        "Summary accepted (%.2f) on attempt %d",
                        result.quality_score,
                        attempt + 1,
                    )
                    break

                hint = result.refinement_hint or result.critique
                prompt = (
                    SUMMARY_PROMPT.format(max_words=max_words, text=text)
                    + f"\n\n[Feedback — improve your summary: {hint}]"
                )
            except Exception as exc:
                logger.warning(
                    "Recursive summarizer attempt %d failed: %s",
                    attempt + 1,
                    exc,
                )

        return best_summary

    async def _generate_and_parse(self, prompt: str) -> dict:
        """Call LLM and parse JSON response (#1383: extracted helper)."""
        response = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}]
        )
        raw = parse_llm_json_response(response.content, fallback_dict=True)
        if isinstance(raw, dict):
            return raw
        return {"summary": "", "key_topics": [], "key_entities": []}

    def _build_summary(
        self,
        parsed: dict,
        source_text: str,
        level: SummaryLevel,
        source_chunk_ids: List[UUID],
        document_id: UUID,
        entity_map: Dict[str, Entity],
    ) -> Summary:
        """Construct a Summary from parsed LLM output (#1383: extracted)."""
        summary_text = parsed.get("summary", "")
        entity_ids = self._resolve_entity_ids(
            parsed.get("key_entities", []), entity_map
        )
        word_count = len(summary_text.split())
        original_words = len(source_text.split())
        ratio = word_count / original_words if original_words else 0.0

        return Summary(
            content=summary_text,
            level=level,
            source_chunk_ids=source_chunk_ids,
            source_document_id=document_id,
            key_topics=parsed.get("key_topics", []),
            key_entities=entity_ids,
            word_count=word_count,
            compression_ratio=ratio,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _group_into_sections(
        self, chunks: List[ProcessedChunk]
    ) -> List[List[ProcessedChunk]]:
        sections = []
        for i in range(0, len(chunks), self.section_size):
            sections.append(chunks[i : i + self.section_size])
        return sections

    @staticmethod
    def _resolve_entity_ids(
        entity_names: List[str],
        entity_map: Dict[str, Entity],
    ) -> List[UUID]:
        ids = []
        for name in entity_names:
            entity = entity_map.get(name.lower())
            if entity:
                ids.append(entity.id)
        return ids
