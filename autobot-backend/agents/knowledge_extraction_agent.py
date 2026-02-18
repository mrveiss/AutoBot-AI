# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Extraction Agent for AutoBot RAG Optimization

Implements intelligent extraction of atomic facts from text content with temporal
awareness. This agent uses LLM-powered analysis to identify discrete facts,
classify them, and assign temporal characteristics for dynamic knowledge
management.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.models.atomic_fact import (
    AtomicFact,
    FactExtractionResult,
    FactType,
    TemporalType,
)
from config import config_manager
from llm_interface import LLMType, get_llm_interface

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)

logger = get_llm_logger("knowledge_extraction")

# Issue #380: Module-level tuple for fact text field validation
_FACT_TEXT_FIELDS = ("subject", "predicate", "object")

# Issue #380: Module-level tuple for numeric types
_NUMERIC_TYPES = (int, float)


class KnowledgeExtractionAgent:
    """
    Advanced agent for extracting atomic facts from textual content.

    This agent analyzes text to identify discrete, verifiable facts and
    classifies them by type and temporal characteristics. It supports the RAG
    optimization pipeline by creating structured, time-aware knowledge
    representations.
    """

    # Agent identifier for SSOT config lookup
    AGENT_ID = "knowledge_extraction"

    def __init__(self, llm_interface=None):
        """
        Initialize the knowledge extraction agent with explicit LLM configuration.

        Args:
            llm_interface: LLM interface for fact extraction (optional)
        """
        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.llm_interface = llm_interface or get_llm_interface()

        # Configuration
        self.max_facts_per_chunk = config_manager.get(
            "knowledge_extraction.max_facts_per_chunk", 20
        )
        self.confidence_threshold = config_manager.get(
            "knowledge_extraction.confidence_threshold", 0.6
        )
        self.enable_entity_extraction = config_manager.get(
            "knowledge_extraction.enable_entity_extraction", True
        )
        self.temporal_keywords = self._load_temporal_keywords()

        logger.info(
            "Knowledge Extraction Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

    def _get_dynamic_indicators(self) -> List[str]:
        """Get keywords indicating dynamic/changing information."""
        return [
            "currently",
            "now",
            "today",
            "recently",
            "latest",
            "updated",
            "changed",
            "modified",
            "new",
            "current",
            "present",
            "as of",
            "this year",
            "this month",
            "upcoming",
            "planned",
            "scheduled",
        ]

    def _get_static_indicators(self) -> List[str]:
        """Get keywords indicating static/permanent information."""
        return [
            "always",
            "never",
            "permanent",
            "constant",
            "inherent",
            "fundamental",
            "basic",
            "definition",
            "concept",
            "principle",
            "established",
            "traditional",
            "historical",
            "original",
        ]

    def _get_future_indicators(self) -> List[str]:
        """Get keywords indicating future events."""
        return [
            "will",
            "shall",
            "going to",
            "planned",
            "expected",
            "projected",
            "forecast",
            "predicted",
            "anticipated",
            "scheduled",
            "upcoming",
            "future",
            "next",
            "soon",
            "eventually",
            "later",
        ]

    def _get_past_indicators(self) -> List[str]:
        """Get keywords indicating past events."""
        return [
            "was",
            "were",
            "had",
            "did",
            "used to",
            "previously",
            "formerly",
            "historically",
            "originally",
            "initially",
            "before",
            "earlier",
            "past",
            "old",
            "legacy",
            "deprecated",
        ]

    def _load_temporal_keywords(self) -> Dict[str, List[str]]:
        """Load temporal keywords for classification."""
        return {
            "dynamic_indicators": self._get_dynamic_indicators(),
            "static_indicators": self._get_static_indicators(),
            "future_indicators": self._get_future_indicators(),
            "past_indicators": self._get_past_indicators(),
        }

    def _get_fact_json_example(self) -> str:
        """Get JSON example for fact extraction prompt.

        Returns:
            Formatted JSON example string.

        Issue #620.
        """
        return """{
  "facts": [
    {
      "subject": "AutoBot",
      "predicate": "is",
      "object": "an AI automation platform",
      "fact_type": "FACT",
      "temporal_type": "STATIC",
      "confidence": 0.9,
      "entities": ["AutoBot", "AI automation platform"],
      "context": "Definition of AutoBot system",
      "reasoning": "Clear definitional statement"
    }
  ]
}"""

    def _get_extraction_guidelines(self) -> str:
        """Get guidelines for fact extraction prompt.

        Returns:
            Formatted guidelines string.

        Issue #620.
        """
        return f"""Guidelines:
- Extract only clear, discrete facts
- Avoid vague or ambiguous statements
- Include temporal indicators in your analysis
- Consider the factual vs. opinion nature of statements
- Aim for {self.max_facts_per_chunk} most important facts maximum
- Ensure confidence reflects certainty level

Respond only with valid JSON."""

    def _build_extraction_prompt(
        self, content: str, context: Optional[str] = None
    ) -> str:
        """Build the LLM prompt for fact extraction.

        Args:
            content: Text content to analyze
            context: Optional context information

        Returns:
            Formatted prompt for LLM
        """
        context_info = f"\n\nContext: {context}" if context else ""

        return f"""Analyze the following text and extract atomic facts. Each fact should be a
single, verifiable statement that can be independently confirmed or contradicted.

Text to analyze:
{content}{context_info}

For each fact, provide:
1. Subject: The main entity or concept
2. Predicate: The relationship or property
3. Object: The value, description, or target entity
4. Fact Type: FACT (objective), OPINION (subjective), PREDICTION (future),
   INSTRUCTION (procedural), or DEFINITION (explanatory)
5. Temporal Type: STATIC (unchanging), DYNAMIC (can change), ATEMPORAL
   (not time-bound), or TEMPORAL_BOUND (specific time period)
6. Confidence: 0.0-1.0 based on how certain the fact is
7. Entities: All entities mentioned in the fact
8. Context: Brief surrounding context for the fact

Return the results as a JSON array of facts. Example format:
{self._get_fact_json_example()}

{self._get_extraction_guidelines()}"""

    def _count_keyword_matches(self, text_lower: str, keyword_type: str) -> int:
        """Count how many keywords of a given type appear in text."""
        return sum(1 for kw in self.temporal_keywords[keyword_type] if kw in text_lower)

    def _has_temporal_bound_pattern(self, text_lower: str) -> bool:
        """Check if text contains date/time/version patterns."""
        date_patterns = [
            r"\b\d{4}\b",  # Years
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # Dates
            r"\b(version|v)\s*\d+\b",  # Versions
        ]
        return any(re.search(pattern, text_lower) for pattern in date_patterns)

    def _classify_temporal_type(
        self, fact_text: str, context: str = ""
    ) -> TemporalType:
        """Classify the temporal type of a fact based on linguistic indicators."""
        text_lower = f"{fact_text} {context}".lower()

        dynamic_count = self._count_keyword_matches(text_lower, "dynamic_indicators")
        static_count = self._count_keyword_matches(text_lower, "static_indicators")
        future_count = self._count_keyword_matches(text_lower, "future_indicators")
        past_count = self._count_keyword_matches(text_lower, "past_indicators")

        if (
            self._has_temporal_bound_pattern(text_lower)
            or future_count > 0
            or past_count > 0
        ):
            return TemporalType.TEMPORAL_BOUND
        elif dynamic_count > static_count:
            return TemporalType.DYNAMIC
        elif static_count > 0:
            return TemporalType.STATIC
        else:
            return TemporalType.ATEMPORAL

    def _get_technical_patterns(self) -> List[str]:
        """Get regex patterns for technical entity extraction."""
        return [
            r"\b\w+\.\w+\b",  # Module.function or similar
            r"\b[a-zA-Z0-9_]+_[a-zA-Z0-9_]+\b",  # snake_case identifiers
            r"\b[A-Z]+\b",  # Acronyms
            r"\bv?\d+\.\d+(?:\.\d+)?\b",  # Version numbers
        ]

    def _get_common_words(self) -> set:
        """Get common words to filter from entities."""
        return {
            "the",
            "is",
            "are",
            "was",
            "were",
            "has",
            "have",
            "had",
            "will",
            "can",
            "could",
            "should",
        }

    def _extract_entities(self, fact_text: str) -> List[str]:
        """Extract entities from fact text using pattern matching."""
        if not self.enable_entity_extraction:
            return []

        entities = []

        # Capitalized words (potential proper nouns)
        entities.extend(re.findall(r"\b[A-Z][a-zA-Z0-9_]*\b", fact_text))

        # Technical terms and identifiers
        for pattern in self._get_technical_patterns():
            entities.extend(re.findall(pattern, fact_text))

        # Remove duplicates and common words
        common_words = self._get_common_words()
        unique_entities = list(
            set(e for e in entities if e.lower() not in common_words and len(e) > 1)
        )

        return unique_entities[:10]

    def _validate_fact(self, fact_data: Dict[str, Any]) -> bool:
        """
        Validate that a fact has required fields and reasonable values.

        Args:
            fact_data: Dictionary containing fact information

        Returns:
            True if fact is valid
        """
        required_fields = [
            "subject",
            "predicate",
            "object",
            "fact_type",
            "temporal_type",
            "confidence",
        ]

        # Check required fields
        if not all(field in fact_data for field in required_fields):
            logger.debug("Missing required fields in fact: %s", fact_data)
            return False

        # Check confidence range
        confidence = fact_data.get("confidence", 0)
        if not isinstance(confidence, _NUMERIC_TYPES) or not (
            0.0 <= confidence <= 1.0
        ):  # Issue #380
            logger.debug("Invalid confidence value: %s", confidence)
            return False

        # Check non-empty strings (Issue #380: use module-level constant)
        if any(
            not isinstance(fact_data.get(field), str)
            or not fact_data.get(field).strip()
            for field in _FACT_TEXT_FIELDS
        ):
            logger.debug("Empty text fields in fact")
            return False

        # Check valid enum values
        try:
            FactType(fact_data["fact_type"])
            TemporalType(fact_data["temporal_type"])
        except ValueError as e:
            logger.debug("Invalid enum value in fact: %s", e)
            return False

        return True

    async def _get_llm_facts_response(
        self, content: str, context: Optional[str]
    ) -> Optional[List[Dict[str, Any]]]:
        """Get raw facts from LLM response. Returns None on error."""
        prompt = self._build_extraction_prompt(content, context)
        response = await self.llm_interface.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            llm_type=LLMType.EXTRACTION,
            structured_output=True,
        )

        if not response or response.error:
            error_msg = response.error if response else "No response"
            logger.warning("No response from LLM for fact extraction: %s", error_msg)
            return None

        try:
            facts_data = json.loads(response.content)
            if "facts" not in facts_data:
                logger.warning("LLM response missing 'facts' field")
                return None
            return facts_data["facts"]
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON: %s", e)
            return None

    def _enhance_fact_data(self, fact_data: Dict[str, Any], content: str) -> None:
        """Enhance fact with temporal classification and entity extraction."""
        fact_text = (
            f"{fact_data['subject']} {fact_data['predicate']} {fact_data['object']}"
        )

        # Enhance temporal classification if not confident
        if fact_data.get("confidence", 0) < 0.8:
            enhanced_temporal = self._classify_temporal_type(fact_text, content)
            fact_data["temporal_type"] = enhanced_temporal.value

        # Extract additional entities if needed
        entities = fact_data.get("entities", [])
        if not entities or len(entities) < 2:
            additional_entities = self._extract_entities(fact_text)
            fact_data["entities"] = list(set(entities + additional_entities))

    def _create_atomic_fact(
        self,
        fact_data: Dict[str, Any],
        source: str,
        content: str,
        context: Optional[str],
        chunk_id: Optional[str],
    ) -> AtomicFact:
        """Create AtomicFact object from fact data."""
        return AtomicFact(
            subject=fact_data["subject"],
            predicate=fact_data["predicate"],
            object=fact_data["object"],
            fact_type=FactType(fact_data["fact_type"]),
            temporal_type=TemporalType(fact_data["temporal_type"]),
            confidence=fact_data["confidence"],
            source=source,
            extraction_method="llm_guided_extraction",
            valid_from=datetime.now(),
            entities=fact_data.get("entities", []),
            context=fact_data.get("context", context),
            original_text=content if len(content) < 500 else content[:500] + "...",
            chunk_id=chunk_id,
            metadata={
                "llm_reasoning": fact_data.get("reasoning", ""),
                "extraction_timestamp": datetime.now().isoformat(),
                "content_length": len(content),
            },
        )

    def _convert_raw_facts(
        self,
        raw_facts: List[Dict[str, Any]],
        source: str,
        content: str,
        context: Optional[str],
        chunk_id: Optional[str],
    ) -> tuple:
        """Convert raw facts to AtomicFact objects. Returns (facts, error_count)."""
        extracted_facts = []
        validation_errors = 0

        for fact_data in raw_facts:
            try:
                if not self._validate_fact(fact_data):
                    validation_errors += 1
                    continue

                self._enhance_fact_data(fact_data, content)
                atomic_fact = self._create_atomic_fact(
                    fact_data, source, content, context, chunk_id
                )

                if atomic_fact.confidence >= self.confidence_threshold:
                    extracted_facts.append(atomic_fact)
                else:
                    logger.debug(
                        f"Fact below confidence threshold: {atomic_fact.confidence}"
                    )

            except Exception as e:
                logger.error("Error creating AtomicFact: %s", e)
                validation_errors += 1

        return extracted_facts, validation_errors

    def _build_extraction_success_result(
        self,
        extracted_facts: List[AtomicFact],
        raw_facts_count: int,
        validation_errors: int,
        source: str,
        content_length: int,
        chunk_id: Optional[str],
        processing_time: float,
    ) -> FactExtractionResult:
        """
        Build a successful FactExtractionResult with metadata.

        Issue #620.
        """
        return FactExtractionResult(
            facts=extracted_facts,
            processing_time=processing_time,
            extraction_metadata={
                "source": source,
                "content_length": content_length,
                "raw_facts_count": raw_facts_count,
                "validation_errors": validation_errors,
                "confidence_threshold": self.confidence_threshold,
                "extraction_method": "llm_guided_extraction",
                "chunk_id": chunk_id,
            },
        )

    def _build_extraction_error_result(
        self,
        error: str,
        source: str,
        content_length: int,
        processing_time: float,
    ) -> FactExtractionResult:
        """
        Build an error FactExtractionResult with error details.

        Issue #620.
        """
        return FactExtractionResult(
            facts=[],
            processing_time=processing_time,
            extraction_metadata={
                "error": error,
                "source": source,
                "content_length": content_length,
            },
        )

    async def extract_facts_from_text(
        self,
        content: str,
        source: str,
        context: Optional[str] = None,
        chunk_id: Optional[str] = None,
    ) -> FactExtractionResult:
        """Extract atomic facts from text content."""
        start_time = time.time()

        try:
            logger.info("Extracting facts from %s character content", len(content))

            raw_facts = await self._get_llm_facts_response(content, context)
            if raw_facts is None:
                return FactExtractionResult(
                    facts=[],
                    extraction_metadata={
                        "error": "LLM extraction failed",
                        "content_length": len(content),
                    },
                )

            extracted_facts, validation_errors = self._convert_raw_facts(
                raw_facts, source, content, context, chunk_id
            )

            processing_time = time.time() - start_time
            logger.info(
                f"Extracted {len(extracted_facts)} facts in "
                f"{processing_time:.2f}s ({validation_errors} validation errors)"
            )

            return self._build_extraction_success_result(
                extracted_facts,
                len(raw_facts),
                validation_errors,
                source,
                len(content),
                chunk_id,
                processing_time,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error("Error in fact extraction: %s", e)
            return self._build_extraction_error_result(
                str(e), source, len(content), processing_time
            )

    def _aggregate_chunk_results(self, chunk_results: List[Any]) -> tuple:
        """Aggregate results from parallel chunk processing. Returns (facts, errors, success_count)."""
        all_facts = []
        total_errors = 0
        successful_extractions = 0

        for result in chunk_results:
            if isinstance(result, Exception):
                logger.error("Chunk processing failed: %s", result)
                total_errors += 1
                continue

            if isinstance(result, FactExtractionResult):
                all_facts.extend(result.facts)
                total_errors += result.extraction_metadata.get("validation_errors", 0)
                successful_extractions += 1

        return all_facts, total_errors, successful_extractions

    async def extract_facts_from_chunks(
        self, chunks: List[Dict[str, Any]], source: str
    ) -> FactExtractionResult:
        """Extract facts from multiple chunks in parallel."""
        logger.info("Processing %s chunks for fact extraction", len(chunks))

        semaphore = asyncio.Semaphore(3)

        async def process_chunk(chunk: Dict[str, Any]) -> FactExtractionResult:
            """Process a single chunk and extract facts with concurrency limiting."""
            async with semaphore:
                return await self.extract_facts_from_text(
                    content=chunk.get("text", ""),
                    source=source,
                    context=str(chunk.get("metadata", {})),
                    chunk_id=chunk.get("id", chunk.get("chunk_id")),
                )

        start_time = time.time()
        chunk_results = await asyncio.gather(
            *[process_chunk(chunk) for chunk in chunks], return_exceptions=True
        )

        all_facts, total_errors, successful = self._aggregate_chunk_results(
            chunk_results
        )
        processing_time = time.time() - start_time

        logger.info(
            f"Extracted {len(all_facts)} total facts from {successful} chunks in {processing_time:.2f}s"
        )

        return FactExtractionResult(
            facts=all_facts,
            processing_time=processing_time,
            extraction_metadata={
                "source": source,
                "total_chunks": len(chunks),
                "successful_chunks": successful,
                "failed_chunks": len(chunks) - successful,
                "total_validation_errors": total_errors,
                "extraction_method": "parallel_chunk_processing",
            },
        )

    def filter_facts(
        self,
        facts: List[AtomicFact],
        fact_types: Optional[List[FactType]] = None,
        temporal_types: Optional[List[TemporalType]] = None,
        min_confidence: Optional[float] = None,
        active_only: bool = True,
    ) -> List[AtomicFact]:
        """
        Filter facts based on various criteria.

        Args:
            facts: List of facts to filter
            fact_types: Filter by fact types
            temporal_types: Filter by temporal types
            min_confidence: Minimum confidence threshold
            active_only: Only return active facts

        Returns:
            Filtered list of facts
        """
        filtered_facts = facts

        if active_only:
            filtered_facts = [f for f in filtered_facts if f.is_active]

        if fact_types:
            filtered_facts = [f for f in filtered_facts if f.fact_type in fact_types]

        if temporal_types:
            filtered_facts = [
                f for f in filtered_facts if f.temporal_type in temporal_types
            ]

        if min_confidence is not None:
            filtered_facts = [
                f for f in filtered_facts if f.confidence >= min_confidence
            ]

        logger.debug("Filtered %s facts to %s facts", len(facts), len(filtered_facts))
        return filtered_facts
