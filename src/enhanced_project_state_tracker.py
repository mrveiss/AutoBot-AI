#!/usr/bin/env python3
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

from scripts.phase_validation_system import PhaseValidator
from src.phase_progression_manager import PhasePromotionStatus, get_progression_manager
from src.project_state_manager import ProjectStateManager
from src.utils.redis_client import get_redis_client

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

                # Load recent snapshots
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

                # Load milestones
                cursor.execute("SELECT * FROM milestones")
                for row in cursor.fetchall():
                    name = row[0]
                    if name in self.milestones:
                        self.milestones[name].achieved = bool(row[3])
                        if row[4]:
                            self.milestones[name].achieved_at = datetime.fromisoformat(
                                row[4]
                            )
                        if row[5]:
                            self.milestones[name].evidence = json.loads(row[5])

                logger.info(f"Loaded {len(self.state_history)} state snapshots")

        except Exception as e:
            logger.error(f"Error loading state: {e}")

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
                TrackingMetric.ERROR_RATE: 0.0,  # TODO: Implement error tracking
                TrackingMetric.PROGRESSION_VELOCITY: self._calculate_progression_velocity(),
                TrackingMetric.USER_INTERACTIONS: 0,  # TODO: Track user interactions
                TrackingMetric.API_CALLS: 0,  # TODO: Track API calls
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
                        json.dumps(change.before_state)
                        if change.before_state
                        else None,
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
        if change_type in [
            StateChangeType.PHASE_PROGRESSION,
            StateChangeType.CAPABILITY_UNLOCK,
        ]:
            await self.capture_state_snapshot()

    async def _check_milestones(self, snapshot: StateSnapshot):
        """Check if any milestones have been achieved"""
        for milestone_name, milestone in self.milestones.items():
            if milestone.achieved:
                continue

            # Check criteria
            criteria_met = True
            evidence = []

            for criterion, target in milestone.criteria.items():
                if criterion == "phases_completed":
                    actual = snapshot.system_metrics[TrackingMetric.PHASE_COMPLETION]
                    if actual >= target:
                        evidence.append(f"Completed {actual} phases (target: {target})")
                    else:
                        criteria_met = False

                elif criterion == "system_maturity":
                    actual = snapshot.system_metrics[TrackingMetric.SYSTEM_MATURITY]
                    if actual >= target:
                        evidence.append(
                            f"System maturity: {actual}% (target: {target}%)"
                        )
                    else:
                        criteria_met = False

                elif criterion == "capabilities_unlocked":
                    required_capabilities = set(target)
                    if required_capabilities.issubset(snapshot.active_capabilities):
                        evidence.append(
                            f"Unlocked capabilities: {', '.join(required_capabilities)}"
                        )
                    else:
                        criteria_met = False

            if criteria_met:
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
                        milestone.achieved_at.isoformat()
                        if milestone.achieved_at
                        else None,
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

    def _start_background_tracking(self):
        """Start background tracking tasks"""

        async def tracking_loop():
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
                "achieved_at": milestone.achieved_at.isoformat()
                if milestone.achieved_at
                else None,
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
                    else "decreasing"
                    if last_value < first_value
                    else "stable"
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

        # Phase Details
        report.append("## Phase Status")
        for phase_name, phase_data in current["phase_states"].items():
            status_icon = (
                "✅"
                if phase_data["completion_percentage"] >= 95
                else "🔄"
                if phase_data["completion_percentage"] >= 50
                else "⏳"
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

        if format == "json":
            with open(output_file, "w") as f:
                json.dump(summary, f, indent=2, default=str)
        elif format == "markdown":
            report = await self.generate_state_report()
            with open(output_file, "w") as f:
                f.write(report)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"State data exported to {output_file}")


# Global instance
_state_tracker = None


def get_state_tracker() -> EnhancedProjectStateTracker:
    """Get singleton instance of state tracker"""
    global _state_tracker
    if _state_tracker is None:
        _state_tracker = EnhancedProjectStateTracker()
    return _state_tracker


# Example usage and testing
if __name__ == "__main__":
    import sys

    async def main():
        tracker = get_state_tracker()

        if len(sys.argv) > 1:
            command = sys.argv[1]

            if command == "snapshot":
                print("Capturing state snapshot...")
                snapshot = await tracker.capture_state_snapshot()
                print(f"Snapshot captured at {snapshot.timestamp}")
                print(
                    f"System maturity: {snapshot.system_metrics[TrackingMetric.SYSTEM_MATURITY]}%"
                )

            elif command == "summary":
                summary = await tracker.get_state_summary()
                print(json.dumps(summary, indent=2, default=str))

            elif command == "report":
                report = await tracker.generate_state_report()
                print(report)

            elif command == "export":
                output_path = (
                    sys.argv[2]
                    if len(sys.argv) > 2
                    else "reports/state_tracking_export.json"
                )
                await tracker.export_state_data(output_path)
                print(f"Data exported to {output_path}")

            else:
                print(f"Unknown command: {command}")
                print("Available commands: snapshot, summary, report, export")
        else:
            # Default: show summary
            summary = await tracker.get_state_summary()
            print(json.dumps(summary, indent=2, default=str))

    asyncio.run(main())
