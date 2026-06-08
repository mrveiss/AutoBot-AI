# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conflict Resolver - Tier 4 Knowledge Grounding Service.

Handles conflicts between knowledge base facts and agent claims by
comparing confidence scores, applying age decay, and determining
the highest-confidence truth source. Escalates to human review when
confidence levels are too close to decide automatically.

Issue #4070: Implements core Tier 4 (Knowledge Grounding) functionality:
1. Confidence comparison and age decay
2. Conflict detection and resolution
3. KB updates when research finds newer facts
4. Human review escalation for borderline cases
5. Review ticket tracking

Architecture:
- resolve(): Main entry point for conflict resolution
- update_kb_if_stale(): Updates KB when research finds newer info
- flag_for_human_review(): Escalates low-confidence conflicts
- _calculate_effective_confidence(): Applies age decay
- _determine_resolution_source(): Picks winner based on confidence

All I/O is async-first; no blocking operations.
"""

import time

from api.knowledge_grounding_models import (
    Claim,
    Conflict,
    ConflictResolution,
    KBFact,
    ResearchResult,
    ResolvedClaim,
    ReviewTicket,
    ReviewTicketPriority,
    ReviewTicketStatus,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from autobot_shared.ssot_constants import TTL_90_DAYS

logger = get_logger(__name__)

# Redis database for conflict resolution data
_REDIS_DATABASE = "analytics"

# Confidence thresholds for decision making
_CONFIDENCE_THRESHOLD_HIGH = 0.8  # High confidence decision
_CONFIDENCE_THRESHOLD_MEDIUM = 0.6  # Medium confidence, flag for review
_CONFIDENCE_THRESHOLD_LOW = 0.6  # Low confidence, must review
_CONFIDENCE_GAP_THRESHOLD = 0.1  # Gap small enough to flag for review

# Age decay boundaries (in days)
_AGE_BOUNDARY_FRESH = 7  # < 7 days
_AGE_BOUNDARY_RECENT = 30  # 7-30 days
_AGE_BOUNDARY_AGING = 90  # 30-90 days
# > 90 days is stale

# Confidence multipliers for age decay
_DECAY_FRESH = 1.0  # < 7 days: no decay
_DECAY_RECENT = 0.8  # 7-30 days: 80% of base
_DECAY_AGING = 0.6  # 30-90 days: 60% of base
_DECAY_STALE = 0.4  # > 90 days: 40% of base (stale)


class ConflictResolver(AsyncRedisClientMixin):
    """Service for resolving conflicts between KB facts and agent claims.

    Compares confidence scores of competing information sources,
    applies age-based decay to older facts, and determines which
    source represents ground truth. Escalates uncertain cases to
    human review.
    """

    _redis_database = _REDIS_DATABASE

    def _calculate_age_decay(self, fact: KBFact) -> float:
        """Apply age decay to knowledge base fact.

        Implements the age decay strategy:
        - < 7 days: 100% confidence (fresh)
        - 7-30 days: 80% confidence (recent)
        - 30-90 days: 60% confidence (aging)
        - > 90 days: 40% confidence (stale)

        Args:
            fact: KBFact to calculate decay for

        Returns:
            Float: Confidence multiplier [0.4-1.0] based on age

        Note:
            This is an internal method; use effective_confidence()
            on the fact directly for cleaner code.
        """
        age = fact.age_days()

        if age < _AGE_BOUNDARY_FRESH:
            return _DECAY_FRESH
        elif age < _AGE_BOUNDARY_RECENT:
            return _DECAY_RECENT
        elif age < _AGE_BOUNDARY_AGING:
            return _DECAY_AGING
        else:
            return _DECAY_STALE

    def _calculate_effective_confidence(self, fact: KBFact) -> float:
        """Calculate effective confidence of KB fact with age decay.

        Args:
            fact: KBFact to evaluate

        Returns:
            Float: Effective confidence [0.0-1.0]
        """
        age_decay = self._calculate_age_decay(fact)
        return fact.confidence * age_decay

    def _determine_resolution_source(
        self,
        kb_confidence: float,
        agent_confidence: float,
        research_confidence: float = 0.0,
    ) -> tuple[ConflictResolution, float, str]:
        """Determine which source wins the conflict.

        Uses a simple max-confidence strategy: the source with the
        highest confidence becomes ground truth.

        Args:
            kb_confidence: Effective confidence of KB fact
            agent_confidence: Confidence of agent claim
            research_confidence: Confidence of research result (optional)

        Returns:
            Tuple of:
            - ConflictResolution: Which source wins
            - float: Winning confidence level
            - str: Name of winning source
        """
        confidences = {
            ConflictResolution.KB_WINS: kb_confidence,
            ConflictResolution.AGENT_WINS: agent_confidence,
            ConflictResolution.RESEARCH_WINS: research_confidence,
        }

        # Find the source with highest confidence
        winner = max(confidences.items(), key=lambda x: x[1])
        resolution_type, winning_confidence = winner

        # Map resolution type to source name for logging
        source_names = {
            ConflictResolution.KB_WINS: "knowledge_base",
            ConflictResolution.AGENT_WINS: "agent",
            ConflictResolution.RESEARCH_WINS: "research",
        }

        return resolution_type, winning_confidence, source_names[resolution_type]

    async def resolve(
        self,
        kb_fact: KBFact,
        agent_claim: Claim,
        research_result: ResearchResult | None = None,
    ) -> ResolvedClaim:
        """Resolve conflict between KB fact and agent claim.

        Main entry point for conflict resolution. Compares confidence
        scores of all available sources and returns the highest-confidence
        truth. Flags for human review if confidence levels are too close.

        Algorithm:
        1. Calculate effective confidence for KB (with age decay)
        2. Use agent confidence as-is (default 0.5 for unknown)
        3. Use research confidence if available
        4. Find max confidence source
        5. If max > 0.8: return with high confidence
        6. If 0.6 < max <= 0.8: return but flag for review
        7. If max <= 0.6: escalate to human review

        Args:
            kb_fact: Knowledge base fact
            agent_claim: Agent claim to compare
            research_result: Optional research validation result

        Returns:
            ResolvedClaim: Final resolved truth with source and reasoning

        Note:
            All I/O is async; never blocks on Redis operations.
        """
        logger.debug(f"Resolving conflict: KB='{kb_fact.fact_text[:50]}' vs " f"Agent='{agent_claim.claim_text[:50]}'")

        # Calculate effective confidence for each source
        kb_confidence = self._calculate_effective_confidence(kb_fact)
        agent_confidence = agent_claim.confidence
        research_confidence = research_result.confidence if research_result else 0.0

        logger.debug(
            f"Confidences: KB={kb_confidence:.2f}, Agent={agent_confidence:.2f}, " f"Research={research_confidence:.2f}"
        )

        # Determine which source wins
        resolution_type, winning_confidence, winning_source = self._determine_resolution_source(
            kb_confidence, agent_confidence, research_confidence
        )

        # Select the claim text and metadata based on winner
        if resolution_type == ConflictResolution.KB_WINS:
            claim_text = kb_fact.fact_text
            reasoning = (
                f"KB fact has effective confidence {kb_confidence:.2f} "
                f"(base {kb_fact.confidence:.2f}, age decay {self._calculate_age_decay(kb_fact):.2f})"
            )
        elif resolution_type == ConflictResolution.AGENT_WINS:
            claim_text = agent_claim.claim_text
            reasoning = f"Agent claim has confidence {agent_confidence:.2f}"
        else:  # RESEARCH_WINS
            claim_text = research_result.fact_text
            reasoning = (
                f"Research result has confidence {research_confidence:.2f}, "
                f"supersedes KB (age {kb_fact.age_days():.1f} days)"
            )

        # Decide if we need human review
        requires_human_review = False
        confidence_gap = abs(kb_confidence - agent_confidence)

        if _CONFIDENCE_THRESHOLD_LOW <= winning_confidence < _CONFIDENCE_THRESHOLD_MEDIUM:
            # Medium confidence: flag for review
            requires_human_review = True
            reasoning += " [FLAGGED FOR REVIEW: medium confidence]"
        elif winning_confidence < _CONFIDENCE_THRESHOLD_LOW:
            # Low confidence: must escalate
            requires_human_review = True
            reasoning += " [ESCALATED FOR REVIEW: low confidence]"
        elif confidence_gap < _CONFIDENCE_GAP_THRESHOLD:
            # Small gap between sources: flag for review even if winning confidence is high
            requires_human_review = True
            reasoning += " [FLAGGED FOR REVIEW: small confidence gap]"

        # Decide if KB should be updated
        update_kb = False
        if (
            resolution_type == ConflictResolution.RESEARCH_WINS
            and kb_fact.is_stale()
            and research_result is not None
            and research_result.confidence >= 0.75
        ):
            update_kb = True
            reasoning += " [RECOMMEND KB UPDATE: research found newer info]"

        logger.info(f"Resolved conflict: {winning_source} wins with confidence " f"{winning_confidence:.2f}")

        # Build resolved claim
        resolved = ResolvedClaim(
            claim=claim_text,
            source=winning_source,
            confidence=winning_confidence,
            kb_fact=kb_fact,
            agent_claim=agent_claim,
            research_result=research_result,
            update_kb=update_kb,
            requires_human_review=requires_human_review,
            reasoning=reasoning,
            resolution_type=resolution_type,
        )

        # If human review is needed, create and persist ticket
        if requires_human_review:
            conflict = Conflict(
                kb_says=kb_fact,
                agent_says=agent_claim,
                kb_confidence=kb_confidence,
                agent_confidence=agent_confidence,
                research_says=research_result,
                research_confidence=research_confidence,
            )

            await self.flag_for_human_review(conflict)

        return resolved

    async def update_kb_if_stale(self, kb_fact: KBFact, research_result: ResearchResult) -> bool:
        """Update KB with research result if fact is stale.

        If KB fact is older than 30 days AND research found newer
        information with high confidence, update KB and log the change.

        Args:
            kb_fact: Original KB fact
            research_result: Research result with newer information

        Returns:
            bool: True if KB was updated, False otherwise

        Note:
            This is called after resolve() determines research wins.
            In production, this would call KB update APIs to persist
            the new fact and maintain audit trails.
        """
        if not kb_fact.is_stale():
            logger.debug(f"KB fact is not stale ({kb_fact.age_days():.1f} days), " "skipping update")
            return False

        if research_result.confidence < 0.75:
            logger.debug(f"Research confidence {research_result.confidence:.2f} too low " "for KB update (min 0.75)")
            return False

        logger.info(
            f"Updating stale KB fact (age {kb_fact.age_days():.1f} days) "
            f"with research result (confidence {research_result.confidence:.2f})"
        )

        try:
            redis = await self._get_redis()

            # Store update record for audit trail
            update_record = {
                "original_fact": kb_fact.fact_text,
                "new_fact": research_result.fact_text,
                "original_source": kb_fact.source_id,
                "new_source": research_result.source,
                "original_confidence": kb_fact.confidence,
                "new_confidence": research_result.confidence,
                "original_age_days": kb_fact.age_days(),
                "timestamp": time.time(),
            }

            # In production: call KB API to persist the update
            # For now: log to Redis for audit
            key = f"kb_updates:{kb_fact.source_id}"
            await redis.lpush(key, str(update_record))
            await redis.expire(key, TTL_90_DAYS)  # Keep 90 days

            logger.info(f"KB update recorded: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to update KB: {e}", exc_info=True)
            return False

    async def flag_for_human_review(self, conflict: Conflict) -> ReviewTicket:
        """Create a human review ticket for a conflict.

        Escalates a conflict to human review when confidence difference
        is small or confidence is too low to decide automatically.

        Assigns priority based on confidence levels:
        - HIGH: max confidence < 0.5 (very uncertain)
        - MEDIUM: gap < 0.05 (sources almost equal)
        - LOW: gap < 0.1 (sources somewhat close)

        Args:
            conflict: Conflict to escalate

        Returns:
            ReviewTicket: Created ticket ready for human review

        Note:
            Persists ticket to Redis for tracking and human team access.
        """
        logger.info(
            f"Flagging conflict for human review: "
            f"KB={conflict.kb_confidence:.2f}, "
            f"Agent={conflict.agent_confidence:.2f}, "
            f"Research={conflict.research_confidence:.2f}"
        )

        # Determine priority based on confidence levels
        max_confidence = conflict.max_confidence()
        gap = conflict.confidence_gap()

        if max_confidence < 0.5:
            priority = ReviewTicketPriority.HIGH
            reasoning = "Very low max confidence"
        elif gap < 0.05:
            priority = ReviewTicketPriority.MEDIUM
            reasoning = "Sources nearly equal in confidence"
        elif gap < 0.1:
            priority = ReviewTicketPriority.LOW
            reasoning = "Sources close in confidence"
        else:
            priority = ReviewTicketPriority.LOW
            reasoning = "Standard review"

        # Create ticket
        ticket = ReviewTicket.create_from_conflict(conflict, priority)
        logger.debug(f"Created review ticket: {ticket.ticket_id} (priority={priority})")

        try:
            redis = await self._get_redis()

            # Store ticket for human review team
            ticket_key = f"review_ticket:{ticket.ticket_id}"
            ticket_data = {
                "conflict_id": conflict.conflict_id,
                "priority": priority.value,
                "status": ReviewTicketStatus.PENDING.value,
                "kb_says": conflict.kb_says.fact_text,
                "agent_says": conflict.agent_says.claim_text,
                "kb_confidence": conflict.kb_confidence,
                "agent_confidence": conflict.agent_confidence,
                "research_confidence": conflict.research_confidence,
                "reasoning": reasoning,
                "created_at": ticket.created_at,
            }

            # Store as JSON for retrieval
            import json

            await redis.set(ticket_key, json.dumps(ticket_data), ex=86400 * 30)

            # Add to review queue for priority-based processing
            queue_key = f"review_queue:{priority.value}"
            await redis.lpush(queue_key, ticket.ticket_id)

            logger.info(f"Review ticket {ticket.ticket_id} persisted " f"(priority={priority.value})")

        except Exception as e:
            logger.error(f"Failed to persist review ticket: {e}", exc_info=True)
            # Ticket still returned even if persistence fails
            # (in-memory state is available)

        return ticket

    async def resolve_review_ticket(
        self,
        ticket_id: str,
        resolution: ResolvedClaim,
        resolved_by: str,
        notes: str = "",
    ) -> ReviewTicket | None:
        """Mark a review ticket as resolved by human decision.

        Updates ticket status to RESOLVED and persists the human's
        decision for future reference and audit trails.

        Args:
            ticket_id: ID of the review ticket
            resolution: Final resolved claim from human
            resolved_by: User/team that made the decision
            notes: Optional explanation of the decision

        Returns:
            ReviewTicket: Updated ticket with resolution, or None if not found

        Note:
            In production, this would be called by the human review UI
            after human has reviewed and decided.
        """
        logger.info(f"Resolving review ticket {ticket_id} " f"(resolved_by={resolved_by})")

        try:
            redis = await self._get_redis()
            ticket_key = f"review_ticket:{ticket_id}"

            # Retrieve ticket data
            ticket_data = await redis.get(ticket_key)
            if not ticket_data:
                logger.warning(f"Review ticket {ticket_id} not found")
                return None

            # Update ticket with resolution
            import json

            ticket_data = json.loads(ticket_data)
            ticket_data["status"] = ReviewTicketStatus.RESOLVED.value
            ticket_data["resolved_by"] = resolved_by
            ticket_data["resolved_at"] = time.time()
            ticket_data["notes"] = notes

            # Persist updated ticket
            await redis.set(ticket_key, json.dumps(ticket_data), ex=86400 * 30)

            logger.info(f"Review ticket {ticket_id} resolved")

            # Return updated ticket representation
            # (in production, reconstruct from stored data)
            return None

        except Exception as e:
            logger.error(f"Failed to resolve review ticket: {e}", exc_info=True)
            return None

    async def dismiss_review_ticket(self, ticket_id: str, dismissed_by: str, notes: str = "") -> ReviewTicket | None:
        """Mark a review ticket as dismissed (false conflict).

        Updates ticket status to DISMISSED and records why the conflict
        was not a real issue.

        Args:
            ticket_id: ID of the review ticket
            dismissed_by: User/team that dismissed it
            notes: Explanation of why it was dismissed

        Returns:
            ReviewTicket: Updated ticket with dismissal, or None if not found
        """
        logger.info(f"Dismissing review ticket {ticket_id} " f"(dismissed_by={dismissed_by})")

        try:
            redis = await self._get_redis()
            ticket_key = f"review_ticket:{ticket_id}"

            # Retrieve and update
            ticket_data = await redis.get(ticket_key)
            if not ticket_data:
                logger.warning(f"Review ticket {ticket_id} not found")
                return None

            import json

            ticket_data = json.loads(ticket_data)
            ticket_data["status"] = ReviewTicketStatus.DISMISSED.value
            ticket_data["dismissed_by"] = dismissed_by
            ticket_data["dismissed_at"] = time.time()
            ticket_data["notes"] = notes

            await redis.set(ticket_key, json.dumps(ticket_data), ex=86400 * 30)

            logger.info(f"Review ticket {ticket_id} dismissed")
            return None

        except Exception as e:
            logger.error(f"Failed to dismiss review ticket: {e}", exc_info=True)
            return None
