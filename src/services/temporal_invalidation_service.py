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

from src.models.atomic_fact import AtomicFact, FactType, TemporalType
from src.services.fact_extraction_service import FactExtractionService
from src.utils.config_manager import config_manager
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
                f"Invalidation rules initialized: {len(existing_rules)} total, "
                f"{rules_added} added"
            )

            return {
                "status": "success",
                "total_rules": len(existing_rules),
                "rules_added": rules_added,
                "message": "Invalidation rules initialized successfully",
            }

        except Exception as e:
            logger.error(f"Error initializing invalidation rules: {e}")
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
                    logger.error(f"Error loading rule {rule_id}: {e}")
                    continue

            return rules

        except Exception as e:
            logger.error(f"Error loading invalidation rules: {e}")
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
            logger.debug(f"Stored {len(rules)} invalidation rules")

        except Exception as e:
            logger.error(f"Error storing invalidation rules: {e}")

    async def run_invalidation_sweep(
        self, source_filter: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Run a comprehensive invalidation sweep.

        Args:
            source_filter: Optional source filter
            dry_run: If True, only identify facts but don't invalidate

        Returns:
            Dictionary with invalidation results
        """
        start_time = datetime.now()
        logger.info(f"Starting invalidation sweep (dry_run={dry_run})")

        try:
            if not self.fact_extraction_service:
                return {
                    "status": "error",
                    "message": "Fact extraction service not available",
                }

            # Load invalidation rules
            rules = await self._load_invalidation_rules()
            if not rules:
                return {"status": "error", "message": "No invalidation rules available"}

            enabled_rules = {k: v for k, v in rules.items() if v.enabled}
            logger.info(f"Using {len(enabled_rules)} enabled invalidation rules")

            # Get all active facts
            all_facts = await self.fact_extraction_service.get_facts_by_criteria(
                source=source_filter,
                active_only=True,
                limit=10000,  # Large limit to get all facts
            )

            if not all_facts:
                return {
                    "status": "success",
                    "message": "No facts found to process",
                    "facts_processed": 0,
                    "facts_invalidated": 0,
                }

            logger.info(f"Processing {len(all_facts)} active facts")

            # Process facts in batches
            facts_to_invalidate = []
            invalidation_reasons = {}
            rule_statistics = {rule_id: 0 for rule_id in enabled_rules.keys()}

            for i, fact in enumerate(all_facts):
                if i % 100 == 0:
                    logger.debug(f"Processed {i}/{len(all_facts)} facts")

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

            processing_time = (datetime.now() - start_time).total_seconds()

            # Invalidate facts if not dry run
            invalidated_count = 0
            if not dry_run and facts_to_invalidate:
                invalidated_count = await self._invalidate_facts(
                    facts_to_invalidate, invalidation_reasons
                )

            # Record invalidation sweep history
            await self._record_invalidation_sweep(
                source_filter=source_filter,
                dry_run=dry_run,
                facts_processed=len(all_facts),
                facts_identified=len(facts_to_invalidate),
                facts_invalidated=invalidated_count,
                processing_time=processing_time,
                rule_statistics=rule_statistics,
            )

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

            logger.info(
                f"Invalidation sweep completed: {invalidated_count}/"
                f"{len(facts_to_invalidate)} facts invalidated"
            )
            return result

        except Exception as e:
            logger.error(f"Error in invalidation sweep: {e}")
            return {
                "status": "error",
                "message": str(e),
                "processing_time": (datetime.now() - start_time).total_seconds(),
            }

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

                # Use Redis pipeline for batch operations
                pipe = self.redis_client.pipeline()

                for fact in batch:
                    try:
                        # Mark fact as inactive
                        fact_key = f"atomic_fact:{fact.fact_id}"

                        # Update fact data
                        fact.is_active = False
                        fact.valid_until = datetime.now()
                        fact.metadata = fact.metadata or {}
                        fact.metadata.update(
                            {
                                "invalidated_at": datetime.now().isoformat(),
                                "invalidation_reason": reasons.get(fact.fact_id, {}),
                                "invalidation_service": "temporal_invalidation",
                            }
                        )

                        # Store updated fact
                        fact_data = fact.to_dict()
                        pipe.hset(fact_key, "data", json.dumps(fact_data))
                        pipe.hset(fact_key, "is_active", "False")
                        pipe.hset(fact_key, "valid_until", fact.valid_until.isoformat())

                        # Add to invalidated facts index
                        pipe.sadd(self.invalidated_facts_key, fact.fact_id)

                        # Remove from active facts indices
                        pipe.srem("atomic_facts_index", fact.fact_id)
                        pipe.srem(f"facts_by_source:{fact.source}", fact.fact_id)
                        pipe.srem(f"facts_by_type:{fact.fact_type.value}", fact.fact_id)
                        pipe.srem(
                            f"facts_by_temporal:{fact.temporal_type.value}",
                            fact.fact_id,
                        )

                    except Exception as e:
                        logger.error(
                            f"Error preparing fact {fact.fact_id} for "
                            f"invalidation: {e}"
                        )
                        continue

                # Execute batch operation
                try:
                    await pipe.execute()
                    invalidated_count += len(batch)
                    logger.debug(f"Invalidated batch of {len(batch)} facts")
                except Exception as e:
                    logger.error(f"Error executing batch invalidation: {e}")
                    continue

            logger.info(f"Successfully invalidated {invalidated_count} facts")
            return invalidated_count

        except Exception as e:
            logger.error(f"Error in fact invalidation: {e}")
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
            logger.error(f"Error recording invalidation history: {e}")

    async def invalidate_contradictory_facts(
        self, new_fact: AtomicFact
    ) -> Dict[str, Any]:
        """
        Invalidate facts that contradict a new fact.

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
                f"Checking for contradictions with new fact: " f"{new_fact.fact_id}"
            )

            # Get facts with same subject and predicate
            similar_facts = await self.fact_extraction_service.get_facts_by_criteria(
                active_only=True, limit=1000
            )

            contradictory_facts = []
            for existing_fact in similar_facts:
                if (
                    existing_fact.subject.lower() == new_fact.subject.lower()
                    and existing_fact.predicate.lower() == new_fact.predicate.lower()
                    and existing_fact.object.lower() != new_fact.object.lower()
                    and existing_fact.fact_id != new_fact.fact_id
                ):
                    # Check if this is a meaningful contradiction
                    if new_fact.is_contradictory_to(existing_fact):
                        contradictory_facts.append(existing_fact)

            # Invalidate contradictory facts if new fact has higher confidence
            invalidated_count = 0
            if contradictory_facts:
                high_confidence_contradictions = [
                    f for f in contradictory_facts if new_fact.confidence > f.confidence
                ]

                if high_confidence_contradictions:
                    reasons = {}
                    for fact in high_confidence_contradictions:
                        reasons[fact.fact_id] = {
                            "rule_id": "contradiction_detection",
                            "rule_name": "Contradiction Detection",
                            "reason": InvalidationReason.CONTRADICTION_DETECTED.value,
                            "contradicted_by": new_fact.fact_id,
                            "new_fact_confidence": new_fact.confidence,
                            "old_fact_confidence": fact.confidence,
                            "timestamp": datetime.now().isoformat(),
                        }

                    invalidated_count = await self._invalidate_facts(
                        high_confidence_contradictions, reasons
                    )

            return {
                "status": "success",
                "contradictions_found": len(contradictory_facts),
                "facts_invalidated": invalidated_count,
                "new_fact_id": new_fact.fact_id,
            }

        except Exception as e:
            logger.error(f"Error in contradiction invalidation: {e}")
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
            logger.error(f"Error getting invalidation statistics: {e}")
            return {"error": str(e)}

    async def add_invalidation_rule(self, rule: InvalidationRule) -> Dict[str, Any]:
        """Add a new invalidation rule."""
        try:
            rules = await self._load_invalidation_rules()
            rules[rule.rule_id] = rule
            await self._store_invalidation_rules(rules)

            logger.info(f"Added invalidation rule: {rule.name}")
            return {"status": "success", "rule_id": rule.rule_id}

        except Exception as e:
            logger.error(f"Error adding invalidation rule: {e}")
            return {"status": "error", "message": str(e)}

    async def remove_invalidation_rule(self, rule_id: str) -> Dict[str, Any]:
        """Remove an invalidation rule."""
        try:
            rules = await self._load_invalidation_rules()
            if rule_id in rules:
                del rules[rule_id]
                await self._store_invalidation_rules(rules)
                logger.info(f"Removed invalidation rule: {rule_id}")
                return {"status": "success", "rule_id": rule_id}
            else:
                return {"status": "error", "message": "Rule not found"}

        except Exception as e:
            logger.error(f"Error removing invalidation rule: {e}")
            return {"status": "error", "message": str(e)}

    async def schedule_periodic_invalidation(self):
        """Schedule periodic invalidation sweeps."""
        if not self.enable_auto_invalidation:
            logger.info("Auto invalidation disabled")
            return

        logger.info(
            f"Scheduling periodic invalidation every "
            f"{self.invalidation_interval_hours} hours"
        )

        while True:
            try:
                await asyncio.sleep(
                    self.invalidation_interval_hours * 3600
                )  # Convert to seconds

                logger.info("Running scheduled invalidation sweep")
                result = await self.run_invalidation_sweep(dry_run=False)

                if result["status"] == "success":
                    logger.info(
                        f"Scheduled invalidation completed: "
                        f"{result['facts_invalidated']} facts invalidated"
                    )
                else:
                    logger.error(
                        f"Scheduled invalidation failed: {result.get('message')}"
                    )

            except asyncio.CancelledError:
                logger.info("Periodic invalidation cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic invalidation: {e}")
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
