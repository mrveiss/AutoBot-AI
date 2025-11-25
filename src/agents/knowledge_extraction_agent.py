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

from src.llm_interface import LLMType, get_llm_interface
from src.models.atomic_fact import (
    AtomicFact,
    FactExtractionResult,
    FactType,
    TemporalType,
)
from src.unified_config_manager import config_manager
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("knowledge_extraction")


class KnowledgeExtractionAgent:
    """
    Advanced agent for extracting atomic facts from textual content.

    This agent analyzes text to identify discrete, verifiable facts and
    classifies them by type and temporal characteristics. It supports the RAG
    optimization pipeline by creating structured, time-aware knowledge
    representations.
    """

    def __init__(self, llm_interface=None):
        """
        Initialize the knowledge extraction agent.

        Args:
            llm_interface: LLM interface for fact extraction (optional)
        """
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

        logger.info("Knowledge Extraction Agent initialized")

    def _load_temporal_keywords(self) -> Dict[str, List[str]]:
        """Load temporal keywords for classification."""
        return {
            "dynamic_indicators": [
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
            ],
            "static_indicators": [
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
            ],
            "future_indicators": [
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
            ],
            "past_indicators": [
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
            ],
        }

    def _build_extraction_prompt(
        self, content: str, context: Optional[str] = None
    ) -> str:
        """
        Build the LLM prompt for fact extraction.

        Args:
            content: Text content to analyze
            context: Optional context information

        Returns:
            Formatted prompt for LLM
        """
        context_info = f"\n\nContext: {context}" if context else ""

        return f"""
Analyze the following text and extract atomic facts. Each fact should be a
single, verifiable statement that can be independently confirmed or
contradicted.

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
{{
  "facts": [
    {{
      "subject": "AutoBot",
      "predicate": "is",
      "object": "an AI automation platform",
      "fact_type": "FACT",
      "temporal_type": "STATIC",
      "confidence": 0.9,
      "entities": ["AutoBot", "AI automation platform"],
      "context": "Definition of AutoBot system",
      "reasoning": "Clear definitional statement"
    }}
  ]
}}

Guidelines:
- Extract only clear, discrete facts
- Avoid vague or ambiguous statements
- Include temporal indicators in your analysis
- Consider the factual vs. opinion nature of statements
- Aim for {self.max_facts_per_chunk} most important facts maximum
- Ensure confidence reflects certainty level

Respond only with valid JSON.
"""

    def _classify_temporal_type(
        self, fact_text: str, context: str = ""
    ) -> TemporalType:
        """
        Classify the temporal type of a fact based on linguistic indicators.

        Args:
            fact_text: The fact text to analyze
            context: Additional context for analysis

        Returns:
            TemporalType classification
        """
        text_lower = f"{fact_text} {context}".lower()

        # Count indicators for each type
        dynamic_count = sum(
            1
            for keyword in self.temporal_keywords["dynamic_indicators"]
            if keyword in text_lower
        ),
        static_count = sum(
            1
            for keyword in self.temporal_keywords["static_indicators"]
            if keyword in text_lower
        ),
        future_count = sum(
            1
            for keyword in self.temporal_keywords["future_indicators"]
            if keyword in text_lower
        ),
        past_count = sum(
            1
            for keyword in self.temporal_keywords["past_indicators"]
            if keyword in text_lower
        )

        # Specific date/time patterns
        date_patterns = [
            r"\b\d{4}\b",  # Years
            r"\b(january|february|march|april|may|june|july|august|september"
            r"|october|november|december)\b",
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # Dates
            r"\b(version|v)\s*\d+\b",  # Versions
        ]

        has_temporal_bound = any(
            re.search(pattern, text_lower) for pattern in date_patterns
        )

        # Classification logic
        if has_temporal_bound or future_count > 0 or past_count > 0:
            return TemporalType.TEMPORAL_BOUND
        elif dynamic_count > static_count:
            return TemporalType.DYNAMIC
        elif static_count > 0:
            return TemporalType.STATIC
        else:
            return TemporalType.ATEMPORAL

    def _extract_entities(self, fact_text: str) -> List[str]:
        """
        Extract entities from fact text using simple pattern matching.

        Args:
            fact_text: Text to extract entities from

        Returns:
            List of identified entities
        """
        if not self.enable_entity_extraction:
            return []

        entities = []

        # Capitalized words (potential proper nouns)
        capitalized_pattern = r"\b[A-Z][a-zA-Z0-9_]*\b"
        capitalized_entities = re.findall(capitalized_pattern, fact_text)
        entities.extend(capitalized_entities)

        # Technical terms and identifiers
        technical_patterns = [
            r"\b\w+\.\w+\b",  # Module.function or similar
            r"\b[a-zA-Z0-9_]+_[a-zA-Z0-9_]+\b",  # snake_case identifiers
            r"\b[A-Z]+\b",  # Acronyms
            r"\bv?\d+\.\d+(?:\.\d+)?\b",  # Version numbers
        ]

        for pattern in technical_patterns:
            matches = re.findall(pattern, fact_text)
            entities.extend(matches)

        # Remove duplicates and common words
        common_words = {
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
        entities = list(
            set(
                entity
                for entity in entities
                if entity.lower() not in common_words and len(entity) > 1
            )
        )

        return entities[:10]  # Limit to 10 entities max

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
            logger.debug(f"Missing required fields in fact: {fact_data}")
            return False

        # Check confidence range
        confidence = fact_data.get("confidence", 0)
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            logger.debug(f"Invalid confidence value: {confidence}")
            return False

        # Check non-empty strings
        text_fields = ["subject", "predicate", "object"]
        if any(
            not isinstance(fact_data.get(field), str)
            or not fact_data.get(field).strip()
            for field in text_fields
        ):
            logger.debug("Empty text fields in fact")
            return False

        # Check valid enum values
        try:
            FactType(fact_data["fact_type"])
            TemporalType(fact_data["temporal_type"])
        except ValueError as e:
            logger.debug(f"Invalid enum value in fact: {e}")
            return False

        return True

    async def extract_facts_from_text(
        self,
        content: str,
        source: str,
        context: Optional[str] = None,
        chunk_id: Optional[str] = None,
    ) -> FactExtractionResult:
        """
        Extract atomic facts from text content.

        Args:
            content: Text content to analyze
            source: Source identifier for the content
            context: Optional context information
            chunk_id: Optional chunk identifier

        Returns:
            FactExtractionResult with extracted facts
        """
        start_time = time.time()

        try:
            logger.info(f"Extracting facts from {len(content)} character content")

            # Build extraction prompt
            prompt = self._build_extraction_prompt(content, context)

            # Get LLM response
            response = await self.llm_interface.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                llm_type=LLMType.EXTRACTION,
                structured_output=True,
            )

            if not response or response.error:
                error_msg = response.error if response else "No response"
                logger.warning(f"No response from LLM for fact extraction: {error_msg}")
                return FactExtractionResult(
                    facts=[],
                    extraction_metadata={
                        "error": response.error if response else "No LLM response",
                        "content_length": len(content),
                    },
                )

            # Parse LLM response
            response_content = response.content

            try:
                facts_data = json.loads(response_content)
                if "facts" not in facts_data:
                    logger.warning("LLM response missing 'facts' field")
                    return FactExtractionResult(facts=[])

                raw_facts = facts_data["facts"]
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                logger.debug(f"Raw response: {response_content[:500]}...")
                return FactExtractionResult(
                    facts=[],
                    extraction_metadata={
                        "error": "JSON parse error",
                        "raw_response": response_content[:200],
                    },
                )

            # Convert to AtomicFact objects
            extracted_facts = []
            validation_errors = 0

            for fact_data in raw_facts:
                try:
                    if not self._validate_fact(fact_data):
                        validation_errors += 1
                        continue

                    # Enhance temporal classification if not confident from LLM
                    if fact_data.get("confidence", 0) < 0.8:
                        fact_text = (
                            f"{fact_data['subject']} {fact_data['predicate']} "
                            f"{fact_data['object']}"
                        ),
                        enhanced_temporal = self._classify_temporal_type(
                            fact_text, content
                        )
                        fact_data["temporal_type"] = enhanced_temporal.value

                    # Extract additional entities if not provided or insufficient
                    entities = fact_data.get("entities", [])
                    if not entities or len(entities) < 2:
                        fact_text = (
                            f"{fact_data['subject']} {fact_data['predicate']} "
                            f"{fact_data['object']}"
                        ),
                        additional_entities = self._extract_entities(fact_text)
                        fact_data["entities"] = list(
                            set(entities + additional_entities)
                        )

                    # Create AtomicFact object
                    atomic_fact = AtomicFact(
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
                        original_text=(
                            content if len(content) < 500 else content[:500] + "..."
                        ),
                        chunk_id=chunk_id,
                        metadata={
                            "llm_reasoning": fact_data.get("reasoning", ""),
                            "extraction_timestamp": datetime.now().isoformat(),
                            "content_length": len(content),
                        },
                    )

                    # Apply confidence threshold
                    if atomic_fact.confidence >= self.confidence_threshold:
                        extracted_facts.append(atomic_fact)
                    else:
                        logger.debug(
                            f"Fact below confidence threshold: "
                            f"{atomic_fact.confidence}"
                        )

                except Exception as e:
                    logger.error(f"Error creating AtomicFact: {e}")
                    logger.debug(f"Problematic fact data: {fact_data}")
                    validation_errors += 1
                    continue

            processing_time = time.time() - start_time

            logger.info(
                f"Extracted {len(extracted_facts)} facts in "
                f"{processing_time:.2f}s ({validation_errors} validation errors)"
            )

            # Create result with metadata
            result = FactExtractionResult(
                facts=extracted_facts,
                processing_time=processing_time,
                extraction_metadata={
                    "source": source,
                    "content_length": len(content),
                    "raw_facts_count": len(raw_facts),
                    "validation_errors": validation_errors,
                    "confidence_threshold": self.confidence_threshold,
                    "extraction_method": "llm_guided_extraction",
                    "chunk_id": chunk_id,
                },
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error in fact extraction: {e}")

            return FactExtractionResult(
                facts=[],
                processing_time=processing_time,
                extraction_metadata={
                    "error": str(e),
                    "source": source,
                    "content_length": len(content),
                },
            )

    async def extract_facts_from_chunks(
        self, chunks: List[Dict[str, Any]], source: str
    ) -> FactExtractionResult:
        """
        Extract facts from multiple chunks in parallel.

        Args:
            chunks: List of chunk dictionaries with 'text' and metadata
            source: Source identifier

        Returns:
            Combined FactExtractionResult
        """
        logger.info(f"Processing {len(chunks)} chunks for fact extraction")

        # Process chunks in parallel with limited concurrency
        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent extractions

        async def process_chunk(chunk: Dict[str, Any]) -> FactExtractionResult:
            async with semaphore:
                chunk_text = chunk.get("text", "")
                chunk_context = str(chunk.get("metadata", {}))
                chunk_id = chunk.get("id", chunk.get("chunk_id"))

                return await self.extract_facts_from_text(
                    content=chunk_text,
                    source=source,
                    context=chunk_context,
                    chunk_id=chunk_id,
                )

        # Execute parallel processing
        start_time = time.time()
        chunk_results = await asyncio.gather(
            *[process_chunk(chunk) for chunk in chunks], return_exceptions=True
        )

        # Combine results
        all_facts = []
        total_errors = 0
        successful_extractions = 0

        for result in chunk_results:
            if isinstance(result, Exception):
                logger.error(f"Chunk processing failed: {result}")
                total_errors += 1
                continue

            if isinstance(result, FactExtractionResult):
                all_facts.extend(result.facts)
                metadata = result.extraction_metadata
                total_errors += metadata.get("validation_errors", 0)
                successful_extractions += 1

        processing_time = time.time() - start_time

        logger.info(
            f"Extracted {len(all_facts)} total facts from "
            f"{successful_extractions} chunks in {processing_time:.2f}s"
        )

        # Create combined result
        combined_result = FactExtractionResult(
            facts=all_facts,
            processing_time=processing_time,
            extraction_metadata={
                "source": source,
                "total_chunks": len(chunks),
                "successful_chunks": successful_extractions,
                "failed_chunks": len(chunks) - successful_extractions,
                "total_validation_errors": total_errors,
                "extraction_method": "parallel_chunk_processing",
            },
        )

        return combined_result

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

        logger.debug(f"Filtered {len(facts)} facts to {len(filtered_facts)} facts")
        return filtered_facts
