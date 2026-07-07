# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fact Extractor Cognifier - Extract atomic facts from text chunks.

Issue #3395: RAG optimization — semantic chunking, fact extraction, entity resolution.
Phase 2 — Atomic Facts Extraction: Extract atomic factual statements from documents
as discrete retrievable units alongside full chunks.
"""

import re
from typing import Any, Dict, List, get_args
from uuid import UUID

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import (
    batched_chunk_extract,
    literal_prompt_list,
    parse_llm_json_response,
    render_prompt_sentinels,
)
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.fact import AtomicFact, FactType
from knowledge.pipeline.registry import TaskRegistry
from llm_shared.types import LLMType
from services.llm_service import get_llm_service

logger = get_logger(__name__)

# Single source of truth for the allowed fact-type values (#11017): derived from
# the ``FactType`` Literal so the prompt fragment and the validation set can never
# drift from the type. Adding a value to FactType updates both at once.
_FACT_TYPES = tuple(get_args(FactType))
_FACT_TYPES_STR = literal_prompt_list(FactType, quote=True)

# Max characters of a chunk sent to the LLM (shared by per-chunk and batched paths).
MAX_CHUNK_CHARS = 2000

FACT_EXTRACTION_PROMPT = render_prompt_sentinels(
    """Extract atomic facts from the following text.

For each fact, provide:
- subject: Main subject or entity (e.g., "AutoBot", "ChromaDB")
- predicate: Relationship or property (e.g., "is", "enables", "has")
- object: Object entity or value (e.g., "AI platform", "knowledge base")
- fact_type: One of %%FACT_TYPES%%
- description: Natural language description of the fact
- context: Supporting context from the text (relevant sentence or phrase)
- confidence: Score 0.0-1.0 indicating extraction confidence

Return JSON array of facts:
[{{
  "subject": "...",
  "predicate": "...",
  "object": "...",
  "fact_type": "statement",
  "description": "...",
  "context": "...",
  "confidence": 0.9
}}, ...]

Text:
{text}
""",
    {"FACT_TYPES": _FACT_TYPES_STR},
)

# Batched variant (#10647): extract facts from multiple labeled chunks in one
# call, keyed by chunk index, to cut LLM round-trips.
FACT_EXTRACTION_BATCH_PROMPT = render_prompt_sentinels(
    """Extract atomic facts from each of the following text chunks.

Each chunk is labeled "Chunk N:". For each fact provide:
- subject, predicate, object
- fact_type: One of %%FACT_TYPES%%
- description, context, confidence (0.0-1.0)

Return a JSON object mapping each chunk index (as a string) to its array of facts
(each fact uses the same fields listed above); use an empty array for chunks with
no facts. Example for two chunks:
{{
  "0": [
    {{"subject": "...", "predicate": "...", "object": "...",
      "fact_type": "statement", "description": "...", "context": "...", "confidence": 0.9}}
  ],
  "1": []
}}

Chunks:
{chunks}
""",
    {"FACT_TYPES": _FACT_TYPES_STR},
)

# NLP-based patterns for fact extraction (Issue #3395)
# Used when sentence-level parsing can identify simple facts
NLP_PATTERNS = [
    # "X is Y" patterns
    (r"(\w+)\s+is\s+(?:an?\s+)?(.+?)(?:\.|,|;|$)", "is", "statement"),
    # "X enables/allows/causes/prevents Y"
    (
        r"(\w+)\s+(?:enables|allows|causes|prevents)\s+(.+?)(?:\.|,|;|$)",
        "enables",
        "relationship",
    ),
    # "X has Y" or "X has property Y"
    (r"(\w+)\s+has\s+(?:an?\s+)?(.+?)(?:\.|,|;|$)", "has", "property"),
    # "X uses Y" or "X integrates Y"
    (
        r"(\w+)\s+(?:uses|integrates|employs)\s+(?:an?\s+)?(.+?)(?:\.|,|;|$)",
        "uses",
        "relationship",
    ),
    # "X contains Y" or "X includes Y"
    (
        r"(\w+)\s+(?:contains|includes)\s+(?:an?\s+)?(.+?)(?:\.|,|;|$)",
        "contains",
        "relationship",
    ),
]

# Valid fact types — derived from the FactType Literal (#11017) so validation
# can never drift from the type or the prompt fragment above.
VALID_FACT_TYPES = frozenset(_FACT_TYPES)


@TaskRegistry.register_cognifier("extract_facts")
class FactExtractor(BaseCognifier):
    """Extract atomic facts from text chunks using LLM or NLP patterns."""

    def __init__(
        self,
        batch_size: int = 5,
        mode: str = "auto",
        nlp_threshold: int = 500,
        use_patterns: bool = True,
    ) -> None:
        """
        Initialize fact extractor.

        Args:
            batch_size: Number of chunks to process per LLM batch
            mode: Extraction mode — "llm", "nlp", or "auto"
            nlp_threshold: Chunk count above which auto selects NLP
            use_patterns: Whether to use regex patterns for NLP mode
        """
        self.batch_size = batch_size
        self.mode = mode
        self.nlp_threshold = nlp_threshold
        self.use_patterns = use_patterns
        self.llm = get_llm_service()

    def _select_mode(self, chunks: List[ProcessedChunk]) -> str:
        """
        Select extraction mode based on chunk count (Issue #3395).

        Args:
            chunks: Input chunks

        Returns:
            "nlp" or "llm"
        """
        if self.mode != "auto":
            return self.mode
        return "nlp" if len(chunks) > self.nlp_threshold else "llm"

    def _nlp_extract(self, chunks: List[ProcessedChunk], document_id: UUID | None) -> List[AtomicFact]:
        """
        Extract facts from chunks using NLP patterns (Issue #3395).

        Applies regex patterns to sentences to identify simple subject-predicate-object
        facts. More efficient than LLM for large document sets.

        Args:
            chunks: Chunks to process
            document_id: Source document ID

        Returns:
            List of extracted AtomicFact objects
        """
        facts: List[AtomicFact] = []

        for chunk in chunks:
            sentences = self._split_sentences(chunk.content)
            for sentence in sentences:
                for pattern, predicate, fact_type in NLP_PATTERNS:
                    matches = re.finditer(pattern, sentence, re.IGNORECASE)
                    for match in matches:
                        subject = match.group(1).strip()
                        obj = match.group(2).strip()

                        if subject and obj and len(subject) < 50 and len(obj) < 100:
                            fact = AtomicFact(
                                subject=subject,
                                predicate=predicate,
                                object=obj,
                                fact_type=fact_type,
                                description=sentence[:200],
                                context=sentence,
                                source_chunk_ids=[chunk.id],
                                source_document_id=document_id or chunk.document_id,
                                confidence=0.7,
                            )
                            facts.append(fact)

        return self._deduplicate_facts(facts)

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences for pattern matching (Issue #3395).

        Args:
            text: Input text

        Returns:
            List of sentence strings
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract atomic facts from chunks in context (Issue #3395).

        Selects LLM or NLP extraction based on mode/threshold. Facts are
        deduplicated and stored in context for downstream loading.

        Args:
            context: Pipeline context with chunks

        Returns:
            Updated context with facts
        """
        chunks: List[ProcessedChunk] = context.chunks
        selected = self._select_mode(chunks)
        logger.info("Fact extraction mode: %s (%d chunks)", selected, len(chunks))

        if selected == "nlp":
            all_facts = self._nlp_extract(chunks, context.document_id)
        else:
            all_facts = await self._llm_process(chunks, context)

        dedup_facts = self._deduplicate_facts(all_facts)
        context.facts = dedup_facts
        logger.info("Extracted %d atomic facts", len(dedup_facts))
        return context

    async def _llm_process(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[AtomicFact]:
        """Run LLM-based fact extraction over all chunks in batches."""
        all_facts: List[AtomicFact] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_facts = await self._process_batch(batch, context)
            all_facts.extend(batch_facts)
        return all_facts

    async def _process_batch(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[AtomicFact]:
        """Extract facts for a batch in ONE LLM call when batching is on (#10647/#11017).

        Routes through the shared ``batched_chunk_extract`` helper (index-keyed
        prompt, per-*missing*-chunk fallback, batch-scaled ``max_tokens``) instead
        of a fact-local reimplementation — so fact extraction honors the
        ``cognifier_multichunk_batching`` / ``cognifier_batch_max_chunk_chars``
        config like the other extractors and inherits the #11012 partial-response
        fix. ``batched_chunk_extract`` honors the flag itself, running the legacy
        per-chunk loop when it is disabled (#11090).
        """
        return await batched_chunk_extract(
            chunks,
            llm=self.llm,
            batch_prompt_template=FACT_EXTRACTION_BATCH_PROMPT,
            llm_type=LLMType.EXTRACTION,
            max_chunk_chars=config.cognifier_batch_max_chunk_chars,
            convert=lambda raw, chunk: self._convert_to_facts(raw, chunk, context.document_id),
            extract_one=lambda chunk: self._extract_from_chunk(chunk, context),
        )

    async def _extract_from_chunk(self, chunk: ProcessedChunk, context: PipelineContext) -> List[AtomicFact]:
        """Extract facts from a single chunk using LLM.

        Transient LLM errors are caught and return an empty list.
        Format and parse errors are re-raised (#10645).
        """
        prompt = FACT_EXTRACTION_PROMPT.format(text=chunk.content[:MAX_CHUNK_CHARS])
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}], llm_type=LLMType.EXTRACTION, structured_output=True
            )
        except Exception as e:
            logger.error("Fact extraction LLM call failed (transient) for chunk %s: %s", chunk.id, e)
            return []
        parsed = parse_llm_json_response(response.content, strict=True)
        raw_facts = parsed if isinstance(parsed, list) else []
        return self._convert_to_facts(raw_facts, chunk, context.document_id)

    def _convert_to_facts(
        self,
        raw_facts: List[Dict[str, Any]],
        chunk: ProcessedChunk,
        document_id: UUID | None,
    ) -> List[AtomicFact]:
        """Convert raw fact dicts to AtomicFact objects."""
        facts = []
        for raw in raw_facts:
            try:
                fact_type = raw.get("fact_type", "statement")
                if fact_type not in VALID_FACT_TYPES:
                    fact_type = "statement"

                fact = AtomicFact(
                    subject=raw["subject"].strip(),
                    predicate=raw["predicate"].strip(),
                    object=raw["object"].strip(),
                    fact_type=fact_type,
                    description=raw.get("description", ""),
                    context=raw.get("context", ""),
                    source_chunk_ids=[chunk.id],
                    source_document_id=document_id or chunk.document_id,
                    confidence=float(raw.get("confidence", 0.8)),
                )
                facts.append(fact)
            except (KeyError, ValueError) as e:
                logger.warning("Failed to create fact: %s", e)
        return facts

    def _deduplicate_facts(self, facts: List[AtomicFact]) -> List[AtomicFact]:
        """
        Deduplicate facts by normalized triple (Issue #3395).

        Facts with identical subject-predicate-object triples (case-insensitive)
        are merged, updating confidence and chunk references.

        Args:
            facts: List of facts to deduplicate

        Returns:
            Deduplicated list of facts
        """
        fact_map: Dict[tuple, AtomicFact] = {}

        for fact in facts:
            key = self._normalize_triple(fact.subject, fact.predicate, fact.object_)
            if key in fact_map:
                existing = fact_map[key]
                existing.source_chunk_ids.extend(fact.source_chunk_ids)
                existing.source_chunk_ids = list(set(existing.source_chunk_ids))
                existing.supported_by_count += 1
                existing.confidence = min(1.0, existing.confidence + 0.05)
            else:
                fact_map[key] = fact

        return list(fact_map.values())

    def _normalize_triple(self, subject: str, predicate: str, obj: str) -> tuple:
        """Normalize fact triple for deduplication."""
        return (
            subject.lower().strip(),
            predicate.lower().strip(),
            obj.lower().strip(),
        )
