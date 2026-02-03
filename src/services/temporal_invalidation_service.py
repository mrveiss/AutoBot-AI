# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Temporal Knowledge Invalidation Service for AutoBot RAG Optimization

Manages the invalidation of time-sensitive knowledge and facts based on
temporal characteristics, ensuring knowledge base freshness and accuracy.
"""

import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.config import config_manager
from src.models.atomic_fact import AtomicFact, FactType, TemporalType
from src.services.fact_extraction_service import FactExtractionService
from src.utils.logging_manager import get_llm_logger
from src.utils.redis_client import get_redis_client

logger = get_llm_logger("temporal_invalidation")


class InvalidationReason(Enum):
    """Reasons for fact invalidation."""

    TEMPORAL_EXPIRY = "temporal_expiry"
    CONTRADICTION_DETECTED = "contradiction_detected"
    SOURCE_OUTDATED = "source_outdated"
    MANUAL_INVALIDATION = "manual_invalidation"
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    BATCH_CLEANUP = "batch_cleanup"


class InvalidationRule:
    """Rule for invalidating facts based on various criteria."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        temporal_types: List[TemporalType],
        max_age_days: Optional[int] = None,
        min_confidence: Optional[float] = None,
        source_patterns: Optional[List[str]] = None,
        fact_types: Optional[List[FactType]] = None,
        enabled: bool = True,
    ):
        """Initialize invalidation rule with criteria for matching facts."""
        self.rule_id = rule_id
        self.name = name
        self.temporal_types = temporal_types
        self.max_age_days = max_age_days
        self.min_confidence = min_confidence
        self.source_patterns = source_patterns or []
        self.fact_types = fact_types or []
        self.enabled = enabled
        self.created_at = datetime.now()

    def matches_fact(
        self, fact: AtomicFact
    ) -> Tuple[bool, Optional[InvalidationReason]]:
        """Check if this rule applies to the given fact."""
        if not self.enabled:
            return False, None

        # Check temporal type
        if fact.temporal_type not in self.temporal_types:
            return False, None

        # Check fact type if specified
        if self.fact_types and fact.fact_type not in self.fact_types:
            return False, None

        # Check age if specified
        if self.max_age_days is not None:
            fact_age = (datetime.now() - fact.valid_from).days
            if fact_age > self.max_age_days:
                return True, InvalidationReason.TEMPORAL_EXPIRY

        # Check confidence if specified
        if self.min_confidence is not None and fact.confidence < self.min_confidence:
            return True, InvalidationReason.CONFIDENCE_THRESHOLD

        # Check source patterns if specified
        if self.source_patterns:
            for pattern in self.source_patterns:
                if pattern.lower() in fact.source.lower():
                    return True, InvalidationReason.SOURCE_OUTDATED

        return False, None

    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "temporal_types": [t.value for t in self.temporal_types],
            "max_age_days": self.max_age_days,
            "min_confidence": self.min_confidence,
            "source_patterns": self.source_patterns,
            "fact_types": [t.value for t in self.fact_types],
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvalidationRule":
        """Create rule from dictionary."""
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            temporal_types=[TemporalType(t) for t in data["temporal_types"]],
            max_age_days=data.get("max_age_days"),
            min_confidence=data.get("min_confidence"),
            source_patterns=data.get("source_patterns", []),
            fact_types=[FactType(t) for t in data.get("fact_types", [])],
            enabled=data.get("enabled", True),
        )


class TemporalInvalidationService:
    """
    Service for managing temporal knowledge invalidation.

    This service automatically identifies and invalidates outdated or
    contradictory facts based on temporal characteristics and business rules.
    """

    def __init__(self, fact_extraction_service: Optional[FactExtractionService] = None):
        """
        Initialize the temporal invalidation service.

        Args:
            fact_extraction_service: Service for fact operations
        """
        self.fact_extraction_service = fact_extraction_service
        self.redis_client = get_redis_client(async_client=True)

        # Configuration
        self.invalidation_rules_key = "temporal_invalidation_rules"
        self.invalidation_history_key = "temporal_invalidation_history"
        self.invalidated_facts_key = "invalidated_facts_index"
        self.invalidation_schedule_key = "invalidation_schedule"

        # Default invalidation rules
        self.default_rules = self._create_default_rules()

        # Service settings
        self.batch_size = config_manager.get("temporal_invalidation.batch_size", 100)
        self.enable_auto_invalidation = config_manager.get(
            "temporal_invalidation.auto_invalidation", True
        )
        self.invalidation_interval_hours = config_manager.get(
            "temporal_invalidation.interval_hours", 24
        )

        logger.info("Temporal Invalidation Service initialized")

    def _create_default_rules(self) -> List[InvalidationRule]:
        """Create default invalidation rules."""
        return [
            # Dynamic facts older than 30 days
            InvalidationRule(
                rule_id="dynamic_facts_30d",
                name="Dynamic Facts - 30 Days",
                temporal_types=[TemporalType.DYNAMIC],
                max_age_days=30,
                enabled=True,
            ),
            # Predictions older than 90 days
            InvalidationRule(
                rule_id="predictions_90d",
                name="Predictions - 90 Days",
                temporal_types=[TemporalType.TEMPORAL_BOUND, TemporalType.DYNAMIC],
                fact_types=[FactType.PREDICTION],
                max_age_days=90,
                enabled=True,
            ),
            # Opinions older than 180 days
            InvalidationRule(
                rule_id="opinions_180d",
                name="Opinions - 180 Days",
                temporal_types=[TemporalType.ATEMPORAL, TemporalType.DYNAMIC],
                fact_types=[FactType.OPINION],
                max_age_days=180,
                enabled=True,
            ),
            # Low confidence facts older than 7 days
            InvalidationRule(
                rule_id="low_confidence_7d",
                name="Low Confidence Facts - 7 Days",
                temporal_types=[TemporalType.DYNAMIC, TemporalType.TEMPORAL_BOUND],
                max_age_days=7,
                min_confidence=0.6,
                enabled=True,
            ),
            # Test or temporary sources older than 1 day
            InvalidationRule(
                rule_id="test_sources_1d",
                name="Test Sources - 1 Day",
                temporal_types=[TemporalType.DYNAMIC, TemporalType.ATEMPORAL],
                source_patterns=["test", "temp", "demo"],
                max_age_days=1,
                enabled=True,
            ),
        ]

    async def initialize_rules(self) -> Dict[str, Any]:
        """Initialize invalidation rules in Redis."""
        try:
            if not self.redis_client:
                return {"status": "error", "message": "Redis client not available"}

            # Load existing rules
            existing_rules = await self._load_invalidation_rules()

            # Add default rules if they don't exist
            rules_added = 0
            for default_rule in self.default_rules:
                if default_rule.rule_id not in existing_rules:
                    existing_rules[default_rule.rule_id] = default_rule
                    rules_added += 1

            # Store updated rules
            await self._store_invalidation_rules(existing_rules)

            logger.info(
                "Invalidation rules initialized: %s total, %s added",
                len(existing_rules),
                rules_added,
            )

            return {
                "status": "success",
                "total_rules": len(existing_rules),
                "rules_added": rules_added,
                "message": "Invalidation rules initialized successfully",
            }

        except Exception as e:
            logger.error("Error initializing invalidation rules: %s", e)
            return {"status": "error", "message": str(e)}

    async def _load_invalidation_rules(self) -> Dict[str, InvalidationRule]:
        """Load invalidation rules from Redis."""
        try:
            if not self.redis_client:
                return {}

            rules_data = await self.redis_client.hgetall(self.invalidation_rules_key)
            rules = {}

            for rule_id, rule_json in rules_data.items():
                try:
                    rule_dict = json.loads(rule_json)
                    rule = InvalidationRule.from_dict(rule_dict)
                    rules[rule_id] = rule
                except Exception as e:
                    logger.error("Error loading rule %s: %s", rule_id, e)
                    continue

            return rules

        except Exception as e:
            logger.error("Error loading invalidation rules: %s", e)
            return {}

    async def _store_invalidation_rules(self, rules: Dict[str, InvalidationRule]):
        """Store invalidation rules to Redis."""
        try:
            if not self.redis_client or not rules:
                return

            # Store rules in batch
            pipe = self.redis_client.pipeline()

            for rule_id, rule in rules.items():
                rule_json = json.dumps(rule.to_dict())
                pipe.hset(self.invalidation_rules_key, rule_id, rule_json)

            await pipe.execute()
            logger.debug("Stored %s invalidation rules", len(rules))

        except Exception as e:
            logger.error("Error storing invalidation rules: %s", e)

    def _process_facts_against_rules(
        self,
        all_facts: List[AtomicFact],
        enabled_rules: Dict[str, "InvalidationRule"],
    ) -> Tuple[List[AtomicFact], Dict[str, Dict[str, Any]], Dict[str, int]]:
        """
        Process facts against enabled rules to find matches.

        Issue #281: Extracted helper for fact-rule matching.

        Args:
            all_facts: List of facts to process
            enabled_rules: Dictionary of enabled invalidation rules

        Returns:
            Tuple of (facts_to_invalidate, invalidation_reasons, rule_statistics)
        """
        facts_to_invalidate = []
        invalidation_reasons = {}
        rule_statistics = {rule_id: 0 for rule_id in enabled_rules.keys()}

        for i, fact in enumerate(all_facts):
            if i % 100 == 0:
                logger.debug("Processed %s/%s facts", i, len(all_facts))

            # Check each rule against this fact
            for rule_id, rule in enabled_rules.items():
                matches, reason = rule.matches_fact(fact)
                if matches:
                    facts_to_invalidate.append(fact)
                    invalidation_reasons[fact.fact_id] = {
                        "rule_id": rule_id,
                        "rule_name": rule.name,
                        "reason": reason.value,
                        "timestamp": datetime.now().isoformat(),
                    }
                    rule_statistics[rule_id] += 1
                    break  # Only apply first matching rule

        return facts_to_invalidate, invalidation_reasons, rule_statistics

    def _build_sweep_result(
        self,
        dry_run: bool,
        all_facts: List[AtomicFact],
        facts_to_invalidate: List[AtomicFact],
        invalidated_count: int,
        processing_time: float,
        enabled_rules: Dict[str, "InvalidationRule"],
        rule_statistics: Dict[str, int],
        source_filter: Optional[str],
        invalidation_reasons: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build the sweep result dictionary.

        Issue #281: Extracted helper for result building.

        Args:
            dry_run: Whether this was a dry run
            all_facts: All processed facts
            facts_to_invalidate: Facts identified for invalidation
            invalidated_count: Number actually invalidated
            processing_time: Time taken for processing
            enabled_rules: Rules used
            rule_statistics: Per-rule statistics
            source_filter: Source filter applied
            invalidation_reasons: Reasons for each fact invalidation

        Returns:
            Result dictionary
        """
        result = {
            "status": "success",
            "dry_run": dry_run,
            "facts_processed": len(all_facts),
            "facts_identified_for_invalidation": len(facts_to_invalidate),
            "facts_invalidated": invalidated_count,
            "processing_time": processing_time,
            "rules_used": len(enabled_rules),
            "rule_statistics": rule_statistics,
            "source_filter": source_filter,
        }

        if dry_run:
            result["sample_facts_to_invalidate"] = [
                {
                    "fact_id": fact.fact_id,
                    "statement": f"{fact.subject} {fact.predicate} {fact.object}",
                    "age_days": (datetime.now() - fact.valid_from).days,
                    "confidence": fact.confidence,
                    "source": fact.source,
                    "reason": invalidation_reasons.get(fact.fact_id, {}),
                }
                for fact in facts_to_invalidate[:10]  # Show first 10
            ]

        return result

    async def _load_rules_and_facts(
        self, source_filter: Optional[str]
    ) -> Tuple[Dict[str, InvalidationRule], List[AtomicFact]]:
        """
        Load invalidation rules and facts concurrently.

        Issue #665: Extracted helper for parallel data loading.

        Args:
            source_filter: Optional source filter for facts

        Returns:
            Tuple of (rules_dict, facts_list)
        """
        # Issue #619: Parallelize rules and facts loading
        # Both operations are independent - load concurrently for better performance
        rules, all_facts = await asyncio.gather(
            self._load_invalidation_rules(),
            self.fact_extraction_service.get_facts_by_criteria(
                source=source_filter,
                active_only=True,
                limit=10000,  # Large limit to get all facts
            ),
        )
        return rules, all_facts

    async def _execute_invalidation(
        self,
        dry_run: bool,
        facts_to_invalidate: List[AtomicFact],
        invalidation_reasons: Dict[str, Dict[str, Any]],
    ) -> int:
        """
        Execute invalidation of facts if not dry run.

        Issue #665: Extracted helper for invalidation execution.

        Args:
            dry_run: Whether this is a dry run
            facts_to_invalidate: Facts to invalidate
            invalidation_reasons: Invalidation reasons for each fact

        Returns:
            Number of facts invalidated
        """
        if dry_run or not facts_to_invalidate:
            return 0
        return await self._invalidate_facts(facts_to_invalidate, invalidation_reasons)

    async def _execute_sweep_core(
        self,
        start_time: datetime,
        source_filter: Optional[str],
        dry_run: bool,
        rules: Dict[str, InvalidationRule],
        all_facts: List[AtomicFact],
    ) -> Dict[str, Any]:
        """
        Execute core sweep logic after rules and facts are loaded. Issue #620.

        Args:
            start_time: When the sweep started
            source_filter: Optional source filter applied
            dry_run: Whether this is a dry run
            rules: Loaded invalidation rules
            all_facts: Facts to process

        Returns:
            Sweep result dictionary
        """
        enabled_rules = {k: v for k, v in rules.items() if v.enabled}
        logger.info("Using %s enabled invalidation rules", len(enabled_rules))

        if not all_facts:
            return self._build_no_facts_response()

        logger.info("Processing %s active facts", len(all_facts))

        # Process and invalidate facts (Issue #620: uses helper)
        sweep_data = await self._process_and_invalidate_facts(
            start_time, source_filter, dry_run, enabled_rules, all_facts
        )

        logger.info(
            "Invalidation sweep completed: %s/%s facts invalidated",
            sweep_data["invalidated_count"],
            len(sweep_data["facts_to_invalidate"]),
        )

        return sweep_data["result"]

    async def _process_and_invalidate_facts(
        self,
        start_time: datetime,
        source_filter: Optional[str],
        dry_run: bool,
        enabled_rules: Dict[str, InvalidationRule],
        all_facts: List[AtomicFact],
    ) -> Dict[str, Any]:
        """Process facts against rules and execute invalidation. Issue #620."""
        (
            facts_to_invalidate,
            invalidation_reasons,
            rule_statistics,
        ) = self._process_facts_against_rules(all_facts, enabled_rules)
        processing_time = (datetime.now() - start_time).total_seconds()
        invalidated_count = await self._execute_invalidation(
            dry_run, facts_to_invalidate, invalidation_reasons
        )

        await self._record_invalidation_sweep(
            source_filter=source_filter,
            dry_run=dry_run,
            facts_processed=len(all_facts),
            facts_identified=len(facts_to_invalidate),
            facts_invalidated=invalidated_count,
            processing_time=processing_time,
            rule_statistics=rule_statistics,
        )

        result = self._build_sweep_result(
            dry_run,
            all_facts,
            facts_to_invalidate,
            invalidated_count,
            processing_time,
            enabled_rules,
            rule_statistics,
            source_filter,
            invalidation_reasons,
        )
        return {
            "facts_to_invalidate": facts_to_invalidate,
            "invalidated_count": invalidated_count,
            "result": result,
        }

    def _build_sweep_error_response(
        self, message: str, processing_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Build error response for invalidation sweep.

        Issue #665: Extracted from run_invalidation_sweep to reduce function length.

        Args:
            message: Error message
            processing_time: Optional processing time in seconds

        Returns:
            Error response dictionary
        """
        response: Dict[str, Any] = {"status": "error", "message": message}
        if processing_time is not None:
            response["processing_time"] = processing_time
        return response

    def _build_no_facts_response(self) -> Dict[str, Any]:
        """
        Build response for when no facts are found.

        Issue #665: Extracted from run_invalidation_sweep to reduce function length.

        Returns:
            Success response with zero counts
        """
        return {
            "status": "success",
            "message": "No facts found to process",
            "facts_processed": 0,
            "facts_invalidated": 0,
        }

    async def run_invalidation_sweep(
        self, source_filter: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Run a comprehensive invalidation sweep.

        Issue #620: Refactored using Extract Method pattern for maintainability.

        Args:
            source_filter: Optional source filter
            dry_run: If True, only identify facts but don't invalidate

        Returns:
            Dictionary with invalidation results
        """
        start_time = datetime.now()
        logger.info("Starting invalidation sweep (dry_run=%s)", dry_run)

        try:
            if not self.fact_extraction_service:
                return self._build_sweep_error_response(
                    "Fact extraction service not available"
                )

            # Load rules and facts (Issue #665: uses helper)
            rules, all_facts = await self._load_rules_and_facts(source_filter)

            if not rules:
                return self._build_sweep_error_response(
                    "No invalidation rules available"
                )

            # Execute core sweep logic (Issue #620: uses helper)
            return await self._execute_sweep_core(
                start_time, source_filter, dry_run, rules, all_facts
            )

        except Exception as e:
            logger.error("Error in invalidation sweep: %s", e)
            processing_time = (datetime.now() - start_time).total_seconds()
            return self._build_sweep_error_response(str(e), processing_time)

    def _prepare_fact_for_invalidation(
        self, pipe, fact: AtomicFact, reasons: Dict[str, Dict[str, Any]]
    ) -> bool:
        """Prepare single fact for invalidation in pipeline (Issue #315: extracted helper).

        Args:
            pipe: Redis pipeline
            fact: Fact to invalidate
            reasons: Invalidation reasons dict

        Returns:
            True if successful, False if error
        """
        try:
            fact_key = f"atomic_fact:{fact.fact_id}"

            # Update fact data using model method (Issue #372 - reduces feature envy)
            fact.mark_invalidated(
                reason=reasons.get(fact.fact_id, {}), service="temporal_invalidation"
            )

            # Store updated fact
            fact_data = fact.to_dict()
            pipe.hset(fact_key, "data", json.dumps(fact_data))
            pipe.hset(fact_key, "is_active", "False")
            pipe.hset(fact_key, "valid_until", fact.valid_until.isoformat())

            # Update indices using model method (Issue #372 - reduces feature envy)
            pipe.sadd(self.invalidated_facts_key, fact.fact_id)
            pipe.srem("atomic_facts_index", fact.fact_id)
            for index_key in fact.get_index_keys():
                pipe.srem(index_key, fact.fact_id)
            return True
        except Exception as e:
            logger.error(
                "Error preparing fact %s for invalidation: %s", fact.fact_id, e
            )
            return False

    async def _invalidate_facts(
        self, facts: List[AtomicFact], reasons: Dict[str, Dict[str, Any]]
    ) -> int:
        """
        Invalidate a list of facts.

        Args:
            facts: Facts to invalidate
            reasons: Invalidation reasons for each fact

        Returns:
            Number of facts successfully invalidated
        """
        invalidated_count = 0

        if not self.redis_client:
            logger.error("Redis client not available for fact invalidation")
            return 0

        try:
            # Process facts in batches
            for i in range(0, len(facts), self.batch_size):
                batch = facts[i : i + self.batch_size]
                pipe = self.redis_client.pipeline()

                # Prepare facts using helper (Issue #315: reduced nesting)
                for fact in batch:
                    self._prepare_fact_for_invalidation(pipe, fact, reasons)

                # Execute batch operation
                try:
                    await pipe.execute()
                    invalidated_count += len(batch)
                    logger.debug("Invalidated batch of %s facts", len(batch))
                except Exception as e:
                    logger.error("Error executing batch invalidation: %s", e)
                    continue

            logger.info("Successfully invalidated %s facts", invalidated_count)
            return invalidated_count

        except Exception as e:
            logger.error("Error in fact invalidation: %s", e)
            return invalidated_count

    async def _record_invalidation_sweep(self, **kwargs):
        """Record invalidation sweep history."""
        try:
            if not self.redis_client:
                return

            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "sweep_id": str(uuid.uuid4()),
                **kwargs,
            }

            # Store in history list (keep last 100 entries)
            await self.redis_client.lpush(
                self.invalidation_history_key, json.dumps(history_entry)
            )
            await self.redis_client.ltrim(self.invalidation_history_key, 0, 99)

            logger.debug("Recorded invalidation sweep history")

        except Exception as e:
            logger.error("Error recording invalidation history: %s", e)

    def _find_contradictory_facts(
        self, new_fact: AtomicFact, similar_facts: List[AtomicFact]
    ) -> List[AtomicFact]:
        """
        Find facts that contradict the new fact.

        (Issue #398: extracted helper)
        """
        contradictory_facts = []
        # Cache new_fact lowercase values to avoid repeated calls (Issue #624)
        new_subject_lower = new_fact.subject.lower()
        new_predicate_lower = new_fact.predicate.lower()
        new_object_lower = new_fact.object.lower()
        for existing_fact in similar_facts:
            # Cache existing_fact lowercase values inside loop (Issue #624)
            existing_subject_lower = existing_fact.subject.lower()
            existing_predicate_lower = existing_fact.predicate.lower()
            existing_object_lower = existing_fact.object.lower()
            if (
                existing_subject_lower == new_subject_lower
                and existing_predicate_lower == new_predicate_lower
                and existing_object_lower != new_object_lower
                and existing_fact.fact_id != new_fact.fact_id
            ):
                if new_fact.is_contradictory_to(existing_fact):
                    contradictory_facts.append(existing_fact)
        return contradictory_facts

    def _build_contradiction_reasons(
        self, new_fact: AtomicFact, facts_to_invalidate: List[AtomicFact]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build invalidation reasons for contradictory facts.

        (Issue #398: extracted helper)
        """
        reasons = {}
        for fact in facts_to_invalidate:
            reasons[fact.fact_id] = {
                "rule_id": "contradiction_detection",
                "rule_name": "Contradiction Detection",
                "reason": InvalidationReason.CONTRADICTION_DETECTED.value,
                "contradicted_by": new_fact.fact_id,
                "new_fact_confidence": new_fact.confidence,
                "old_fact_confidence": fact.confidence,
                "timestamp": datetime.now().isoformat(),
            }
        return reasons

    async def invalidate_contradictory_facts(
        self, new_fact: AtomicFact
    ) -> Dict[str, Any]:
        """
        Invalidate facts that contradict a new fact.

        (Issue #398: refactored to use extracted helpers)

        Args:
            new_fact: New fact that may contradict existing facts

        Returns:
            Dictionary with contradiction invalidation results
        """
        try:
            if not self.fact_extraction_service:
                return {
                    "status": "error",
                    "message": "Fact extraction service not available",
                }

            logger.info(
                "Checking for contradictions with new fact: %s", new_fact.fact_id
            )

            similar_facts = await self.fact_extraction_service.get_facts_by_criteria(
                active_only=True, limit=1000
            )

            contradictory_facts = self._find_contradictory_facts(
                new_fact, similar_facts
            )

            invalidated_count = 0
            if contradictory_facts:
                high_confidence = [
                    f for f in contradictory_facts if new_fact.confidence > f.confidence
                ]

                if high_confidence:
                    reasons = self._build_contradiction_reasons(
                        new_fact, high_confidence
                    )
                    invalidated_count = await self._invalidate_facts(
                        high_confidence, reasons
                    )

            return {
                "status": "success",
                "contradictions_found": len(contradictory_facts),
                "facts_invalidated": invalidated_count,
                "new_fact_id": new_fact.fact_id,
            }

        except Exception as e:
            logger.error("Error in contradiction invalidation: %s", e)
            return {"status": "error", "message": str(e)}

    async def get_invalidation_statistics(self) -> Dict[str, Any]:
        """Get statistics about temporal invalidation operations."""
        try:
            if not self.redis_client:
                return {"error": "Redis client not available"}

            # Get total invalidated facts
            total_invalidated = await self.redis_client.scard(
                self.invalidated_facts_key
            )

            # Get recent invalidation history
            recent_history = await self.redis_client.lrange(
                self.invalidation_history_key, 0, 49
            )

            # Calculate statistics from history
            total_sweeps = len(recent_history)
            total_facts_processed = 0
            total_facts_invalidated = 0
            total_processing_time = 0.0

            rule_usage = {}

            for history_json in recent_history:
                try:
                    history = json.loads(history_json)
                    total_facts_processed += history.get("facts_processed", 0)
                    total_facts_invalidated += history.get("facts_invalidated", 0)
                    total_processing_time += history.get("processing_time", 0)

                    # Aggregate rule statistics
                    for rule_id, count in history.get("rule_statistics", {}).items():
                        rule_usage[rule_id] = rule_usage.get(rule_id, 0) + count

                except json.JSONDecodeError:
                    continue

            # Get current rules
            rules = await self._load_invalidation_rules()
            enabled_rules = sum(1 for r in rules.values() if r.enabled)

            avg_processing_time = (
                total_processing_time / total_sweeps if total_sweeps > 0 else 0
            )
            invalidation_rate = (
                total_facts_invalidated / total_facts_processed * 100
                if total_facts_processed > 0
                else 0
            )

            return {
                "total_invalidated_facts": total_invalidated,
                "recent_sweeps": total_sweeps,
                "total_facts_processed": total_facts_processed,
                "total_facts_invalidated_recent": total_facts_invalidated,
                "average_processing_time": round(avg_processing_time, 2),
                "invalidation_rate": round(invalidation_rate, 2),
                "total_rules": len(rules),
                "enabled_rules": enabled_rules,
                "rule_usage_statistics": rule_usage,
                "auto_invalidation_enabled": self.enable_auto_invalidation,
                "invalidation_interval_hours": self.invalidation_interval_hours,
            }

        except Exception as e:
            logger.error("Error getting invalidation statistics: %s", e)
            return {"error": str(e)}

    async def add_invalidation_rule(self, rule: InvalidationRule) -> Dict[str, Any]:
        """Add a new invalidation rule."""
        try:
            rules = await self._load_invalidation_rules()
            rules[rule.rule_id] = rule
            await self._store_invalidation_rules(rules)

            logger.info("Added invalidation rule: %s", rule.name)
            return {"status": "success", "rule_id": rule.rule_id}

        except Exception as e:
            logger.error("Error adding invalidation rule: %s", e)
            return {"status": "error", "message": str(e)}

    async def remove_invalidation_rule(self, rule_id: str) -> Dict[str, Any]:
        """Remove an invalidation rule."""
        try:
            rules = await self._load_invalidation_rules()
            if rule_id in rules:
                del rules[rule_id]
                await self._store_invalidation_rules(rules)
                logger.info("Removed invalidation rule: %s", rule_id)
                return {"status": "success", "rule_id": rule_id}
            else:
                return {"status": "error", "message": "Rule not found"}

        except Exception as e:
            logger.error("Error removing invalidation rule: %s", e)
            return {"status": "error", "message": str(e)}

    async def schedule_periodic_invalidation(self):
        """Schedule periodic invalidation sweeps."""
        if not self.enable_auto_invalidation:
            logger.info("Auto invalidation disabled")
            return

        logger.info(
            "Scheduling periodic invalidation every %s hours",
            self.invalidation_interval_hours,
        )

        while True:
            try:
                await asyncio.sleep(
                    self.invalidation_interval_hours * 3600
                )  # Convert to seconds

                logger.info("Running scheduled invalidation sweep")
                result = await self.run_invalidation_sweep(dry_run=False)

                if result["status"] == "success":
                    logger.info("Scheduled invalidation completed: ")
                else:
                    logger.error(
                        f"Scheduled invalidation failed: {result.get('message')}"
                    )

            except asyncio.CancelledError:
                logger.info("Periodic invalidation cancelled")
                break
            except Exception as e:
                logger.error("Error in periodic invalidation: %s", e)
                # Continue running despite errors
                continue


# Singleton instance for global access
temporal_invalidation_service = None


def get_temporal_invalidation_service(fact_extraction_service=None):
    """Get or create temporal invalidation service instance."""
    global temporal_invalidation_service
    if temporal_invalidation_service is None:
        temporal_invalidation_service = TemporalInvalidationService(
            fact_extraction_service
        )
    return temporal_invalidation_service
