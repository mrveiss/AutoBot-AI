# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking - Main Tracker Module

Enhanced tracking system for comprehensive project state management.

Part of Issue #381 - God Class Refactoring
Issue #357: Wrapped blocking SQLite operations with asyncio.to_thread().
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from scripts.phase_validation_system import PhaseValidator
from src.constants.path_constants import PATH
from src.constants.threshold_constants import TimingConstants
from src.phase_progression_manager import get_progression_manager
from src.project_state_manager import ProjectStateManager
from src.utils.redis_client import get_redis_client

from .database import (
    init_database,
    load_milestones_from_db,
    load_snapshots_from_db,
    record_state_change_sync,
    save_milestone_sync,
    save_snapshot_sync,
)
from .metrics import (
    calculate_progression_velocity,
    get_api_calls_count,
    get_error_rate,
    get_metrics_summary,
    get_user_interactions_count,
)
from .milestones import define_default_milestones, evaluate_milestone_criteria
from .models import ProjectMilestone, StateChange, StateSnapshot
from .reports import calculate_trends, export_state_data_to_file
from .tracking import (
    track_api_call_to_redis,
    track_error_to_redis,
    track_user_interaction_to_redis,
)
from .types import (
    SIGNIFICANT_CHANGES,
    SIGNIFICANT_INTERACTIONS,
    StateChangeType,
    TrackingMetric,
)

try:
    from src.utils.error_boundaries import get_error_boundary_manager
except ImportError:

    def get_error_boundary_manager():
        """Return None when error_boundaries module is unavailable."""
        return None


logger = logging.getLogger(__name__)


class EnhancedProjectStateTracker:
    """Enhanced tracking system for comprehensive project state management."""

    def __init__(self, db_path: str = "data/project_state_tracking.db"):
        """Initialize enhanced project state tracker with database and validators."""
        self.db_path = db_path
        # Use centralized PathConstants (Issue #380)
        self.project_root = PATH.PROJECT_ROOT

        # Core components
        self.progression_manager = get_progression_manager()
        self.legacy_state_manager = ProjectStateManager()
        self.validator = PhaseValidator(self.project_root)

        # State tracking
        self.state_history: List[StateSnapshot] = []
        self.change_log: List[StateChange] = []
        self.milestones: Dict[str, ProjectMilestone] = {}

        # Metrics tracking
        self.metrics_history: Dict[TrackingMetric, List[Tuple[datetime, float]]] = {
            metric: [] for metric in TrackingMetric
        }

        # Redis client for real-time metrics
        self.redis_client = get_redis_client()

        # Error tracking
        self.error_boundary_manager = get_error_boundary_manager()

        # Tracking state
        self._last_snapshot_time = datetime.now()
        self._api_call_count = 0
        self._user_interaction_count = 0
        self._error_count = 0
        self._counter_lock = asyncio.Lock()

        # Initialize database and load state
        init_database(self.db_path)
        self._define_milestones()
        self._load_state()

        # Start background tracking
        self._start_background_tracking()

        logger.info("Enhanced Project State Tracker initialized")

    def _define_milestones(self):
        """Define project milestones to track."""
        self.milestones = define_default_milestones()

    def _load_state(self):
        """Load state from database."""
        try:
            self.state_history = load_snapshots_from_db(self.db_path, limit=100)
            load_milestones_from_db(self.db_path, self.milestones)
            logger.info("Loaded %s state snapshots", len(self.state_history))
        except Exception as e:
            logger.error("Error loading state: %s", e)

    def _extract_phase_states(
        self, validation_results: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract phase states from validation results (Issue #665: extracted helper).

        Args:
            validation_results: Results from validator.validate_all_phases()

        Returns:
            Dictionary mapping phase names to their state data
        """
        phase_states = {}
        for phase_name, phase_data in validation_results["phases"].items():
            phase_states[phase_name] = {
                "completion_percentage": phase_data["completion_percentage"],
                "status": phase_data["status"],
                "missing_items": phase_data.get("missing_items", []),
            }
        return phase_states

    async def _calculate_snapshot_metrics(
        self,
        phase_states: Dict[str, Dict[str, Any]],
        capabilities: Dict[str, Any],
        validation_results: Dict[str, Any],
    ) -> Dict[TrackingMetric, Any]:
        """
        Calculate tracking metrics for snapshot (Issue #665: extracted helper).

        Args:
            phase_states: Extracted phase state data
            capabilities: System capabilities from progression manager
            validation_results: Results from validator

        Returns:
            Dictionary of tracking metrics
        """
        return {
            TrackingMetric.PHASE_COMPLETION: len(
                [p for p in phase_states.values() if p["completion_percentage"] >= 95.0]
            ),
            TrackingMetric.CAPABILITY_COUNT: len(capabilities["active_capabilities"]),
            TrackingMetric.VALIDATION_SCORE: validation_results["overall_assessment"][
                "system_maturity_score"
            ],
            TrackingMetric.SYSTEM_MATURITY: capabilities["system_maturity"],
            TrackingMetric.ERROR_RATE: await get_error_rate(
                self.redis_client, self._error_count
            ),
            TrackingMetric.PROGRESSION_VELOCITY: calculate_progression_velocity(
                self.state_history
            ),
            TrackingMetric.USER_INTERACTIONS: await get_user_interactions_count(
                self.redis_client, self._user_interaction_count
            ),
            TrackingMetric.API_CALLS: await get_api_calls_count(
                self.redis_client, self._api_call_count
            ),
        }

    async def capture_state_snapshot(self) -> StateSnapshot:
        """
        Capture current system state.

        Issue #665: Refactored to use extracted helpers for phase extraction
        and metrics calculation.
        """
        try:
            # Get phase validation results and capabilities
            validation_results = await self.validator.validate_all_phases()
            capabilities = self.progression_manager.get_current_system_capabilities()

            # Extract phase states and calculate metrics (Issue #665: uses helpers)
            phase_states = self._extract_phase_states(validation_results)
            metrics = await self._calculate_snapshot_metrics(
                phase_states, capabilities, validation_results
            )

            # Get configuration
            config = self.progression_manager.config.copy()

            # Create snapshot
            snapshot = StateSnapshot(
                timestamp=datetime.now(),
                phase_states=phase_states,
                active_capabilities=set(capabilities["active_capabilities"]),
                system_metrics=metrics,
                configuration=config,
                validation_results={
                    phase: data["completion_percentage"]
                    for phase, data in phase_states.items()
                },
                metadata={
                    "total_phases": len(phase_states),
                    "completed_phases": metrics[TrackingMetric.PHASE_COMPLETION],
                    "snapshot_source": "automated_capture",
                },
            )

            # Save to history
            self.state_history.append(snapshot)
            if len(self.state_history) > 1000:
                self.state_history = self.state_history[-1000:]

            # Issue #379: Parallelize independent snapshot operations
            await asyncio.gather(
                self._save_snapshot(snapshot),
                self._check_milestones(snapshot),
            )

            return snapshot

        except Exception as e:
            logger.error("Error capturing state snapshot: %s", e)
            raise

    async def _save_snapshot(self, snapshot: StateSnapshot):
        """Save snapshot to database using asyncio.to_thread()."""
        try:
            timestamp_iso = snapshot.timestamp.isoformat()
            phase_states_json = json.dumps(snapshot.phase_states)
            capabilities_json = json.dumps(list(snapshot.active_capabilities))
            metrics_json = json.dumps(
                {k.value: v for k, v in snapshot.system_metrics.items()}
            )
            config_json = json.dumps(snapshot.configuration)
            validation_json = json.dumps(snapshot.validation_results)
            metadata_json = json.dumps(snapshot.metadata)

            metrics_list = [
                (metric.value, timestamp_iso, value)
                for metric, value in snapshot.system_metrics.items()
            ]

            await asyncio.to_thread(
                save_snapshot_sync,
                self.db_path,
                timestamp_iso,
                phase_states_json,
                capabilities_json,
                metrics_json,
                config_json,
                validation_json,
                metadata_json,
                metrics_list,
            )

        except Exception as e:
            logger.error("Error saving snapshot: %s", e)

    async def record_state_change(
        self,
        change_type: StateChangeType,
        description: str,
        after_state: Dict[str, Any],
        before_state: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record a state change event using asyncio.to_thread()."""
        change = StateChange(
            timestamp=datetime.now(),
            change_type=change_type,
            before_state=before_state,
            after_state=after_state,
            description=description,
            user_id=user_id,
            metadata=metadata or {},
        )

        self.change_log.append(change)

        try:
            before_state_json = (
                json.dumps(change.before_state) if change.before_state else None
            )

            await asyncio.to_thread(
                record_state_change_sync,
                self.db_path,
                change.timestamp.isoformat(),
                change.change_type.value,
                before_state_json,
                json.dumps(change.after_state),
                change.description,
                change.user_id,
                json.dumps(change.metadata),
            )

        except Exception as e:
            logger.error("Error recording state change: %s", e)

        # Trigger snapshot if significant change
        if change_type in SIGNIFICANT_CHANGES:
            await self.capture_state_snapshot()

    async def _check_milestones(self, snapshot: StateSnapshot):
        """Check if any milestones have been achieved."""
        for milestone_name, milestone in self.milestones.items():
            if milestone.achieved:
                continue

            criteria_met, evidence = evaluate_milestone_criteria(milestone, snapshot)

            if criteria_met:
                await self._mark_milestone_achieved(milestone_name, milestone, evidence)

    async def _mark_milestone_achieved(
        self, milestone_name: str, milestone: ProjectMilestone, evidence: List[str]
    ):
        """Mark a milestone as achieved and record the event."""
        milestone.achieved = True
        milestone.achieved_at = datetime.now()
        milestone.evidence = evidence

        await asyncio.gather(
            self.record_state_change(
                StateChangeType.MILESTONE_REACHED,
                f"Milestone achieved: {milestone.name}",
                {"milestone": milestone_name, "evidence": evidence},
                metadata={"milestone_description": milestone.description},
            ),
            self._save_milestone(milestone_name, milestone),
        )

        logger.info("🎉 Milestone achieved: %s", milestone.name)

    async def _save_milestone(self, name: str, milestone: ProjectMilestone):
        """Save milestone to database using asyncio.to_thread()."""
        try:
            await asyncio.to_thread(
                save_milestone_sync,
                self.db_path,
                name,
                milestone.description,
                json.dumps(milestone.criteria),
                milestone.achieved,
                milestone.achieved_at.isoformat() if milestone.achieved_at else None,
                json.dumps(milestone.evidence),
                datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error("Error saving milestone: %s", e)

    async def track_error(
        self, error: Exception, context: Optional[Dict[str, Any]] = None
    ):
        """Track an error occurrence for error rate calculation (thread-safe)."""
        try:
            async with self._counter_lock:
                self._error_count += 1

            await track_error_to_redis(self.redis_client, error, context)

            await self.record_state_change(
                StateChangeType.ERROR_OCCURRED,
                f"Error tracked: {type(error).__name__}: {str(error)[:100]}",
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "context": context or {},
                    "timestamp": datetime.now().isoformat(),
                },
                metadata={
                    "severity": "error",
                    "tracking_source": "enhanced_state_tracker",
                },
            )

            logger.debug("Error tracked: %s", type(error).__name__)

        except Exception as e:
            logger.error("Failed to track error: %s", e)

    async def track_api_call(
        self, endpoint: str, method: str = "GET", response_status: Optional[int] = None
    ):
        """Track an API call for metrics (thread-safe)."""
        try:
            async with self._counter_lock:
                self._api_call_count += 1

            await track_api_call_to_redis(
                self.redis_client, endpoint, method, response_status
            )

            logger.debug(
                "API call tracked: %s %s -> %s", method, endpoint, response_status
            )

        except Exception as e:
            logger.error("Failed to track API call: %s", e)

    async def track_user_interaction(
        self,
        interaction_type: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Track a user interaction for metrics (thread-safe)."""
        try:
            async with self._counter_lock:
                self._user_interaction_count += 1

            await track_user_interaction_to_redis(
                self.redis_client, interaction_type, user_id, context
            )

            if interaction_type in SIGNIFICANT_INTERACTIONS:
                await self.record_state_change(
                    StateChangeType.USER_ACTION,
                    f"User interaction: {interaction_type}",
                    {
                        "interaction_type": interaction_type,
                        "user_id": user_id,
                        "context": context or {},
                        "timestamp": datetime.now().isoformat(),
                    },
                    user_id=user_id,
                    metadata={"tracking_source": "enhanced_state_tracker"},
                )

            logger.debug(
                "User interaction tracked: %s by %s", interaction_type, user_id
            )

        except Exception as e:
            logger.error("Failed to track user interaction: %s", e)

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of tracked metrics."""
        return await get_metrics_summary(
            self.redis_client,
            self._error_count,
            self._api_call_count,
            self._user_interaction_count,
            self.error_boundary_manager,
        )

    def _start_background_tracking(self):
        """Start background tracking tasks."""

        async def tracking_loop():
            """Capture state snapshots hourly in background."""
            while True:
                try:
                    await asyncio.sleep(TimingConstants.HOURLY_INTERVAL)
                    await self.capture_state_snapshot()
                except Exception as e:
                    logger.error("Error in background tracking: %s", e)

        asyncio.create_task(tracking_loop())

    async def get_state_summary(self) -> Dict[str, Any]:
        """Get comprehensive state summary."""
        latest_snapshot = self.state_history[-1] if self.state_history else None

        if not latest_snapshot:
            latest_snapshot = await self.capture_state_snapshot()

        recent_changes = self.change_log[-10:] if self.change_log else []

        milestone_status = {
            name: {
                "achieved": milestone.achieved,
                "achieved_at": (
                    milestone.achieved_at.isoformat() if milestone.achieved_at else None
                ),
                "description": milestone.description,
            }
            for name, milestone in self.milestones.items()
        }

        trends = calculate_trends(self.state_history)

        return {
            "timestamp": datetime.now().isoformat(),
            "current_state": {
                "phase_states": latest_snapshot.phase_states,
                "active_capabilities": list(latest_snapshot.active_capabilities),
                "system_metrics": {
                    k.value: v for k, v in latest_snapshot.system_metrics.items()
                },
                "validation_results": latest_snapshot.validation_results,
            },
            "recent_changes": [
                {
                    "timestamp": change.timestamp.isoformat(),
                    "type": change.change_type.value,
                    "description": change.description,
                    "user_id": change.user_id,
                }
                for change in recent_changes
            ],
            "milestones": milestone_status,
            "trends": trends,
            "snapshot_count": len(self.state_history),
            "change_count": len(self.change_log),
            "tracking_metrics": await self.get_metrics_summary(),
        }

    async def generate_state_report(self) -> str:
        """Generate comprehensive state tracking report."""
        from .reports import generate_state_report_from_summary

        summary = await self.get_state_summary()
        return generate_state_report_from_summary(summary)

    async def export_state_data(self, output_path: str, format: str = "json"):
        """Export state tracking data."""
        summary = await self.get_state_summary()
        await export_state_data_to_file(
            summary,
            output_path,
            format,
            report_generator=self.generate_state_report
            if format == "markdown"
            else None,
        )


# Global instance (thread-safe)
_state_tracker = None
_state_tracker_lock = threading.Lock()


def get_state_tracker() -> EnhancedProjectStateTracker:
    """Get singleton instance of state tracker (thread-safe)."""
    global _state_tracker
    if _state_tracker is None:
        with _state_tracker_lock:
            if _state_tracker is None:
                _state_tracker = EnhancedProjectStateTracker()
    return _state_tracker
