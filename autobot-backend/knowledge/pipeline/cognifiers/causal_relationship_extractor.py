# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Causal Relationship Extractor Cognifier - Extract causal knowledge from documents.

Issue #3395: RAG semantic chunking, fact extraction, entity resolution.

Extracts explicit causal relationships ("X CAUSES Y BECAUSE Z") from text,
distinguishing causality from correlation. Uses LLM guidance for high-confidence
extraction with condition detection and evidence tracking.
"""

from typing import Any, Dict, List, get_args

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import (
    batched_chunk_extract,
    literal_prompt_list,
    parse_llm_json_response,
    render_prompt_sentinels,
)
from knowledge.pipeline.models.causal_edge import CausalEdge, EffectType
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.registry import TaskRegistry
from llm_shared.types import LLMType
from services.llm_service import get_llm_service

logger = get_logger(__name__)

# Allowed effect-type values derived from the EffectType Literal (#11017) so the
# prompt fragment and the validation set can never drift from the type.
_EFFECT_TYPES = tuple(get_args(EffectType))
_EFFECT_TYPES_STR = literal_prompt_list(EffectType)

CAUSAL_EXTRACTION_PROMPT = render_prompt_sentinels(
    """Extract CAUSAL relationships from the following text.

CRITICAL: Distinguish explicit causality from correlation:
- ACCEPT: "X causes Y", "X leads to Y", "X results in Y", "if X then Y", "because X, Y happens"
- REJECT: "X and Y both increase", "X is correlated with Y", "X and Y tend to occur together"

For each causal relationship, provide:
- source_name: The cause entity (e.g., "cache_ttl", "request_rate")
- target_name: The effect entity (e.g., "query_latency", "memory_usage")
- effect_type: One of %%EFFECT_TYPES%%
- condition: When does this causality hold? (e.g., "when cache is full", "under high load",
  or empty string for unconditional)
- evidence_text: The exact sentence supporting this causality
- confidence: 0.9-1.0 for explicit statements, 0.7-0.85 for strong inference, reject (<0.7)

Return JSON array:
[{{
  "source_name": "cache_ttl",
  "target_name": "query_latency",
  "effect_type": "REDUCES",
  "condition": "when cache is enabled",
  "evidence_text": "Shorter cache TTLs reduce query latency by forcing fresh data retrieval.",
  "confidence": 0.95
}}, ...]

Return empty array [] if no clear causal relationships found.

Text:
{text}
""",
    {"EFFECT_TYPES": _EFFECT_TYPES_STR},
)

CAUSAL_EXTRACTION_BATCH_PROMPT = render_prompt_sentinels(
    """Extract CAUSAL relationships from each of the following text chunks.

CRITICAL: Distinguish explicit causality from correlation:
- ACCEPT: "X causes Y", "X leads to Y", "X results in Y", "if X then Y", "because X, Y happens"
- REJECT: "X and Y both increase", "X is correlated with Y", "X and Y tend to occur together"

Each chunk is labeled "Chunk N:". For each causal relationship provide:
- source_name, target_name
- effect_type: One of %%EFFECT_TYPES%%
- condition (empty string if unconditional)
- evidence_text: The exact sentence supporting this causality
- confidence: 0.9-1.0 explicit, 0.7-0.85 strong inference, reject (<0.7)

Return a JSON object mapping each chunk index (as a string) to its array of
causal relationships (same fields as above); use an empty array for chunks with
no clear causality. Example for two chunks:
{{
  "0": [{{"source_name": "cache_ttl", "target_name": "query_latency", "effect_type": "REDUCES",
         "condition": "", "evidence_text": "...", "confidence": 0.95}}],
  "1": []
}}

Chunks:
{chunks}
""",
    {"EFFECT_TYPES": _EFFECT_TYPES_STR},
)


# NLP patterns for lightweight causal detection (fallback mode)
CAUSAL_KEYWORDS = {
    "cause": "CAUSES",
    "causes": "CAUSES",
    "caused": "CAUSES",
    "lead": "CAUSES",
    "leads": "CAUSES",
    "result": "CAUSES",
    "results": "CAUSES",
    "enable": "ENABLES",
    "enables": "ENABLES",
    "prevent": "PREVENTS",
    "prevents": "PREVENTS",
    "inhibit": "INHIBITS",
    "inhibits": "INHIBITS",
    "increase": "AMPLIFIES",
    "increases": "AMPLIFIES",
    "amplify": "AMPLIFIES",
    "amplifies": "AMPLIFIES",
    "decrease": "REDUCES",
    "decreases": "REDUCES",
    "reduce": "REDUCES",
    "reduces": "REDUCES",
    "accelerate": "ACCELERATES",
    "accelerates": "ACCELERATES",
    "decelerate": "DECELERATES",
    "decelerates": "DECELERATES",
    "slow": "DECELERATES",
    "slows": "DECELERATES",
}

# Reject patterns (correlation/association, not causality)
REJECT_PATTERNS = {
    "correlat",
    "associate",
    "related to",
    "together with",
    "along with",
    "and",  # simple conjunction often signals correlation
}


@TaskRegistry.register_cognifier("extract_causal_relationships")
class CausalRelationshipExtractor(BaseCognifier):
    """
    Extract causal relationships from text chunks using LLM guidance.

    Identifies explicit causality patterns while filtering out correlations.
    Includes condition detection and evidence tracking for traceability.

    Issue #3395: Causal knowledge extraction for RAG graph structure.
    """

    def __init__(
        self,
        batch_size: int = 5,
        mode: str = "auto",
        nlp_threshold: int = 500,
        min_confidence: float = 0.7,
    ) -> None:
        """
        Initialize causal relationship extractor.

        Args:
            batch_size: Number of chunks to process per LLM batch
            mode: Extraction mode — "llm", "nlp", or "auto"
            nlp_threshold: Chunk count above which auto selects NLP
            min_confidence: Minimum confidence threshold for results (0.0-1.0)
        """
        self.batch_size = batch_size
        self.mode = mode
        self.nlp_threshold = nlp_threshold
        self.min_confidence = min_confidence
        self.llm = get_llm_service()

    def _select_mode(self, chunks: List[ProcessedChunk]) -> str:
        """
        Select extraction mode based on chunk count.

        Args:
            chunks: Input chunks

        Returns:
            "nlp" or "llm"
        """
        if self.mode != "auto":
            return self.mode
        return "nlp" if len(chunks) > self.nlp_threshold else "llm"

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract causal relationships from chunks.

        Args:
            context: Pipeline context with chunks

        Returns:
            Updated context with causal_edges
        """
        chunks: List[ProcessedChunk] = context.chunks
        if not chunks:
            logger.warning("No chunks for causal extraction")
            return context

        selected = self._select_mode(chunks)
        logger.info("Causal extraction mode: %s (%d chunks)", selected, len(chunks))

        if selected == "nlp":
            causal_edges = self._nlp_extract(chunks, context.document_id)
        else:
            causal_edges = await self._llm_process(chunks, context)

        # Store in context (extend existing list if any)
        if not hasattr(context, "causal_edges"):
            context.causal_edges = []
        context.causal_edges.extend(causal_edges)

        logger.info("Extracted %d causal edges", len(causal_edges))
        return context

    def _nlp_extract(self, chunks: List[ProcessedChunk], document_id) -> List[CausalEdge]:
        """
        Extract causal edges using lightweight NLP patterns.

        Args:
            chunks: Chunks to process
            document_id: Source document ID

        Returns:
            List of CausalEdge objects with moderate confidence
        """
        edges: List[CausalEdge] = []
        for chunk in chunks:
            chunk_edges = self._nlp_extract_chunk(chunk, document_id)
            edges.extend(chunk_edges)
        return edges

    def _nlp_extract_chunk(self, chunk: ProcessedChunk, document_id) -> List[CausalEdge]:
        """
        Extract causal edges from single chunk via keyword matching.

        Args:
            chunk: Chunk to process
            document_id: Source document ID

        Returns:
            List of CausalEdge objects
        """
        chunk.content.lower()
        edges: List[CausalEdge] = []

        # Simple heuristic: find sentences with causal keywords
        sentences = chunk.content.split(".")
        for sent in sentences:
            sent_lower = sent.lower()

            # Reject correlation patterns
            if any(pattern in sent_lower for pattern in REJECT_PATTERNS):
                continue

            # Find causal keyword
            causal_type = None
            keyword_match = None
            for keyword, effect_type in CAUSAL_KEYWORDS.items():
                if keyword in sent_lower:
                    causal_type = effect_type
                    keyword_match = keyword
                    break

            if not causal_type:
                continue

            # Simple extraction: assume "X keyword Y" pattern
            # This is a basic heuristic; LLM mode is more accurate
            words = sent.strip().split()
            if len(words) >= 3:
                # Rough guess at source/target based on keyword position
                try:
                    idx = sent_lower.find(keyword_match)
                    before = sent[:idx].strip().split()
                    after = sent[idx + len(keyword_match) :].strip().split()

                    source = before[-1] if before else "unknown"
                    target = after[1] if len(after) > 1 else (after[0] if after else "unknown")

                    # Clean up word fragments
                    source = source.strip("(),;:")
                    target = target.strip("(),;:")

                    if source and target and source != target:
                        edge = CausalEdge(
                            source_name=source,
                            target_name=target,
                            effect_type=causal_type,
                            condition="",
                            confidence=0.6,  # Low confidence for NLP-only extraction
                            evidence_text=sent.strip(),
                            source_chunk_ids=[chunk.id],
                        )
                        edges.append(edge)
                except (IndexError, ValueError):
                    pass

        return edges

    async def _llm_process(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[CausalEdge]:
        """
        Run LLM-based extraction over chunks in batches.

        Args:
            chunks: Chunks to process
            context: Pipeline context

        Returns:
            List of extracted causal edges
        """
        all_edges: List[CausalEdge] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_edges = await self._process_batch(batch, context)
            all_edges.extend(batch_edges)
        return all_edges

    async def _process_batch(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[CausalEdge]:
        """Extract causal edges for a batch in ONE LLM call when batching is on (#10598).

        Routes through ``batched_chunk_extract`` (index-keyed prompt, per-chunk
        fallback) so K chunks cost one round-trip instead of K. The helper runs
        the legacy per-chunk loop itself when the config flag is disabled (#11090).
        """
        return await batched_chunk_extract(
            chunks,
            llm=self.llm,
            batch_prompt_template=CAUSAL_EXTRACTION_BATCH_PROMPT,
            llm_type=LLMType.EXTRACTION,
            max_chunk_chars=config.cognifier_batch_max_chunk_chars,
            convert=lambda raw, chunk: self._convert_to_causal_edges(raw, chunk, context.document_id),
            extract_one=lambda chunk: self._extract_from_chunk(chunk, context),
        )

    async def _extract_from_chunk(self, chunk: ProcessedChunk, context: PipelineContext) -> List[CausalEdge]:
        """
        Extract causal edges from single chunk using LLM.

        Args:
            chunk: Chunk to process
            context: Pipeline context

        Returns:
            List of causal edges from chunk
        """
        prompt = CAUSAL_EXTRACTION_PROMPT.format(text=chunk.content)
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}], llm_type=LLMType.EXTRACTION, structured_output=True
            )
            # #10645: parse strictly so malformed JSON surfaces as an error
            # rather than being silently coerced; a bad response for one chunk
            # must not crash the whole document pipeline, so log + skip it.
            parsed = parse_llm_json_response(response.content, strict=True)
        except Exception as e:
            logger.error("Causal extraction failed for chunk (skipping): %s", e)
            return []
        raw_edges = parsed if isinstance(parsed, list) else []
        return self._convert_to_causal_edges(raw_edges, chunk, context.document_id)

    def _convert_to_causal_edges(
        self, raw_edges: List[Dict[str, Any]], chunk: ProcessedChunk, document_id
    ) -> List[CausalEdge]:
        """
        Convert raw LLM output to CausalEdge objects.

        Args:
            raw_edges: Raw edge dicts from LLM
            chunk: Source chunk
            document_id: Document ID

        Returns:
            List of validated CausalEdge objects
        """
        edges = []
        for raw in raw_edges:
            try:
                confidence = float(raw.get("confidence", 0.8))

                # Filter by confidence threshold
                if confidence < self.min_confidence:
                    logger.debug(
                        "Skipping edge below confidence (%.2f < %.2f)",
                        confidence,
                        self.min_confidence,
                    )
                    continue

                effect_type = raw.get("effect_type", "CAUSES")
                if effect_type not in _EFFECT_TYPES:
                    effect_type = "CAUSES"

                edge = CausalEdge(
                    source_name=raw.get("source_name", ""),
                    target_name=raw.get("target_name", ""),
                    effect_type=effect_type,
                    condition=raw.get("condition", ""),
                    confidence=confidence,
                    evidence_text=raw.get("evidence_text", ""),
                    evidence_source=None,
                    source_chunk_ids=[chunk.id],
                )

                # Validate required fields
                if not edge.source_name or not edge.target_name:
                    logger.warning("Skipping edge with missing source/target")
                    continue

                edges.append(edge)
            except Exception as e:
                logger.warning("Failed to create causal edge: %s", e)

        return edges
