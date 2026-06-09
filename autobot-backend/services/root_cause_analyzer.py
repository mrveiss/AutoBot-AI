# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Root Cause Analysis Service - Trace causal failure chains from error events.

Issue #4068: Traces causal failure chains backward to identify root causes.
Integrates with TemporalSearchService.find_causal_chain() for event traversal.

Provides:
- RootCauseAnalyzer: Analyzes task failures via causal chain traversal
- RootCauseReport: Structured causal explanation with confidence scores
- Confounder detection: Identifies when multiple causes contribute to failure
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from knowledge.temporal_search import TemporalSearchService

logger = get_logger(__name__)


@dataclass
class CausalEvent:
    """A single event in the causal chain."""

    event_id: str
    event_type: str
    name: str
    description: str
    timestamp: str
    confidence: float = 1.0
    depth: int = 0
    participants: List[str] = field(default_factory=list)


@dataclass
class RootCauseReport:
    """Structured root cause analysis report."""

    task_id: str
    root_event: CausalEvent | None = None
    causal_chain: List[CausalEvent] = field(default_factory=list)
    confidence: float = 0.0
    explanations: List[str] = field(default_factory=list)
    confounders: List[CausalEvent] = field(default_factory=list)
    chain_depth: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    analysis_status: str = "success"  # success, partial, failed
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert report to dictionary for API serialization."""
        return {
            "task_id": self.task_id,
            "root_event": (self._event_to_dict(self.root_event) if self.root_event else None),
            "causal_chain": [self._event_to_dict(e) for e in self.causal_chain],
            "confidence": self.confidence,
            "explanations": self.explanations,
            "confounders": [self._event_to_dict(c) for c in self.confounders],
            "chain_depth": self.chain_depth,
            "timestamp": self.timestamp,
            "analysis_status": self.analysis_status,
            "error_message": self.error_message,
        }

    @staticmethod
    def _event_to_dict(event: CausalEvent | None) -> dict | None:
        """Convert CausalEvent to dictionary."""
        if not event:
            return None
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "name": event.name,
            "description": event.description,
            "timestamp": event.timestamp,
            "confidence": event.confidence,
            "depth": event.depth,
            "participants": event.participants,
        }


class RootCauseAnalyzer:
    """
    Analyzes root causes of task failures via causal chain traversal.

    Uses TemporalSearchService.find_causal_chain() to traverse event causality
    and synthesizes user-friendly explanations from the causal graph.
    """

    def __init__(self) -> None:
        """Initialize root cause analyzer."""
        self.redis_client = None
        self.temporal_service = None

    async def _ensure_initialized(self) -> None:
        """Lazily initialize Redis and temporal service."""
        if self.redis_client is None:
            try:
                self.redis_client = await get_async_redis_client(database="knowledge")
                self.temporal_service = TemporalSearchService(self.redis_client)
            except Exception as e:
                logger.error("Failed to initialize Redis client: %s", e)
                raise

    async def analyze_task_failure(self, task_id: str) -> RootCauseReport:
        """
        Analyze the root cause of a task failure.

        Args:
            task_id: The failed task ID (may be a UUID string or task reference)

        Returns:
            RootCauseReport with causal chain, root event, and explanations
        """
        try:
            await self._ensure_initialized()
        except Exception as e:
            logger.error("Failed to initialize analyzer: %s", e)
            return RootCauseReport(
                task_id=task_id,
                analysis_status="failed",
                error_message=f"Analysis error: {str(e)}",
            )

        try:
            # Fetch error event for this task from Redis
            error_event_id = await self._get_error_event_id(task_id)
            if not error_event_id:
                return RootCauseReport(
                    task_id=task_id,
                    analysis_status="failed",
                    error_message=f"No error event found for task {task_id}",
                )

            # Traverse causal chain backward (causes -> root causes)
            chain = await self.temporal_service.find_causal_chain(
                event_id=UUID(error_event_id),
                direction="backward",
                max_depth=5,
            )

            if not chain:
                return RootCauseReport(
                    task_id=task_id,
                    analysis_status="partial",
                    error_message="Could not traverse causal chain",
                )

            # Build report from chain
            report = await self._build_report(task_id, chain)
            return report

        except Exception as e:
            logger.error("Root cause analysis failed for task %s: %s", task_id, e)
            return RootCauseReport(
                task_id=task_id,
                analysis_status="failed",
                error_message=f"Analysis error: {str(e)}",
            )

    async def _get_error_event_id(self, task_id: str) -> str | None:
        """
        Lookup error event ID from task_id.

        Error events are indexed by task_id in Redis.
        Key format: task:{task_id}:error_event_id

        Args:
            task_id: The task ID to lookup

        Returns:
            Event UUID string, or None if not found
        """
        try:
            key = f"task:{task_id}:error_event_id"
            event_id = await self.redis_client.get(key)
            if event_id:
                return event_id.decode() if isinstance(event_id, bytes) else event_id
            return None
        except Exception as e:
            logger.warning("Failed to lookup error event for task %s: %s", task_id, e)
            return None

    async def _build_report(self, task_id: str, chain: List[dict]) -> RootCauseReport:
        """
        Build RootCauseReport from causal chain.

        Args:
            task_id: Task ID being analyzed
            chain: List of event dicts from find_causal_chain()

        Returns:
            RootCauseReport with structured analysis
        """
        if not chain:
            return RootCauseReport(
                task_id=task_id,
                analysis_status="partial",
                chain_depth=0,
            )

        # Convert raw event dicts to CausalEvent objects
        causal_events = []
        for idx, event_dict in enumerate(chain):
            causal_events.append(
                CausalEvent(
                    event_id=str(event_dict.get("id", event_dict.get("event_id", ""))),
                    event_type=event_dict.get("event_type", "unknown"),
                    name=event_dict.get("name", ""),
                    description=event_dict.get("description", ""),
                    timestamp=event_dict.get("timestamp", ""),
                    confidence=event_dict.get("confidence", 1.0),
                    depth=idx,
                    participants=[str(p) for p in event_dict.get("participants", [])],
                )
            )

        # Root event is the last in the backward chain (oldest cause)
        root_event = causal_events[-1] if causal_events else None

        # Detect confounders (multiple independent causal paths at depth 1)
        confounders = self._detect_confounders(causal_events)

        # Generate explanations
        explanations = self._generate_explanations(causal_events, confounders)

        # Calculate confidence based on chain completeness and event confidence
        confidence = self._calculate_confidence(causal_events)

        return RootCauseReport(
            task_id=task_id,
            root_event=root_event,
            causal_chain=causal_events,
            confidence=confidence,
            explanations=explanations,
            confounders=confounders,
            chain_depth=len(causal_events),
            analysis_status="success",
        )

    def _detect_confounders(self, chain: List[CausalEvent]) -> List[CausalEvent]:
        """
        Detect confounding events (multiple independent causes at same depth).

        Confounders are secondary causes that contribute to failure alongside
        the root cause, making the failure multi-factorial.

        Args:
            chain: Causal event chain

        Returns:
            List of confounder events (if any)
        """
        if len(chain) < 2:
            return []

        # Group by depth
        by_depth = {}
        max_depth = 0
        for event in chain:
            if event.depth not in by_depth:
                by_depth[event.depth] = []
            by_depth[event.depth].append(event)
            max_depth = max(max_depth, event.depth)

        # Identify confounders: multiple events at same depth (excluding root depth)
        confounders = []
        for depth, events in by_depth.items():
            if len(events) > 1 and depth < max_depth:
                # Multiple causes at same level (not root); keep all but first as confounders
                confounders.extend(events[1:])

        return confounders

    def _generate_explanations(self, chain: List[CausalEvent], confounders: List[CausalEvent]) -> List[str]:
        """
        Generate human-readable causal explanations.

        Args:
            chain: Causal event chain
            confounders: Confounder events

        Returns:
            List of explanation strings
        """
        explanations = []

        if not chain:
            return ["No causal chain found"]

        # Root cause explanation
        if len(chain) > 0:
            root = chain[-1]
            explanations.append(f"Root cause: {root.name or root.event_type} " f"({root.timestamp or 'unknown time'})")

        # Immediate cause explanation
        if len(chain) > 1:
            immediate = chain[0]
            root = chain[-1]
            explanations.append(
                f"Immediate trigger: {immediate.name or immediate.event_type} "
                f"(caused by '{root.name or root.event_type}')"
            )

        # Chain path explanation
        if len(chain) > 2:
            path = " → ".join([e.name or e.event_type for e in reversed(chain)])
            explanations.append(f"Causal path: {path}")

        # Confounder explanation
        if confounders:
            confounder_names = ", ".join([c.name or c.event_type for c in confounders])
            explanations.append(f"Contributing factors: {confounder_names} " "(multiple causes amplified failure)")

        # Confidence level explanation
        if len(chain) >= 3:
            explanations.append("High confidence: Multi-level causal path traced successfully")
        elif len(chain) == 2:
            explanations.append("Medium confidence: Direct cause identified")
        else:
            explanations.append("Low confidence: Limited causal information available")

        return explanations

    def _calculate_confidence(self, chain: List[CausalEvent]) -> float:
        """
        Calculate overall confidence in the analysis.

        Confidence increases with:
        - Chain depth (more events traced)
        - Individual event confidence scores
        - Completeness of event data

        Args:
            chain: Causal event chain

        Returns:
            Confidence score 0.0-1.0
        """
        if not chain:
            return 0.0

        # Base confidence from chain depth (max 0.6 from depth)
        max_depth = 5
        depth_score = min(len(chain) / max_depth, 1.0) * 0.6

        # Average event confidence (max 0.4 from event quality)
        event_confidence = (sum(e.confidence for e in chain) / len(chain)) * 0.4

        return depth_score + event_confidence
