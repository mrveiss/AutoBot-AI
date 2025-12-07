#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Project State Tracking System
Provides comprehensive tracking of project state, phase progression, capabilities, and system evolution
"""

import asyncio
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import aiofiles

from scripts.phase_validation_system import PhaseValidator
from src.phase_progression_manager import get_progression_manager
from src.project_state_manager import ProjectStateManager
from src.utils.redis_client import get_redis_client

try:
    from src.utils.error_boundaries import get_error_boundary_manager
except ImportError:

    def get_error_boundary_manager():
        """Return None when error_boundaries module is unavailable."""
        return None


logger = logging.getLogger(__name__)


class StateChangeType(Enum):
    """Types of state changes in the system"""

    PHASE_PROGRESSION = "phase_progression"
    CAPABILITY_UNLOCK = "capability_unlock"
    VALIDATION_UPDATE = "validation_update"
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_EVENT = "system_event"
    USER_ACTION = "user_action"
    ERROR_OCCURRED = "error_occurred"
    MILESTONE_REACHED = "milestone_reached"


class TrackingMetric(Enum):
    """Metrics to track for system evolution"""

    PHASE_COMPLETION = "phase_completion"
    CAPABILITY_COUNT = "capability_count"
    VALIDATION_SCORE = "validation_score"
    ERROR_RATE = "error_rate"
    PROGRESSION_VELOCITY = "progression_velocity"
    SYSTEM_MATURITY = "system_maturity"
    USER_INTERACTIONS = "user_interactions"
    API_CALLS = "api_calls"


@dataclass
class StateSnapshot:
    """A snapshot of system state at a point in time"""

    timestamp: datetime
    phase_states: Dict[str, Dict[str, Any]]
    active_capabilities: Set[str]
    system_metrics: Dict[TrackingMetric, float]
    configuration: Dict[str, Any]
    validation_results: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateChange:
    """Records a change in system state"""

    timestamp: datetime
    change_type: StateChangeType
    before_state: Optional[Dict[str, Any]]
    after_state: Dict[str, Any]
    description: str
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectMilestone:
    """Represents a significant project milestone"""

    name: str
    description: str
    criteria: Dict[str, Any]
    achieved: bool = False
    achieved_at: Optional[datetime] = None
    evidence: List[str] = field(default_factory=list)


# O(1) lookup optimization constants (Issue #326)
SIGNIFICANT_CHANGES = {StateChangeType.PHASE_PROGRESSION, StateChangeType.CAPABILITY_UNLOCK}
SIGNIFICANT_INTERACTIONS = {"login", "logout", "settings_change", "agent_switch"}


class EnhancedProjectStateTracker:
    """Enhanced tracking system for comprehensive project state management"""

    def __init__(self, db_path: str = "data/project_state_tracking.db"):
        self.db_path = db_path
        self.project_root = Path(__file__).parent.parent

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
        self._counter_lock = asyncio.Lock()  # Lock for thread-safe counter access

        # Metric keys for Redis
        self.REDIS_KEYS = {
            "error_count": "autobot:metrics:error_count",
            "api_calls": "autobot:metrics:api_calls",
            "user_interactions": "autobot:metrics:user_interactions",
            "error_rate": "autobot:metrics:error_rate",
        }

        # Initialize database and load state
        self._init_database()
        self._define_milestones()
        self._load_state()

        # Start background tracking
        self._start_background_tracking()

        logger.info("Enhanced Project State Tracker initialized")

    def _init_database(self):
        """Initialize SQLite database for enhanced state tracking"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # State snapshots table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    phase_states TEXT NOT NULL,
                    active_capabilities TEXT NOT NULL,
                    system_metrics TEXT NOT NULL,
                    configuration TEXT NOT NULL,
                    validation_results TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # State changes table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS state_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    change_type TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT NOT NULL,
                    description TEXT NOT NULL,
                    user_id TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Metrics history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    value REAL NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indices separately
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_metric_timestamp
                ON metrics_history (metric_name, timestamp)
            """
            )

            # Milestones table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS milestones (
                    name TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    criteria TEXT NOT NULL,
                    achieved BOOLEAN DEFAULT FALSE,
                    achieved_at TIMESTAMP,
                    evidence TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Events table for detailed tracking
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    source TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indices separately
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_event_type
                ON system_events (event_type)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON system_events (timestamp)
            """
            )

            conn.commit()

    def _define_milestones(self):
        """Define project milestones to track"""
        self.milestones = {
            "first_phase_complete": ProjectMilestone(
                "First Phase Complete",
                "Complete the first development phase",
                {"phases_completed": 1},
            ),
            "half_way_there": ProjectMilestone(
                "Halfway There",
                "Reach 50% overall system maturity",
                {"system_maturity": 50.0},
            ),
            "core_system_ready": ProjectMilestone(
                "Core System Ready", "Complete first 5 phases", {"phases_completed": 5}
            ),
            "advanced_features_unlocked": ProjectMilestone(
                "Advanced Features Unlocked",
                "Unlock advanced AI capabilities",
                {
                    "capabilities_unlocked": [
                        "multimodal_ai",
                        "code_search",
                        "intelligent_agents",
                    ]
                },
            ),
            "production_ready": ProjectMilestone(
                "Production Ready",
                "System ready for production deployment",
                {"phases_completed": 10, "system_maturity": 95.0},
            ),
            "fully_autonomous": ProjectMilestone(
                "Fully Autonomous",
                "System can self-manage and evolve",
                {
                    "capabilities_unlocked": [
                        "self_improvement",
                        "auto_documentation",
                        "error_recovery",
                    ]
                },
            ),
        }

    def _load_state(self):
        """Load state from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                self._load_snapshots_from_db(cursor)
                self._load_milestones_from_db(cursor)
                logger.info(f"Loaded {len(self.state_history)} state snapshots")
        except Exception as e:
            logger.error(f"Error loading state: {e}")

    def _load_snapshots_from_db(self, cursor):  # (Issue #315 - extracted)
        """Load recent snapshots from database cursor"""
        cursor.execute(
            """
            SELECT timestamp, phase_states, active_capabilities,
                   system_metrics, configuration, validation_results, metadata
            FROM state_snapshots
            ORDER BY timestamp DESC
            LIMIT 100
        """
        )

        for row in cursor.fetchall():
            snapshot = StateSnapshot(
                timestamp=datetime.fromisoformat(row[0]),
                phase_states=json.loads(row[1]),
                active_capabilities=set(json.loads(row[2])),
                system_metrics={
                    TrackingMetric(k): v for k, v in json.loads(row[3]).items()
                },
                configuration=json.loads(row[4]),
                validation_results=json.loads(row[5]),
                metadata=json.loads(row[6]) if row[6] else {},
            )
            self.state_history.append(snapshot)

    def _load_milestones_from_db(self, cursor):  # (Issue #315 - extracted)
        """Load milestones from database cursor"""
        cursor.execute("SELECT * FROM milestones")
        for row in cursor.fetchall():
            self._update_milestone_from_row(row)

    def _update_milestone_from_row(self, row):  # (Issue #315 - extracted)
        """Update milestone from database row"""
        name = row[0]
        if name not in self.milestones:
            return

        self.milestones[name].achieved = bool(row[3])
        if row[4]:
            self.milestones[name].achieved_at = datetime.fromisoformat(row[4])
        if row[5]:
            self.milestones[name].evidence = json.loads(row[5])

    async def capture_state_snapshot(self) -> StateSnapshot:
        """Capture current system state"""
        try:
            # Get phase validation results
            validation_results = await self.validator.validate_all_phases()

            # Get current capabilities
            capabilities = self.progression_manager.get_current_system_capabilities()

            # Get phase states
            phase_states = {}
            for phase_name, phase_data in validation_results["phases"].items():
                phase_states[phase_name] = {
                    "completion_percentage": phase_data["completion_percentage"],
                    "status": phase_data["status"],
                    "missing_items": phase_data.get("missing_items", []),
                }

            # Calculate metrics
            metrics = {
                TrackingMetric.PHASE_COMPLETION: len(
                    [
                        p
                        for p in phase_states.values()
                        if p["completion_percentage"] >= 95.0
                    ]
                ),
                TrackingMetric.CAPABILITY_COUNT: len(
                    capabilities["active_capabilities"]
                ),
                TrackingMetric.VALIDATION_SCORE: validation_results[
                    "overall_assessment"
                ]["system_maturity_score"],
                TrackingMetric.SYSTEM_MATURITY: capabilities["system_maturity"],
                TrackingMetric.ERROR_RATE: await self._get_error_rate(),
                TrackingMetric.PROGRESSION_VELOCITY: (
                    self._calculate_progression_velocity()
                ),
                TrackingMetric.USER_INTERACTIONS: (
                    await self._get_user_interactions_count()
                ),
                TrackingMetric.API_CALLS: await self._get_api_calls_count(),
            }

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
            if len(self.state_history) > 1000:  # Keep last 1000 snapshots
                self.state_history = self.state_history[-1000:]

            # Save to database
            await self._save_snapshot(snapshot)

            # Check milestones
            await self._check_milestones(snapshot)

            return snapshot

        except Exception as e:
            logger.error(f"Error capturing state snapshot: {e}")
            raise

    async def _save_snapshot(self, snapshot: StateSnapshot):
        """Save snapshot to database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO state_snapshots
                    (timestamp, phase_states, active_capabilities, system_metrics,
                     configuration, validation_results, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        snapshot.timestamp.isoformat(),
                        json.dumps(snapshot.phase_states),
                        json.dumps(list(snapshot.active_capabilities)),
                        json.dumps(
                            {k.value: v for k, v in snapshot.system_metrics.items()}
                        ),
                        json.dumps(snapshot.configuration),
                        json.dumps(snapshot.validation_results),
                        json.dumps(snapshot.metadata),
                    ),
                )

                # Also save metrics to history
                for metric, value in snapshot.system_metrics.items():
                    cursor.execute(
                        """
                        INSERT INTO metrics_history (metric_name, timestamp, value)
                        VALUES (?, ?, ?)
                    """,
                        (metric.value, snapshot.timestamp.isoformat(), value),
                    )

                conn.commit()

        except Exception as e:
            logger.error(f"Error saving snapshot: {e}")

    async def record_state_change(
        self,
        change_type: StateChangeType,
        description: str,
        after_state: Dict[str, Any],
        before_state: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record a state change event"""
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

        # Save to database
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO state_changes
                    (timestamp, change_type, before_state, after_state,
                     description, user_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        change.timestamp.isoformat(),
                        change.change_type.value,
                        (
                            json.dumps(change.before_state)
                            if change.before_state
                            else None
                        ),
                        json.dumps(change.after_state),
                        change.description,
                        change.user_id,
                        json.dumps(change.metadata),
                    ),
                )

                conn.commit()

        except Exception as e:
            logger.error(f"Error recording state change: {e}")

        # Trigger snapshot if significant change
        if change_type in SIGNIFICANT_CHANGES:  # O(1) lookup (Issue #326)
            await self.capture_state_snapshot()

    async def _check_milestones(self, snapshot: StateSnapshot):
        """Check if any milestones have been achieved"""
        for milestone_name, milestone in self.milestones.items():
            if milestone.achieved:
                continue

            criteria_met, evidence = self._evaluate_milestone_criteria(
                milestone, snapshot
            )

            if criteria_met:
                await self._mark_milestone_achieved(milestone_name, milestone, evidence)

    def _evaluate_milestone_criteria(
        self, milestone: ProjectMilestone, snapshot: StateSnapshot
    ) -> Tuple[bool, List[str]]:  # (Issue #315 - extracted)
        """Evaluate if milestone criteria are met and collect evidence"""
        criteria_met = True
        evidence = []

        for criterion, target in milestone.criteria.items():
            met, criterion_evidence = self._check_single_criterion(
                criterion, target, snapshot
            )
            if met:
                evidence.append(criterion_evidence)
            else:
                criteria_met = False

        return criteria_met, evidence

    def _check_single_criterion(
        self, criterion: str, target: Any, snapshot: StateSnapshot
    ) -> Tuple[bool, str]:  # (Issue #315 - extracted)
        """Check a single milestone criterion"""
        if criterion == "phases_completed":
            actual = snapshot.system_metrics[TrackingMetric.PHASE_COMPLETION]
            if actual >= target:
                return True, f"Completed {actual} phases (target: {target})"
            return False, ""

        if criterion == "system_maturity":
            actual = snapshot.system_metrics[TrackingMetric.SYSTEM_MATURITY]
            if actual >= target:
                return True, f"System maturity: {actual}% (target: {target}%)"
            return False, ""

        if criterion == "capabilities_unlocked":
            required_capabilities = set(target)
            if required_capabilities.issubset(snapshot.active_capabilities):
                return (
                    True,
                    f"Unlocked capabilities: {', '.join(required_capabilities)}",
                )
            return False, ""

        return False, ""

    async def _mark_milestone_achieved(
        self, milestone_name: str, milestone: ProjectMilestone, evidence: List[str]
    ):  # (Issue #315 - extracted)
        """Mark a milestone as achieved and record the event"""
        milestone.achieved = True
        milestone.achieved_at = datetime.now()
        milestone.evidence = evidence

        # Record milestone achievement
        await self.record_state_change(
            StateChangeType.MILESTONE_REACHED,
            f"Milestone achieved: {milestone.name}",
            {"milestone": milestone_name, "evidence": evidence},
            metadata={"milestone_description": milestone.description},
        )

        # Save to database
        self._save_milestone(milestone_name, milestone)

        logger.info(f"🎉 Milestone achieved: {milestone.name}")

    def _save_milestone(self, name: str, milestone: ProjectMilestone):
        """Save milestone to database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO milestones
                    (name, description, criteria, achieved, achieved_at, evidence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        name,
                        milestone.description,
                        json.dumps(milestone.criteria),
                        milestone.achieved,
                        (
                            milestone.achieved_at.isoformat()
                            if milestone.achieved_at
                            else None
                        ),
                        json.dumps(milestone.evidence),
                        datetime.now().isoformat(),
                    ),
                )

                conn.commit()

        except Exception as e:
            logger.error(f"Error saving milestone: {e}")

    def _calculate_progression_velocity(self) -> float:
        """Calculate rate of phase progression"""
        if len(self.state_history) < 2:
            return 0.0

        # Look at last 7 days of data
        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_snapshots = [
            s for s in self.state_history if s.timestamp >= seven_days_ago
        ]

        if len(recent_snapshots) < 2:
            return 0.0

        # Calculate change in phase completion
        first_completion = recent_snapshots[0].system_metrics.get(
            TrackingMetric.PHASE_COMPLETION, 0
        )
        last_completion = recent_snapshots[-1].system_metrics.get(
            TrackingMetric.PHASE_COMPLETION, 0
        )

        days_elapsed = (
            recent_snapshots[-1].timestamp - recent_snapshots[0].timestamp
        ).days or 1

        return (last_completion - first_completion) / days_elapsed

    async def _get_error_rate(self) -> float:
        """Calculate current error rate based on recent error data"""
        try:
            if not self.redis_client:
                return 0.0

            # Get error count from current hour
            current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)

            error_key = f"{self.REDIS_KEYS['error_count']}:{current_hour.timestamp()}"
            error_count = await self._get_redis_metric(error_key, 0)

            # Get total API calls from last hour for rate calculation
            api_key = f"{self.REDIS_KEYS['api_calls']}:{current_hour.timestamp()}"
            api_calls = await self._get_redis_metric(
                api_key, 1
            )  # Avoid division by zero

            # Calculate error rate as percentage
            error_rate = (error_count / api_calls) * 100 if api_calls > 0 else 0.0

            return round(error_rate, 2)

        except Exception as e:
            logger.warning(f"Error calculating error rate: {e}")
            return 0.0

    async def _get_user_interactions_count(self) -> int:
        """Get current user interactions count"""
        try:
            if not self.redis_client:
                return self._user_interaction_count

            # Get user interactions from last 24 hours
            total_interactions = 0
            now = datetime.now()

            for i in range(24):  # Last 24 hours
                hour = now - timedelta(hours=i)
                hour_key = hour.replace(minute=0, second=0, microsecond=0)
                key = f"{self.REDIS_KEYS['user_interactions']}:{hour_key.timestamp()}"
                interactions = await self._get_redis_metric(key, 0)
                total_interactions += interactions

            return total_interactions

        except Exception as e:
            logger.warning(f"Error getting user interactions count: {e}")
            return self._user_interaction_count

    async def _get_api_calls_count(self) -> int:
        """Get current API calls count"""
        try:
            if not self.redis_client:
                return self._api_call_count

            # Get API calls from last 24 hours
            total_calls = 0
            now = datetime.now()

            for i in range(24):  # Last 24 hours
                hour = now - timedelta(hours=i)
                hour_key = hour.replace(minute=0, second=0, microsecond=0)
                key = f"{self.REDIS_KEYS['api_calls']}:{hour_key.timestamp()}"
                calls = await self._get_redis_metric(key, 0)
                total_calls += calls

            return total_calls

        except Exception as e:
            logger.warning(f"Error getting API calls count: {e}")
            return self._api_call_count

    async def _get_redis_metric(self, key: str, default: int = 0) -> int:
        """Helper to get metric from Redis with fallback"""
        try:
            if not self.redis_client:
                return default

            value = await self.redis_client.get(key)
            return int(value) if value else default

        except Exception as e:
            logger.debug(f"Redis metric fetch failed for {key}: {e}")
            return default

    async def track_error(
        self, error: Exception, context: Optional[Dict[str, Any]] = None
    ):
        """Track an error occurrence for error rate calculation (thread-safe)"""
        try:
            async with self._counter_lock:
                self._error_count += 1

            # Store in Redis for hourly aggregation
            if self.redis_client:
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                error_key = (
                    f"{self.REDIS_KEYS['error_count']}:{current_hour.timestamp()}"
                )

                # Increment error count for this hour
                await self.redis_client.incr(error_key)
                await self.redis_client.expire(
                    error_key, 86400
                )  # Expire after 24 hours

            # Record state change
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

            logger.debug(f"Error tracked: {type(error).__name__}")

        except Exception as e:
            logger.error(f"Failed to track error: {e}")

    async def track_api_call(
        self, endpoint: str, method: str = "GET", response_status: Optional[int] = None
    ):
        """Track an API call for metrics (thread-safe)"""
        try:
            async with self._counter_lock:
                self._api_call_count += 1

            # Store in Redis for hourly aggregation
            if self.redis_client:
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                api_key = f"{self.REDIS_KEYS['api_calls']}:{current_hour.timestamp()}"

                # Increment API call count for this hour
                await self.redis_client.incr(api_key)
                await self.redis_client.expire(api_key, 86400)  # Expire after 24 hours

                # Track specific endpoint stats
                endpoint_key = f"autobot:metrics:endpoints:{endpoint}:calls"
                await self.redis_client.incr(endpoint_key)
                await self.redis_client.expire(endpoint_key, 86400)

            logger.debug(f"API call tracked: {method} {endpoint} -> {response_status}")

        except Exception as e:
            logger.error(f"Failed to track API call: {e}")

    async def track_user_interaction(
        self,
        interaction_type: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Track a user interaction for metrics (thread-safe)"""
        try:
            async with self._counter_lock:
                self._user_interaction_count += 1

            # Store in Redis for hourly aggregation
            if self.redis_client:
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                interaction_key = (
                    f"{self.REDIS_KEYS['user_interactions']}:{current_hour.timestamp()}"
                )

                # Increment user interaction count for this hour
                await self.redis_client.incr(interaction_key)
                await self.redis_client.expire(
                    interaction_key, 86400
                )  # Expire after 24 hours

                # Track interaction types
                type_key = f"autobot:metrics:interaction_types:{interaction_type}:count"
                await self.redis_client.incr(type_key)
                await self.redis_client.expire(type_key, 86400)

            # Record state change for significant interactions
            if interaction_type in SIGNIFICANT_INTERACTIONS:  # O(1) lookup (Issue #326)
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

            logger.debug(f"User interaction tracked: {interaction_type} by {user_id}")

        except Exception as e:
            logger.error(f"Failed to track user interaction: {e}")

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of tracked metrics"""
        try:
            return {
                "error_tracking": {
                    "current_error_rate": await self._get_error_rate(),
                    "total_errors_tracked": self._error_count,
                    "last_update": datetime.now().isoformat(),
                },
                "api_tracking": {
                    "total_api_calls_24h": await self._get_api_calls_count(),
                    "current_session_calls": self._api_call_count,
                    "last_update": datetime.now().isoformat(),
                },
                "user_interactions": {
                    "total_interactions_24h": await self._get_user_interactions_count(),
                    "current_session_interactions": self._user_interaction_count,
                    "last_update": datetime.now().isoformat(),
                },
                "system_health": {
                    "redis_connected": self.redis_client is not None,
                    "error_boundary_available": self.error_boundary_manager is not None,
                    "tracking_active": True,
                },
            }
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return {"error": str(e)}

    def _start_background_tracking(self):
        """Start background tracking tasks"""

        async def tracking_loop():
            """Capture state snapshots hourly in background."""
            while True:
                try:
                    # Capture snapshot every hour
                    await asyncio.sleep(3600)
                    await self.capture_state_snapshot()
                except Exception as e:
                    logger.error(f"Error in background tracking: {e}")

        # Start in background (non-blocking)
        asyncio.create_task(tracking_loop())

    async def get_state_summary(self) -> Dict[str, Any]:
        """Get comprehensive state summary"""
        latest_snapshot = self.state_history[-1] if self.state_history else None

        if not latest_snapshot:
            # Capture a new snapshot if none exists
            latest_snapshot = await self.capture_state_snapshot()

        # Get recent changes
        recent_changes = self.change_log[-10:] if self.change_log else []

        # Get milestone status
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

        # Get trend data
        trends = {}
        for metric in TrackingMetric:
            recent_values = [
                (s.timestamp, s.system_metrics.get(metric, 0))
                for s in self.state_history[-30:]
                if metric in s.system_metrics
            ]
            if len(recent_values) >= 2:
                # Simple trend calculation
                first_value = recent_values[0][1]
                last_value = recent_values[-1][1]
                trend = (
                    "increasing"
                    if last_value > first_value
                    else "decreasing" if last_value < first_value else "stable"
                )
                trends[metric.value] = {
                    "current": last_value,
                    "trend": trend,
                    "change": last_value - first_value,
                }

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
        """Generate comprehensive state tracking report"""
        summary = await self.get_state_summary()

        report = []
        report.append("# AutoBot Enhanced State Tracking Report")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Current State
        report.append("## Current System State")
        current = summary["current_state"]
        metrics = current["system_metrics"]

        report.append(
            f"- **System Maturity**: {metrics.get('system_maturity', 0):.1f}%"
        )
        report.append(
            f"- **Phases Completed**: {metrics.get('phase_completion', 0)}/10"
        )
        report.append(
            f"- **Active Capabilities**: {metrics.get('capability_count', 0)}"
        )
        report.append(
            f"- **Validation Score**: {metrics.get('validation_score', 0):.1f}%"
        )
        report.append("")

        # Milestones
        report.append("## Milestones")
        for name, status in summary["milestones"].items():
            icon = "✅" if status["achieved"] else "⏳"
            report.append(f"- {icon} **{name}**: {status['description']}")
            if status["achieved"]:
                report.append(f"  - Achieved: {status['achieved_at']}")
        report.append("")

        # Trends
        report.append("## System Trends")
        for metric_name, trend_data in summary["trends"].items():
            report.append(f"- **{metric_name.replace('_', ' ').title()}**:")
            report.append(f"  - Current: {trend_data['current']:.2f}")
            report.append(f"  - Trend: {trend_data['trend']}")
            report.append(f"  - Change: {trend_data['change']:+.2f}")
        report.append("")

        # Recent Changes
        report.append("## Recent Changes")
        for change in summary["recent_changes"][-5:]:
            report.append(
                f"- {change['timestamp']}: {change['description']} ({change['type']})"
            )
        report.append("")

        # Tracking Metrics
        report.append("## System Tracking Metrics")
        tracking_metrics = summary.get("tracking_metrics", {})

        if "error_tracking" in tracking_metrics:
            error_data = tracking_metrics["error_tracking"]
            report.append(
                f"- **Error Rate**: {error_data.get('current_error_rate', 0)}%"
            )
            report.append(
                f"- **Total Errors**: {error_data.get('total_errors_tracked', 0)}"
            )

        if "api_tracking" in tracking_metrics:
            api_data = tracking_metrics["api_tracking"]
            report.append(
                f"- **API Calls (24h)**: {api_data.get('total_api_calls_24h', 0)}"
            )
            report.append(
                f"- **Session API Calls**: {api_data.get('current_session_calls', 0)}"
            )

        if "user_interactions" in tracking_metrics:
            interaction_data = tracking_metrics["user_interactions"]
            report.append(
                f"- **User Interactions (24h)**: {interaction_data.get('total_interactions_24h', 0)}"
            )
            report.append(
                f"- **Session Interactions**: {interaction_data.get('current_session_interactions', 0)}"
            )

        if "system_health" in tracking_metrics:
            health_data = tracking_metrics["system_health"]
            redis_status = (
                "✅ Connected"
                if health_data.get("redis_connected")
                else "❌ Disconnected"
            )
            report.append(f"- **Redis Status**: {redis_status}")

        report.append("")

        # Phase Details
        report.append("## Phase Status")
        for phase_name, phase_data in current["phase_states"].items():
            status_icon = (
                "✅"
                if phase_data["completion_percentage"] >= 95
                else "🔄" if phase_data["completion_percentage"] >= 50 else "⏳"
            )
            report.append(
                f"- {status_icon} **{phase_name}**: {phase_data['completion_percentage']:.1f}% ({phase_data['status']})"
            )

        return "\n".join(report)

    async def export_state_data(self, output_path: str, format: str = "json"):
        """Export state tracking data"""
        summary = await self.get_state_summary()

        # Ensure output goes to data directory
        if not output_path.startswith("data/"):
            output_path = f"data/reports/state_tracking/{Path(output_path).name}"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            if format == "json":
                async with aiofiles.open(
                    output_file, "w", encoding="utf-8"
                ) as f:
                    await f.write(json.dumps(summary, indent=2, default=str))
            elif format == "markdown":
                report = await self.generate_state_report()
                async with aiofiles.open(
                    output_file, "w", encoding="utf-8"
                ) as f:
                    await f.write(report)
            else:
                raise ValueError(f"Unsupported format: {format}")

            logger.info(f"State data exported to {output_file}")
        except OSError as e:
            logger.error(f"Failed to export state data to {output_file}: {e}")
            raise


# Global instance (thread-safe)
import threading

_state_tracker = None
_state_tracker_lock = threading.Lock()


def get_state_tracker() -> EnhancedProjectStateTracker:
    """Get singleton instance of state tracker (thread-safe)."""
    global _state_tracker
    if _state_tracker is None:
        with _state_tracker_lock:
            # Double-check after acquiring lock
            if _state_tracker is None:
                _state_tracker = EnhancedProjectStateTracker()
    return _state_tracker


# Convenience functions for easy integration
async def track_system_error(
    error: Exception, context: Optional[Dict[str, Any]] = None
):
    """Convenience function to track system errors from anywhere in the codebase"""
    try:
        tracker = get_state_tracker()
        await tracker.track_error(error, context)
    except Exception as e:
        logger.error(f"Failed to track system error: {e}")


async def track_api_request(
    endpoint: str, method: str = "GET", status_code: Optional[int] = None
):
    """Convenience function to track API requests from middleware or endpoints"""
    try:
        tracker = get_state_tracker()
        await tracker.track_api_call(endpoint, method, status_code)
    except Exception as e:
        logger.error(f"Failed to track API request: {e}")


async def track_user_action(
    action_type: str,
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
):
    """Convenience function to track user actions from frontend or API"""
    try:
        tracker = get_state_tracker()
        await tracker.track_user_interaction(action_type, user_id, context)
    except Exception as e:
        logger.error(f"Failed to track user action: {e}")


def error_tracking_decorator(func):
    """Decorator to automatically track errors in functions"""
    import functools

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Async wrapper that tracks errors before re-raising."""
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await track_system_error(
                    e,
                    {
                        "function": func.__name__,
                        "module": func.__module__,
                        "args": str(args)[:200],  # Limit size
                        "kwargs": str(kwargs)[:200],
                    },
                )
                raise

        return async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Sync wrapper that tracks errors before re-raising."""
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _handle_sync_error_tracking(e, func, args, kwargs)  # (Issue #315 - extracted)
                raise

        return sync_wrapper


def _handle_sync_error_tracking(
    error: Exception, func, args, kwargs
):  # (Issue #315 - extracted)
    """Handle error tracking for sync functions"""
    error_context = {
        "function": func.__name__,
        "module": func.__module__,
        "args": str(args)[:200],
        "kwargs": str(kwargs)[:200],
    }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _schedule_error_tracking(error, error_context)
        else:
            _run_error_tracking(error, error_context)
    except Exception:
        logger.error(f"Error in {func.__name__}: {error}")


def _schedule_error_tracking(
    error: Exception, context: Dict[str, Any]
):  # (Issue #315 - extracted)
    """Schedule error tracking in running event loop"""
    asyncio.create_task(track_system_error(error, context))


def _run_error_tracking(
    error: Exception, context: Dict[str, Any]
):  # (Issue #315 - extracted)
    """Run error tracking in new event loop"""
    asyncio.run(track_system_error(error, context))


# Command handlers (Issue #315 - extracted)
async def _handle_snapshot_command(tracker):
    """Handle snapshot command"""
    print("Capturing state snapshot...")
    snapshot = await tracker.capture_state_snapshot()
    print(f"Snapshot captured at {snapshot.timestamp}")
    print(
        f"System maturity: {snapshot.system_metrics[TrackingMetric.SYSTEM_MATURITY]}%"
    )


async def _handle_summary_command(tracker):
    """Handle summary command"""
    summary = await tracker.get_state_summary()
    print(json.dumps(summary, indent=2, default=str))


async def _handle_report_command(tracker):
    """Handle report command"""
    report = await tracker.generate_state_report()
    print(report)


async def _handle_metrics_command(tracker):
    """Handle metrics command"""
    metrics = await tracker.get_metrics_summary()
    print(json.dumps(metrics, indent=2, default=str))


async def _handle_test_tracking_command(tracker):
    """Handle test-tracking command"""
    print("Testing tracking functionality...")

    # Test error tracking
    test_error = ValueError("Test error for tracking")
    await tracker.track_error(test_error, {"test": True})
    print("✅ Error tracking tested")

    # Test API call tracking
    await tracker.track_api_call("/api/test", "POST", 200)
    print("✅ API call tracking tested")

    # Test user interaction tracking
    await tracker.track_user_interaction(
        "test_interaction", "test_user", {"test": True}
    )
    print("✅ User interaction tracking tested")

    # Show updated metrics
    metrics = await tracker.get_metrics_summary()
    print("\nUpdated metrics:")
    print(json.dumps(metrics, indent=2, default=str))


async def _handle_export_command(tracker, args):
    """Handle export command"""
    output_path = (
        args[2] if len(args) > 2 else "reports/state_tracking_export.json"
    )
    await tracker.export_state_data(output_path)
    print(f"Data exported to {output_path}")


# Command dispatch map (Issue #315 - refactored)
COMMAND_HANDLERS = {
    "snapshot": _handle_snapshot_command,
    "summary": _handle_summary_command,
    "report": _handle_report_command,
    "metrics": _handle_metrics_command,
    "test-tracking": _handle_test_tracking_command,
}


# Example usage and testing
if __name__ == "__main__":
    import sys

    async def main():
        """Run state tracker CLI commands."""
        tracker = get_state_tracker()

        if len(sys.argv) <= 1:
            # Default: show summary
            await _handle_summary_command(tracker)
            return

        command = sys.argv[1]

        # Handle export separately (needs args)
        if command == "export":
            await _handle_export_command(tracker, sys.argv)
            return

        # Dispatch to handler
        handler = COMMAND_HANDLERS.get(command)
        if handler:
            await handler(tracker)
        else:
            print(f"Unknown command: {command}")
            print(
                "Available commands: snapshot, summary, report, metrics, test-tracking, export"
            )

    asyncio.run(main())
