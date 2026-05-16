# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Extractor Cognifier - Extract named entities from text chunks.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
Issue #2025: Dual-mode entity extraction — LLM + NLP (Neural Mesh RAG Phase 2).
"""

from typing import Any, Dict, List
from uuid import UUID

from autobot_shared.logging_manager import get_logger
from knowledge.pipeline.base import BaseCognifier, PipelineContext
from knowledge.pipeline.cognifiers.llm_utils import parse_llm_json_response
from knowledge.pipeline.models.chunk import ProcessedChunk
from knowledge.pipeline.models.entity import Entity, EntityType
from knowledge.pipeline.registry import TaskRegistry
from services.llm_service import get_llm_service

logger = get_logger(__name__)

# spaCy NER label → EntityType mapping (Issue #2025)
_SPACY_LABEL_MAP: Dict[str, str] = {
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "EVENT": "EVENT",
    "PRODUCT": "TECHNOLOGY",
    "LAW": "DOCUMENT",
    "WORK_OF_ART": "DOCUMENT",
    "FAC": "LOCATION",
    "NORP": "ORGANIZATION",
}

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
    """Extract named entities from text chunks using LLM or NLP (spaCy)."""

    def __init__(
        self,
        batch_size: int = 5,
        mode: str = "auto",
        nlp_threshold: int = 500,
    ) -> None:
        """
        Initialize entity extractor.

        Args:
            batch_size: Number of chunks to process per LLM batch
            mode: Extraction mode — "llm", "nlp", or "auto"
            nlp_threshold: Chunk count above which auto selects NLP (Issue #2025)
        """
        self.batch_size = batch_size
        self.mode = mode
        self.nlp_threshold = nlp_threshold
        self.llm = get_llm_service()
        self._nlp_model: Any | None = None

    def _get_nlp(self) -> Any:
        """
        Lazy-load spaCy en_core_web_sm model (Issue #2025).

        Returns:
            Loaded spaCy language model
        """
        if self._nlp_model is None:
            import spacy  # noqa: PLC0415

            self._nlp_model = spacy.load("en_core_web_sm")
        return self._nlp_model

    def _select_mode(self, chunks: List[ProcessedChunk]) -> str:
        """
        Select extraction mode based on chunk count and configured mode (Issue #2025).

        Args:
            chunks: Input chunks

        Returns:
            "nlp" or "llm"
        """
        if self.mode != "auto":
            return self.mode
        return "nlp" if len(chunks) > self.nlp_threshold else "llm"

    def _nlp_extract(self, chunks: List[ProcessedChunk], document_id: UUID | None) -> List[Entity]:
        """
        Extract entities from chunks using spaCy NER + noun phrases (Issue #2025).

        Named entities are mapped to EntityType via _SPACY_LABEL_MAP; unrecognised
        labels default to CONCEPT.  Noun chunks are added as CONCEPT entities with
        confidence 0.5.  Results are deduplicated by canonical_name before returning.

        Args:
            chunks: Chunks to process
            document_id: Source document ID

        Returns:
            Deduplicated list of Entity objects
        """
        nlp = self._get_nlp()
        seen: Dict[str, Entity] = {}

        for chunk in chunks:
            doc = nlp(chunk.content)
            self._collect_ner_entities(doc, chunk, document_id, seen)
            self._collect_noun_chunks(doc, chunk, document_id, seen)

        return list(seen.values())

    def _collect_ner_entities(
        self,
        doc: Any,
        chunk: ProcessedChunk,
        document_id: UUID | None,
        seen: Dict[str, Entity],
    ) -> None:
        """Add spaCy NER spans to the seen map (Issue #2025)."""
        for ent in doc.ents:
            entity_type = _SPACY_LABEL_MAP.get(ent.label_, "CONCEPT")
            self._upsert_entity(
                name=ent.text,
                entity_type=entity_type,
                confidence=0.8,
                chunk=chunk,
                document_id=document_id,
                seen=seen,
            )

    def _collect_noun_chunks(
        self,
        doc: Any,
        chunk: ProcessedChunk,
        document_id: UUID | None,
        seen: Dict[str, Entity],
    ) -> None:
        """Add spaCy noun-phrase chunks to the seen map (Issue #2025)."""
        for nc in doc.noun_chunks:
            self._upsert_entity(
                name=nc.text,
                entity_type="CONCEPT",
                confidence=0.5,
                chunk=chunk,
                document_id=document_id,
                seen=seen,
            )

    def _upsert_entity(
        self,
        name: str,
        entity_type: str,
        confidence: float,
        chunk: ProcessedChunk,
        document_id: UUID | None,
        seen: Dict[str, Entity],
    ) -> None:
        """Insert or update an entity in the seen map by canonical name (Issue #2025)."""
        canonical = self._normalize_name(name)
        if not canonical:
            return
        if canonical in seen:
            existing = seen[canonical]
            existing.source_chunk_ids.append(chunk.id)
            existing.extraction_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
        else:
            try:
                entity = Entity(
                    name=name,
                    canonical_name=canonical,
                    entity_type=entity_type,
                    confidence=confidence,
                    source_chunk_ids=[chunk.id],
                    source_document_id=document_id or chunk.document_id,
                )
                seen[canonical] = entity
            except Exception as exc:
                logger.warning("NLP entity creation failed for %r: %s", name, exc)

    async def process(self, context: PipelineContext) -> PipelineContext:
        """
        Extract entities from chunks in context.

        Selects LLM or NLP extraction based on mode/threshold (Issue #2025).

        Args:
            context: Pipeline context with chunks

        Returns:
            Updated context with entities
        """
        chunks: List[ProcessedChunk] = context.chunks
        selected = self._select_mode(chunks)
        logger.info("Entity extraction mode: %s (%d chunks)", selected, len(chunks))

        if selected == "nlp":
            all_entities = self._nlp_extract(chunks, context.document_id)
            merged_entities = self._merge_entities(all_entities)
        else:
            merged_entities = await self._llm_process(chunks, context)

        context.entities = merged_entities
        logger.info("Extracted %s entities", len(merged_entities))
        return context

    async def _llm_process(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[Entity]:
        """Run LLM-based extraction over all chunks in batches."""
        all_entities: List[Entity] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_entities = await self._process_batch(batch, context)
            all_entities.extend(batch_entities)
        return self._merge_entities(all_entities)

    async def _process_batch(self, chunks: List[ProcessedChunk], context: PipelineContext) -> List[Entity]:
        """Process a batch of chunks."""
        entities = []
        for chunk in chunks:
            chunk_entities = await self._extract_from_chunk(chunk, context)
            entities.extend(chunk_entities)
        return entities

    async def _extract_from_chunk(self, chunk: ProcessedChunk, context: PipelineContext) -> List[Entity]:
        """Extract entities from a single chunk."""
        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=chunk.content)
            response = await self.llm.chat([{"role": "user", "content": prompt}])
            parsed = parse_llm_json_response(response.content)
            raw_entities = parsed if isinstance(parsed, list) else []
            return self._convert_to_entities(raw_entities, chunk, context.document_id)
        except Exception as e:
            logger.error("Entity extraction failed: %s", e)
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

    def _parse_llm_response(self, content: str) -> list:
        """
        Parse LLM JSON response for entity extraction. Delegates to shared util.

        Args:
            content: Raw LLM response text

        Returns:
            Parsed list of entity dicts, or empty list on failure
        """
        parsed = parse_llm_json_response(content)
        return parsed if isinstance(parsed, list) else []

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
