# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fact Extraction Service for AutoBot RAG Optimization

Provides high-level interface for atomic fact extraction and management.
Integrates with the knowledge base to store and retrieve temporal facts.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.knowledge_extraction_agent import KnowledgeExtractionAgent
from src.models.atomic_fact import (
    AtomicFact,
    FactExtractionResult,
    FactType,
    TemporalType,
)
from src.config import config_manager
from src.utils.entity_resolver import entity_resolver
from src.utils.logging_manager import get_llm_logger
from src.utils.redis_client import get_redis_client

logger = get_llm_logger("fact_extraction_service")


class FactExtractionService:
    """
    Service for managing atomic fact extraction and storage.

    This service provides a high-level interface for extracting facts from content,
    storing them in the knowledge base, and managing temporal relationships.
    """

    def __init__(self, knowledge_base=None):
        """
        Initialize the fact extraction service.

        Args:
            knowledge_base: KnowledgeBase instance for storage
        """
        self.knowledge_base = knowledge_base
        self.extraction_agent = KnowledgeExtractionAgent()
        self.redis_client = get_redis_client(async_client=True)

        # Configuration
        self.fact_storage_prefix = "atomic_fact:"
        self.fact_index_key = "atomic_facts_index"
        self.extraction_history_key = "fact_extraction_history"
        self.batch_size = config_manager.get("fact_extraction.batch_size", 50)
        self.enable_deduplication = config_manager.get(
            "fact_extraction.enable_deduplication", True
        )
        self.enable_entity_resolution = config_manager.get(
            "fact_extraction.enable_entity_resolution", True
        )
        self.enable_temporal_invalidation = config_manager.get(
            "fact_extraction.enable_temporal_invalidation", True
        )

        logger.info("Fact Extraction Service initialized")

    async def _apply_fact_processing(self, extraction_result) -> None:
        """Apply deduplication and entity resolution to extracted facts (Issue #398: extracted).

        Args:
            extraction_result: Result object with facts list (modified in place)
        """
        if self.enable_deduplication:
            original_count = len(extraction_result.facts)
            extraction_result.facts = await self._deduplicate_facts(extraction_result.facts)
            logger.info("Deduplication: %s -> %s facts", original_count, len(extraction_result.facts))

        if self.enable_entity_resolution:
            extraction_result.facts = await entity_resolver.resolve_facts_entities(extraction_result.facts)
            logger.info("Entity resolution: %s facts processed", len(extraction_result.facts))

    def _build_extraction_result(self, extraction_result, storage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Build the final extraction result dictionary (Issue #398: extracted).

        Args:
            extraction_result: Extraction result with facts and metadata
            storage_results: Results from storing facts

        Returns:
            Complete result dictionary
        """
        return {
            "status": "success",
            "facts_extracted": len(extraction_result.facts),
            "facts_stored": storage_results["stored_count"],
            "storage_errors": storage_results["error_count"],
            "processing_time": extraction_result.processing_time,
            "average_confidence": extraction_result.average_confidence,
            "fact_type_distribution": extraction_result.fact_type_distribution,
            "temporal_type_distribution": extraction_result.temporal_type_distribution,
            "extraction_metadata": extraction_result.extraction_metadata,
        }

    async def extract_and_store_facts(
        self, content: str, source: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract facts from content and store them (Issue #398: refactored).

        Args:
            content: Text content to process
            source: Source identifier
            metadata: Additional metadata

        Returns:
            Dictionary with extraction results and storage information
        """
        try:
            logger.info("Starting fact extraction for source: %s", source)

            extraction_result = await self.extraction_agent.extract_facts_from_text(
                content=content, source=source, context=str(metadata) if metadata else None
            )

            if not extraction_result.facts:
                logger.warning("No facts extracted from source: %s", source)
                return {
                    "status": "success", "facts_extracted": 0, "facts_stored": 0,
                    "processing_time": extraction_result.processing_time,
                    "message": "No facts found in content",
                }

            # Apply processing steps (Issue #398: uses helper)
            await self._apply_fact_processing(extraction_result)

            # Store facts and handle post-processing
            storage_results = await self._store_facts(extraction_result.facts, metadata)

            if self.enable_temporal_invalidation and extraction_result.facts:
                await self._handle_temporal_invalidation(extraction_result.facts)

            await self._record_extraction_history(source, extraction_result, storage_results)

            logger.info("Completed fact extraction: %s facts stored", len(extraction_result.facts))
            return self._build_extraction_result(extraction_result, storage_results)

        except Exception as e:
            logger.error("Error in fact extraction and storage: %s", e)
            return {"status": "error", "message": str(e), "facts_extracted": 0, "facts_stored": 0}

    def _build_extraction_success_response(
        self,
        extraction_result: Any,
        storage_results: Dict[str, Any],
        chunks_count: int,
    ) -> Dict[str, Any]:
        """
        Build success response for fact extraction.

        Issue #665: Extracted from extract_facts_from_chunks to reduce function length.

        Args:
            extraction_result: Result from extraction agent
            storage_results: Results from storing facts
            chunks_count: Number of chunks processed

        Returns:
            Success response dictionary
        """
        return {
            "status": "success",
            "facts_extracted": len(extraction_result.facts),
            "facts_stored": storage_results["stored_count"],
            "storage_errors": storage_results["error_count"],
            "chunks_processed": chunks_count,
            "successful_chunks": extraction_result.extraction_metadata.get(
                "successful_chunks", 0
            ),
            "processing_time": extraction_result.processing_time,
            "average_confidence": extraction_result.average_confidence,
            "fact_distributions": {
                "by_type": extraction_result.fact_type_distribution,
                "by_temporal": extraction_result.temporal_type_distribution,
                "by_confidence": extraction_result.confidence_distribution,
            },
        }

    async def _process_extracted_facts(
        self,
        extraction_result: Any,
    ) -> Any:
        """
        Process extracted facts with deduplication and entity resolution.

        Issue #665: Extracted from extract_facts_from_chunks to reduce function length.

        Args:
            extraction_result: Result from extraction agent (modified in place)

        Returns:
            Processed extraction result
        """
        if self.enable_deduplication:
            extraction_result.facts = await self._deduplicate_facts(
                extraction_result.facts
            )

        if self.enable_entity_resolution:
            extraction_result.facts = await entity_resolver.resolve_facts_entities(
                extraction_result.facts
            )

        return extraction_result

    async def extract_facts_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extract facts from semantic chunks and store them.

        Issue #665: Refactored to use extracted helpers for processing
        and response building.

        Args:
            chunks: List of semantic chunks with text and metadata
            source: Source identifier
            metadata: Additional metadata

        Returns:
            Dictionary with extraction results
        """
        try:
            logger.info("Processing %s chunks for fact extraction", len(chunks))

            # Extract facts from chunks in parallel
            extraction_result = await self.extraction_agent.extract_facts_from_chunks(
                chunks=chunks, source=source
            )

            if not extraction_result.facts:
                return {
                    "status": "success",
                    "facts_extracted": 0,
                    "facts_stored": 0,
                    "chunks_processed": len(chunks),
                    "message": "No facts found in chunks",
                }

            # Process facts (Issue #665: uses helper)
            extraction_result = await self._process_extracted_facts(extraction_result)

            storage_results = await self._store_facts(extraction_result.facts, metadata)

            # Record extraction history
            await self._record_extraction_history(
                source, extraction_result, storage_results
            )

            logger.info("Processed %s chunks, extracted %s facts", len(chunks), len(extraction_result.facts))

            # Build response (Issue #665: uses helper)
            return self._build_extraction_success_response(
                extraction_result, storage_results, len(chunks)
            )

        except Exception as e:
            logger.error("Error processing chunks for fact extraction: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "facts_extracted": 0,
                "facts_stored": 0,
                "chunks_processed": len(chunks),
            }

    async def _deduplicate_facts(self, facts: List[AtomicFact]) -> List[AtomicFact]:
        """
        Remove duplicate facts based on semantic similarity.

        Args:
            facts: List of facts to deduplicate

        Returns:
            Deduplicated list of facts
        """
        if not facts or not self.enable_deduplication:
            return facts

        try:
            deduplicated = []
            seen_combinations = set()

            for fact in facts:
                # Create a normalized key for deduplication
                fact_key = (
                    fact.subject.lower().strip(),
                    fact.predicate.lower().strip(),
                    fact.object.lower().strip(),
                )

                if fact_key not in seen_combinations:
                    seen_combinations.add(fact_key)
                    deduplicated.append(fact)
                else:
                    logger.debug("Duplicate fact filtered: %s", fact)

            return deduplicated

        except Exception as e:
            logger.error("Error in fact deduplication: %s", e)
            return facts  # Return original list if deduplication fails

    def _prepare_fact_for_pipeline(
        self, pipe, fact: AtomicFact, metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """Prepare single fact for pipeline storage (Issue #315: extracted helper).

        Args:
            pipe: Redis pipeline
            fact: Fact to prepare
            metadata: Additional metadata

        Returns:
            True if successful, False if error
        """
        try:
            fact_key = f"{self.fact_storage_prefix}{fact.fact_id}"
            fact_data = fact.to_dict()

            # Add service metadata
            fact_data.update({
                "storage_timestamp": datetime.now().isoformat(),
                "service_metadata": metadata or {},
            })

            # Store fact data using model method (Issue #372 - reduces feature envy)
            pipe.hset(
                fact_key,
                mapping=fact.to_redis_mapping(json.dumps(fact_data)),
            )

            # Add to indices using model method (Issue #372 - reduces feature envy)
            pipe.sadd(self.fact_index_key, fact.fact_id)
            for index_key in fact.get_index_keys():
                pipe.sadd(index_key, fact.fact_id)
            return True
        except Exception as e:
            logger.error("Error preparing fact for storage: %s", e)
            return False

    async def _store_facts(
        self, facts: List[AtomicFact], metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store facts in Redis and knowledge base.

        Args:
            facts: List of facts to store
            metadata: Additional metadata

        Returns:
            Dictionary with storage results
        """
        stored_count = 0
        error_count = 0

        if not self.redis_client:
            logger.warning("Redis client not available, skipping fact storage")
            return {"stored_count": 0, "error_count": len(facts)}

        try:
            # Store facts in batches for better performance
            for i in range(0, len(facts), self.batch_size):
                batch = facts[i : i + self.batch_size]
                pipe = self.redis_client.pipeline()
                batch_errors = 0

                # Prepare facts using helper (Issue #315: reduced nesting)
                for fact in batch:
                    if not self._prepare_fact_for_pipeline(pipe, fact, metadata):
                        batch_errors += 1

                # Execute batch operation
                try:
                    await pipe.execute()
                    stored_count += len(batch) - batch_errors
                    error_count += batch_errors
                    logger.debug("Stored batch of %s facts", len(batch))
                except Exception as e:
                    logger.error("Error executing batch storage: %s", e)
                    error_count += len(batch)

            # Also store facts in the main knowledge base as structured content
            if self.knowledge_base and hasattr(self.knowledge_base, "store_fact"):
                await self._store_facts_in_kb(facts, metadata)

            logger.info("Fact storage complete: %s stored, %s errors", stored_count, error_count)

        except Exception as e:
            logger.error("Error in fact storage: %s", e)
            error_count = len(facts)

        return {"stored_count": stored_count, "error_count": error_count}

    async def _store_facts_in_kb(
        self, facts: List[AtomicFact], metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Store facts in the main knowledge base as structured content.

        Args:
            facts: List of facts to store
            metadata: Additional metadata
        """
        try:
            # Create a structured representation of facts
            facts_summary = {
                "type": "atomic_facts_collection",
                "total_facts": len(facts),
                "extraction_timestamp": datetime.now().isoformat(),
                "facts": [],
            }

            for fact in facts:
                facts_summary["facts"].append(
                    {
                        "id": fact.fact_id,
                        "statement": f"{fact.subject} {fact.predicate} {fact.object}",
                        "type": fact.fact_type.value,
                        "temporal": fact.temporal_type.value,
                        "confidence": fact.confidence,
                        "entities": fact.entities,
                    }
                )

            # Store as a knowledge base fact
            content = json.dumps(facts_summary, indent=2)
            kb_metadata = {
                "type": "atomic_facts",
                "content_type": "structured_facts",
                "facts_count": len(facts),
                **(metadata or {}),
            }

            await self.knowledge_base.store_fact(content, kb_metadata)
            logger.debug("Stored %s facts in knowledge base as structured content", len(facts))

        except Exception as e:
            logger.error("Error storing facts in knowledge base: %s", e)

    async def _record_extraction_history(
        self,
        source: str,
        extraction_result: FactExtractionResult,
        storage_results: Dict[str, Any],
    ):
        """
        Record extraction history for analytics and monitoring.

        Args:
            source: Source identifier
            extraction_result: Results from fact extraction
            storage_results: Results from fact storage
        """
        try:
            if not self.redis_client:
                return

            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "facts_extracted": len(extraction_result.facts),
                "facts_stored": storage_results["stored_count"],
                "storage_errors": storage_results["error_count"],
                "processing_time": extraction_result.processing_time,
                "average_confidence": extraction_result.average_confidence,
                "distributions": {
                    "fact_types": extraction_result.fact_type_distribution,
                    "temporal_types": extraction_result.temporal_type_distribution,
                    "confidence": extraction_result.confidence_distribution,
                },
                "extraction_metadata": extraction_result.extraction_metadata,
            }

            # Store in extraction history list (keep last 1000 entries)
            await self.redis_client.lpush(
                self.extraction_history_key, json.dumps(history_entry)
            )
            await self.redis_client.ltrim(self.extraction_history_key, 0, 999)

            logger.debug("Recorded extraction history for source: %s", source)

        except Exception as e:
            logger.error("Error recording extraction history: %s", e)

    def _build_criteria_candidate_keys(
        self,
        source: Optional[str],
        fact_type: Optional[FactType],
        temporal_type: Optional[TemporalType],
    ) -> List[str]:
        """
        Build Redis index keys for fact criteria filtering.

        Issue #281: Extracted helper to reduce complexity in get_facts_by_criteria.

        Args:
            source: Filter by source
            fact_type: Filter by fact type
            temporal_type: Filter by temporal type

        Returns:
            List of Redis index keys to query
        """
        candidate_keys = []
        if source:
            candidate_keys.append(f"facts_by_source:{source}")
        if fact_type:
            candidate_keys.append(f"facts_by_type:{fact_type.value}")
        if temporal_type:
            candidate_keys.append(f"facts_by_temporal:{temporal_type.value}")
        return candidate_keys

    async def _get_fact_ids_from_criteria(
        self,
        candidate_keys: List[str],
    ) -> set:
        """
        Retrieve fact IDs by intersecting criteria index keys.

        Issue #281: Extracted helper to reduce complexity in get_facts_by_criteria.

        Args:
            candidate_keys: Redis index keys to intersect

        Returns:
            Set of fact IDs matching all criteria
        """
        if candidate_keys:
            if len(candidate_keys) == 1:
                return await self.redis_client.smembers(candidate_keys[0])
            else:
                # Create temporary intersection key
                temp_key = f"temp_intersection:{uuid.uuid4()}"
                await self.redis_client.sinterstore(temp_key, *candidate_keys)
                fact_ids = await self.redis_client.smembers(temp_key)
                await self.redis_client.delete(temp_key)
                return fact_ids
        else:
            # Get all facts
            return await self.redis_client.smembers(self.fact_index_key)

    async def _batch_retrieve_facts(
        self, fact_ids_list: List[str]
    ) -> List[Optional[str]]:
        """
        Batch retrieve fact data from Redis.

        Issue #665: Extracted from get_facts_by_criteria to reduce function length.

        Args:
            fact_ids_list: List of fact IDs to retrieve

        Returns:
            List of fact data strings (or None for missing facts)
        """
        pipe = self.redis_client.pipeline()
        for fact_id in fact_ids_list:
            fact_key = f"{self.fact_storage_prefix}{fact_id}"
            pipe.hget(fact_key, "data")
        return await pipe.execute()

    def _filter_and_deserialize_fact(
        self,
        fact_id: str,
        fact_data: Optional[str],
        active_only: bool,
        min_confidence: Optional[float],
    ) -> Optional[AtomicFact]:
        """
        Deserialize and filter a single fact.

        Issue #665: Extracted from get_facts_by_criteria to reduce function length.

        Args:
            fact_id: Fact identifier
            fact_data: Serialized fact data
            active_only: Whether to filter inactive facts
            min_confidence: Minimum confidence threshold

        Returns:
            AtomicFact if passes filters, None otherwise
        """
        if not fact_data:
            return None

        try:
            fact_dict = json.loads(fact_data)
            fact = AtomicFact.from_dict(fact_dict)

            if active_only and not fact.is_active:
                return None
            if min_confidence and fact.confidence < min_confidence:
                return None

            return fact
        except Exception as e:
            logger.error("Error deserializing fact %s: %s", fact_id, e)
            return None

    async def get_facts_by_criteria(
        self,
        source: Optional[str] = None,
        fact_type: Optional[FactType] = None,
        temporal_type: Optional[TemporalType] = None,
        min_confidence: Optional[float] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> List[AtomicFact]:
        """
        Retrieve facts based on various criteria.

        Issue #665: Refactored to use extracted helper methods.

        Args:
            source: Filter by source
            fact_type: Filter by fact type
            temporal_type: Filter by temporal type
            min_confidence: Minimum confidence threshold
            active_only: Only return active facts
            limit: Maximum number of facts to return

        Returns:
            List of matching AtomicFact objects
        """
        try:
            if not self.redis_client:
                logger.warning("Redis client not available")
                return []

            candidate_keys = self._build_criteria_candidate_keys(
                source, fact_type, temporal_type
            )
            fact_ids = await self._get_fact_ids_from_criteria(candidate_keys)

            if not fact_ids:
                return []

            # Get more IDs to account for filtering
            fact_ids_list = list(fact_ids)[: limit * 2]

            # Issue #665: Use helper for batch retrieval
            fact_data_list = await self._batch_retrieve_facts(fact_ids_list)

            # Issue #665: Use helper for filtering
            facts = []
            for fact_id, fact_data in zip(fact_ids_list, fact_data_list):
                fact = self._filter_and_deserialize_fact(
                    fact_id, fact_data, active_only, min_confidence
                )
                if fact:
                    facts.append(fact)
                    if len(facts) >= limit:
                        break

            logger.debug("Retrieved %s facts matching criteria", len(facts))
            return facts

        except Exception as e:
            logger.error("Error retrieving facts: %s", e)
            return []

    def _aggregate_history_entry(
        self,
        history: Dict[str, Any],
        totals: Dict[str, Any],
    ) -> None:
        """Aggregate a single history entry into totals.

        Issue #665: Extracted from get_extraction_statistics to reduce function length.

        Args:
            history: Parsed history entry dictionary
            totals: Dictionary of running totals (modified in place)
        """
        totals["processing_time"] += history.get("processing_time", 0)
        totals["facts_extracted"] += history.get("facts_extracted", 0)
        totals["facts_stored"] += history.get("facts_stored", 0)

        # Aggregate fact type distribution
        fact_dist = history.get("distributions", {}).get("fact_types", {})
        for fact_type, count in fact_dist.items():
            totals["fact_types"][fact_type] = (
                totals["fact_types"].get(fact_type, 0) + count
            )

        # Aggregate temporal type distribution
        temporal_dist = history.get("distributions", {}).get("temporal_types", {})
        for temporal_type, count in temporal_dist.items():
            totals["temporal_types"][temporal_type] = (
                totals["temporal_types"].get(temporal_type, 0) + count
            )

    def _build_statistics_response(
        self,
        total_facts: int,
        totals: Dict[str, Any],
        extraction_count: int,
    ) -> Dict[str, Any]:
        """Build statistics response from aggregated totals.

        Issue #665: Extracted from get_extraction_statistics to reduce function length.

        Args:
            total_facts: Total facts in storage
            totals: Aggregated totals from history
            extraction_count: Number of extractions processed

        Returns:
            Statistics response dictionary
        """
        avg_processing_time = (
            totals["processing_time"] / extraction_count if extraction_count > 0 else 0
        )
        avg_facts_per_extraction = (
            totals["facts_extracted"] / extraction_count if extraction_count > 0 else 0
        )
        success_rate = (
            (totals["facts_stored"] / totals["facts_extracted"] * 100)
            if totals["facts_extracted"] > 0
            else 0
        )

        return {
            "total_facts_stored": total_facts,
            "recent_extractions": extraction_count,
            "total_facts_extracted": totals["facts_extracted"],
            "total_facts_stored_recent": totals["facts_stored"],
            "average_processing_time": round(avg_processing_time, 2),
            "average_facts_per_extraction": round(avg_facts_per_extraction, 1),
            "fact_type_distribution": totals["fact_types"],
            "temporal_type_distribution": totals["temporal_types"],
            "extraction_success_rate": round(success_rate, 1),
        }

    async def get_extraction_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about fact extraction operations.
        Issue #665: Refactored to use extracted helpers for aggregation and response building.

        Returns:
            Dictionary with extraction statistics
        """
        try:
            if not self.redis_client:
                return {"error": "Redis client not available"}

            # Get total facts count
            total_facts = await self.redis_client.scard(self.fact_index_key)

            # Get recent extraction history
            recent_history = await self.redis_client.lrange(
                self.extraction_history_key, 0, 99
            )

            # Initialize totals for aggregation
            totals = {
                "processing_time": 0,
                "facts_extracted": 0,
                "facts_stored": 0,
                "fact_types": {},
                "temporal_types": {},
            }

            # Aggregate history entries
            for history_json in recent_history:
                try:
                    history = json.loads(history_json)
                    self._aggregate_history_entry(history, totals)
                except json.JSONDecodeError:
                    continue

            return self._build_statistics_response(
                total_facts, totals, len(recent_history)
            )

        except Exception as e:
            logger.error("Error getting extraction statistics: %s", e)
            return {"error": str(e)}

    async def _handle_temporal_invalidation(self, new_facts: List[AtomicFact]):
        """
        Handle temporal invalidation for newly extracted facts.

        Args:
            new_facts: List of newly extracted facts to check for contradictions
        """
        try:
            # Import here to avoid circular imports
            from src.services.temporal_invalidation_service import (
                get_temporal_invalidation_service,
            )

            temporal_service = get_temporal_invalidation_service(self)

            # Check each new fact for contradictions
            for fact in new_facts:
                try:
                    result = await temporal_service.invalidate_contradictory_facts(fact)

                    if (
                        result["status"] == "success"
                        and result["facts_invalidated"] > 0
                    ):
                        logger.info("contradictory facts for new fact %s", fact.fact_id)

                except Exception as e:
                    logger.error("Error checking contradictions for fact %s: %s", fact.fact_id, e)
                    continue

        except Exception as e:
            logger.error("Error in temporal invalidation handling: %s", e)
