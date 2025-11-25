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
from src.unified_config_manager import config_manager
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

    async def extract_and_store_facts(
        self, content: str, source: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract facts from content and store them in the knowledge base.

        Args:
            content: Text content to process
            source: Source identifier
            metadata: Additional metadata

        Returns:
            Dictionary with extraction results and storage information
        """
        try:
            logger.info(f"Starting fact extraction for source: {source}")

            # Extract facts using the extraction agent
            extraction_result = await self.extraction_agent.extract_facts_from_text(
                content=content,
                source=source,
                context=str(metadata) if metadata else None,
            )

            if not extraction_result.facts:
                logger.warning(f"No facts extracted from source: {source}")
                return {
                    "status": "success",
                    "facts_extracted": 0,
                    "facts_stored": 0,
                    "processing_time": extraction_result.processing_time,
                    "message": "No facts found in content",
                }

            # Deduplicate facts if enabled
            if self.enable_deduplication:
                deduplicated_facts = await self._deduplicate_facts(
                    extraction_result.facts
                )
                logger.info(
                    f"Deduplication: {len(extraction_result.facts)} -> "
                    f"{len(deduplicated_facts)} facts"
                )
                extraction_result.facts = deduplicated_facts

            # Resolve entities if enabled
            if self.enable_entity_resolution:
                resolved_facts = await entity_resolver.resolve_facts_entities(
                    extraction_result.facts
                )
                logger.info(
                    f"Entity resolution: {len(extraction_result.facts)} "
                    f"facts processed"
                )
                extraction_result.facts = resolved_facts

            # Store facts in Redis and knowledge base
            storage_results = await self._store_facts(extraction_result.facts, metadata)

            # Check for contradictions and invalidate conflicting facts
            if self.enable_temporal_invalidation and extraction_result.facts:
                await self._handle_temporal_invalidation(extraction_result.facts)

            # Update extraction history
            await self._record_extraction_history(
                source, extraction_result, storage_results
            )

            logger.info(
                f"Completed fact extraction: {len(extraction_result.facts)} "
                f"facts stored"
            )

            return {
                "status": "success",
                "facts_extracted": len(extraction_result.facts),
                "facts_stored": storage_results["stored_count"],
                "storage_errors": storage_results["error_count"],
                "processing_time": extraction_result.processing_time,
                "average_confidence": extraction_result.average_confidence,
                "fact_type_distribution": extraction_result.fact_type_distribution,
                "temporal_type_distribution": (
                    extraction_result.temporal_type_distribution
                ),
                "extraction_metadata": extraction_result.extraction_metadata,
            }

        except Exception as e:
            logger.error(f"Error in fact extraction and storage: {e}")
            return {
                "status": "error",
                "message": str(e),
                "facts_extracted": 0,
                "facts_stored": 0,
            }

    async def extract_facts_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extract facts from semantic chunks and store them.

        Args:
            chunks: List of semantic chunks with text and metadata
            source: Source identifier
            metadata: Additional metadata

        Returns:
            Dictionary with extraction results
        """
        try:
            logger.info(f"Processing {len(chunks)} chunks for fact extraction")

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

            # Deduplicate and resolve entities
            if self.enable_deduplication:
                extraction_result.facts = await self._deduplicate_facts(
                    extraction_result.facts
                )

            if self.enable_entity_resolution:
                extraction_result.facts = await entity_resolver.resolve_facts_entities(
                    extraction_result.facts
                )

            storage_results = await self._store_facts(extraction_result.facts, metadata)

            # Record extraction history
            await self._record_extraction_history(
                source, extraction_result, storage_results
            )

            logger.info(
                f"Processed {len(chunks)} chunks, extracted "
                f"{len(extraction_result.facts)} facts"
            )

            return {
                "status": "success",
                "facts_extracted": len(extraction_result.facts),
                "facts_stored": storage_results["stored_count"],
                "storage_errors": storage_results["error_count"],
                "chunks_processed": len(chunks),
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

        except Exception as e:
            logger.error(f"Error processing chunks for fact extraction: {e}")
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
                    logger.debug(f"Duplicate fact filtered: {fact}")

            return deduplicated

        except Exception as e:
            logger.error(f"Error in fact deduplication: {e}")
            return facts  # Return original list if deduplication fails

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

                # Use Redis pipeline for batch operations
                pipe = self.redis_client.pipeline()

                for fact in batch:
                    try:
                        fact_key = f"{self.fact_storage_prefix}{fact.fact_id}"
                        fact_data = fact.to_dict()

                        # Add service metadata
                        fact_data.update(
                            {
                                "storage_timestamp": datetime.now().isoformat(),
                                "service_metadata": metadata or {},
                            }
                        )

                        # Store fact data
                        pipe.hset(
                            fact_key,
                            mapping={
                                "data": json.dumps(fact_data),
                                "subject": fact.subject,
                                "predicate": fact.predicate,
                                "object": fact.object,
                                "fact_type": fact.fact_type.value,
                                "temporal_type": fact.temporal_type.value,
                                "confidence": str(fact.confidence),
                                "source": fact.source,
                                "is_active": str(fact.is_active),
                                "valid_from": fact.valid_from.isoformat(),
                            },
                        )

                        # Add to facts index
                        pipe.sadd(self.fact_index_key, fact.fact_id)

                        # Add to source-specific index
                        source_index_key = f"facts_by_source:{fact.source}"
                        pipe.sadd(source_index_key, fact.fact_id)

                        # Add to type-specific indices
                        type_index_key = f"facts_by_type:{fact.fact_type.value}"
                        temporal_index_key = (
                            f"facts_by_temporal:{fact.temporal_type.value}"
                        )
                        pipe.sadd(type_index_key, fact.fact_id)
                        pipe.sadd(temporal_index_key, fact.fact_id)

                    except Exception as e:
                        logger.error(f"Error preparing fact for storage: {e}")
                        error_count += 1
                        continue

                # Execute batch operation
                try:
                    await pipe.execute()
                    stored_count += len(batch) - (
                        error_count - (stored_count // self.batch_size * error_count)
                    )
                    logger.debug(f"Stored batch of {len(batch)} facts")
                except Exception as e:
                    logger.error(f"Error executing batch storage: {e}")
                    error_count += len(batch)

            # Also store facts in the main knowledge base as structured content
            if self.knowledge_base and hasattr(self.knowledge_base, "store_fact"):
                await self._store_facts_in_kb(facts, metadata)

            logger.info(
                f"Fact storage complete: {stored_count} stored, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Error in fact storage: {e}")
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
            logger.debug(
                f"Stored {len(facts)} facts in knowledge base as structured content"
            )

        except Exception as e:
            logger.error(f"Error storing facts in knowledge base: {e}")

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

            logger.debug(f"Recorded extraction history for source: {source}")

        except Exception as e:
            logger.error(f"Error recording extraction history: {e}")

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

            # Determine which index to use
            candidate_keys = []

            if source:
                candidate_keys.append(f"facts_by_source:{source}")
            if fact_type:
                candidate_keys.append(f"facts_by_type:{fact_type.value}")
            if temporal_type:
                candidate_keys.append(f"facts_by_temporal:{temporal_type.value}")

            # Get fact IDs
            if candidate_keys:
                # Intersect all criteria
                if len(candidate_keys) == 1:
                    fact_ids = await self.redis_client.smembers(candidate_keys[0])
                else:
                    # Create temporary intersection key
                    temp_key = f"temp_intersection:{uuid.uuid4()}"
                    await self.redis_client.sinterstore(temp_key, *candidate_keys)
                    fact_ids = await self.redis_client.smembers(temp_key)
                    await self.redis_client.delete(temp_key)
            else:
                # Get all facts
                fact_ids = await self.redis_client.smembers(self.fact_index_key)

            if not fact_ids:
                return []

            # Retrieve and filter facts
            facts = []
            # Get more IDs to account for filtering
            fact_ids_list = list(fact_ids)[: limit * 2]

            # Batch retrieve facts
            pipe = self.redis_client.pipeline()
            for fact_id in fact_ids_list:
                fact_key = f"{self.fact_storage_prefix}{fact_id}"
                pipe.hget(fact_key, "data")

            fact_data_list = await pipe.execute()

            for fact_id, fact_data in zip(fact_ids_list, fact_data_list):
                if not fact_data:
                    continue

                try:
                    fact_dict = json.loads(fact_data)
                    fact = AtomicFact.from_dict(fact_dict)

                    # Apply additional filters
                    if active_only and not fact.is_active:
                        continue
                    if min_confidence and fact.confidence < min_confidence:
                        continue

                    facts.append(fact)

                    if len(facts) >= limit:
                        break

                except Exception as e:
                    logger.error(f"Error deserializing fact {fact_id}: {e}")
                    continue

            logger.debug(f"Retrieved {len(facts)} facts matching criteria")
            return facts

        except Exception as e:
            logger.error(f"Error retrieving facts: {e}")
            return []

    async def get_extraction_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about fact extraction operations.

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

            # Calculate statistics from history
            total_extractions = len(recent_history)
            total_processing_time = 0
            total_facts_extracted = 0
            total_facts_stored = 0

            fact_type_totals = {}
            temporal_type_totals = {}

            for history_json in recent_history:
                try:
                    history = json.loads(history_json)
                    total_processing_time += history.get("processing_time", 0)
                    total_facts_extracted += history.get("facts_extracted", 0)
                    total_facts_stored += history.get("facts_stored", 0)

                    # Aggregate distributions
                    fact_dist = history.get("distributions", {}).get("fact_types", {})
                    for fact_type, count in fact_dist.items():
                        fact_type_totals[fact_type] = (
                            fact_type_totals.get(fact_type, 0) + count
                        )

                    temporal_dist = history.get("distributions", {}).get(
                        "temporal_types", {}
                    )
                    for temporal_type, count in temporal_dist.items():
                        temporal_type_totals[temporal_type] = (
                            temporal_type_totals.get(temporal_type, 0) + count
                        )

                except json.JSONDecodeError:
                    continue

            avg_processing_time = (
                total_processing_time / total_extractions
                if total_extractions > 0
                else 0
            ),
            avg_facts_per_extraction = (
                total_facts_extracted / total_extractions
                if total_extractions > 0
                else 0
            )

            return {
                "total_facts_stored": total_facts,
                "recent_extractions": total_extractions,
                "total_facts_extracted": total_facts_extracted,
                "total_facts_stored_recent": total_facts_stored,
                "average_processing_time": round(avg_processing_time, 2),
                "average_facts_per_extraction": round(avg_facts_per_extraction, 1),
                "fact_type_distribution": fact_type_totals,
                "temporal_type_distribution": temporal_type_totals,
                "extraction_success_rate": round(
                    (
                        (total_facts_stored / total_facts_extracted * 100)
                        if total_facts_extracted > 0
                        else 0
                    ),
                    1,
                ),
            }

        except Exception as e:
            logger.error(f"Error getting extraction statistics: {e}")
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
                        logger.info(
                            f"Invalidated {result['facts_invalidated']} "
                            f"contradictory facts for new fact {fact.fact_id}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error checking contradictions for fact "
                        f"{fact.fact_id}: {e}"
                    )
                    continue

        except Exception as e:
            logger.error(f"Error in temporal invalidation handling: {e}")
