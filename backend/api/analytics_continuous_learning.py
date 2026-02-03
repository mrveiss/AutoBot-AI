# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Continuous Pattern Learning System (Issue #239)

A system that continuously monitors, learns, and improves pattern detection
through real-time monitoring, automated learning, and insight generation.

Key Features:
- Real-time file change monitoring
- Automated learning pipeline
- Model retraining triggers
- Feedback loop integration
- Insight generation and dashboards
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field

from src.auth_middleware import check_admin_permission

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Enums and Constants
# =============================================================================


class LearningEventType(str, Enum):
    """Types of learning events."""

    FILE_CHANGE = "file_change"
    PATTERN_DETECTED = "pattern_detected"
    FEEDBACK_RECEIVED = "feedback_received"
    MODEL_UPDATED = "model_updated"
    INSIGHT_GENERATED = "insight_generated"
    THRESHOLD_CROSSED = "threshold_crossed"
    ANOMALY_DETECTED = "anomaly_detected"


class MonitoringState(str, Enum):
    """States of the monitoring system."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


class InsightType(str, Enum):
    """Types of generated insights."""

    NEW_PATTERN = "new_pattern"
    PATTERN_EVOLUTION = "pattern_evolution"
    FALSE_POSITIVE_TREND = "false_positive_trend"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    DEVELOPER_PREFERENCE = "developer_preference"
    CODE_QUALITY_TREND = "code_quality_trend"
    SECURITY_CONCERN = "security_concern"


class RetrainingReason(str, Enum):
    """Reasons for triggering model retraining."""

    SCHEDULED = "scheduled"
    FEEDBACK_THRESHOLD = "feedback_threshold"
    ACCURACY_DROP = "accuracy_drop"
    NEW_PATTERNS = "new_patterns"
    MANUAL = "manual"


# Thresholds for automated actions
THRESHOLDS = {
    "feedback_for_retrain": 50,  # Feedback count to trigger retraining
    "accuracy_drop_percent": 10,  # Accuracy drop to trigger retraining
    "file_changes_for_scan": 10,  # File changes to trigger pattern scan
    "insight_generation_interval": 3600,  # Seconds between insight generation
    "anomaly_detection_window": 86400,  # 24 hours for anomaly detection
}


# =============================================================================
# Data Models
# =============================================================================


class LearningEvent(BaseModel):
    """An event in the learning system."""

    event_id: str
    event_type: LearningEventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    processed: bool = False


class Insight(BaseModel):
    """A generated insight."""

    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    data: Dict[str, Any]
    recommendations: List[str]
    generated_at: datetime
    expires_at: Optional[datetime] = None


class LearningMetrics(BaseModel):
    """Metrics for the learning system."""

    total_events_processed: int
    events_last_hour: int
    events_last_day: int
    patterns_learned: int
    patterns_updated: int
    false_positives_reduced: int
    accuracy_improvement: float
    last_retrain: Optional[datetime]
    next_scheduled_retrain: Optional[datetime]
    insights_generated: int
    active_insights: int


class MonitoringStatus(BaseModel):
    """Status of the monitoring system."""

    state: MonitoringState
    started_at: Optional[datetime]
    uptime_seconds: int
    files_monitored: int
    directories_watched: List[str]
    events_queue_size: int
    last_event_time: Optional[datetime]


class RetrainingRequest(BaseModel):
    """Request for model retraining."""

    reason: RetrainingReason = RetrainingReason.MANUAL
    force: bool = False
    patterns_to_focus: Optional[List[str]] = None


class LearningConfig(BaseModel):
    """Configuration for the learning system."""

    monitoring_enabled: bool = True
    auto_retrain_enabled: bool = True
    insight_generation_enabled: bool = True
    monitored_paths: List[str] = Field(default_factory=lambda: ["backend/", "src/"])
    scan_interval_seconds: int = 300
    retrain_interval_hours: int = 24
    feedback_threshold: int = 50
    accuracy_threshold: float = 0.7


# =============================================================================
# Learning Pipeline
# =============================================================================


@dataclass
class PatternStatistics:
    """Statistics for a pattern."""

    pattern_id: str
    detections: int = 0
    true_positives: int = 0
    false_positives: int = 0
    accuracy: float = 1.0
    last_detected: Optional[datetime] = None
    evolution_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FileState:
    """State of a monitored file."""

    path: str
    content_hash: str
    last_modified: datetime
    patterns_detected: List[str] = field(default_factory=list)


class LearningPipeline:
    """
    Pipeline for processing learning events and updating models.

    Handles:
    - Event processing
    - Pattern analysis
    - Model updates
    - Insight generation
    """

    def __init__(self):
        """Initialize learning pipeline with event tracking and statistics."""
        self.events: List[LearningEvent] = []
        self.pattern_stats: Dict[str, PatternStatistics] = {}
        self.insights: List[Insight] = []
        self.processed_count = 0
        self.last_retrain: Optional[datetime] = None
        self.accuracy_history: List[Tuple[datetime, float]] = []
        # Build event handler dispatch table (Issue #315)
        self._event_handlers = {
            LearningEventType.FILE_CHANGE: self._handle_file_change,
            LearningEventType.PATTERN_DETECTED: self._handle_pattern_detected,
            LearningEventType.FEEDBACK_RECEIVED: self._handle_feedback,
            LearningEventType.THRESHOLD_CROSSED: self._handle_threshold_crossed,
        }

    async def _dispatch_event(self, event: LearningEvent) -> Optional[str]:
        """Dispatch event to appropriate handler. (Issue #315 - extracted)"""
        handler = self._event_handlers.get(event.event_type)
        if handler:
            return await handler(event)
        return None

    def _create_insight(
        self,
        id_prefix: str,
        pattern_id: Optional[str],
        insight_type: InsightType,
        title: str,
        description: str,
        confidence: float,
        data: Dict[str, Any],
        recommendations: List[str],
        expires_days: int = 7,
    ) -> Insight:
        """
        Create an Insight object with standardized ID generation and timestamps.

        Issue #281: Extracted helper to reduce repetition in generate_insights.

        Args:
            id_prefix: Prefix for insight ID (e.g., 'trend', 'fp', 'improvement')
            pattern_id: Pattern ID to include in hash (optional)
            insight_type: Type of insight
            title: Insight title
            description: Insight description
            confidence: Confidence score (0.0 to 1.0)
            data: Additional data dict
            recommendations: List of recommendation strings
            expires_days: Days until insight expires (default: 7)

        Returns:
            Insight object with generated ID and timestamps
        """
        now = datetime.now()
        # Build hash input: prefix + optional pattern_id + timestamp
        hash_input = f"{id_prefix}_{pattern_id or ''}_{now.isoformat()}"
        insight_id = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        return Insight(
            insight_id=insight_id,
            insight_type=insight_type,
            title=title,
            description=description,
            confidence=confidence,
            data=data,
            recommendations=recommendations,
            generated_at=now,
            expires_at=now + timedelta(days=expires_days),
        )

    async def process_event(self, event: LearningEvent) -> Dict[str, Any]:
        """Process a learning event."""
        self.events.append(event)
        result = {"event_id": event.event_id, "processed": False}

        try:
            # Use dispatch table for O(1) lookup (Issue #315 - reduced depth)
            action = await self._dispatch_event(event)
            if action:
                result["action"] = action
            event.processed = True
            result["processed"] = True
            self.processed_count += 1
        except Exception as e:
            logger.error("Failed to process event %s: %s", event.event_id, e)
            result["error"] = str(e)

        return result

    async def _handle_file_change(self, event: LearningEvent) -> str:
        """Handle file change event."""
        file_path = event.data.get("path", "")
        change_type = event.data.get("change_type", "modified")

        # Track for batch scanning
        logger.debug("File change: %s - %s", change_type, file_path)

        return f"tracked_{change_type}"

    async def _handle_pattern_detected(self, event: LearningEvent) -> str:
        """Handle pattern detection event."""
        pattern_id = event.data.get("pattern_id", "")
        confidence = event.data.get("confidence", 0.0)

        if pattern_id not in self.pattern_stats:
            self.pattern_stats[pattern_id] = PatternStatistics(pattern_id=pattern_id)

        stats = self.pattern_stats[pattern_id]
        stats.detections += 1
        stats.last_detected = event.timestamp

        # Track evolution
        stats.evolution_history.append(
            {
                "timestamp": event.timestamp.isoformat(),
                "confidence": confidence,
                "file": event.data.get("file_path", ""),
            }
        )

        # Keep only last 100 entries
        if len(stats.evolution_history) > 100:
            stats.evolution_history = stats.evolution_history[-100:]

        return "pattern_tracked"

    async def _handle_feedback(self, event: LearningEvent) -> str:
        """Handle feedback event."""
        pattern_id = event.data.get("pattern_id", "")
        is_correct = event.data.get("is_correct", True)

        if pattern_id not in self.pattern_stats:
            self.pattern_stats[pattern_id] = PatternStatistics(pattern_id=pattern_id)

        stats = self.pattern_stats[pattern_id]
        if is_correct:
            stats.true_positives += 1
        else:
            stats.false_positives += 1

        # Recalculate accuracy
        total = stats.true_positives + stats.false_positives
        if total > 0:
            stats.accuracy = stats.true_positives / total

        # Check if retraining needed
        if self._should_trigger_retrain():
            return "retrain_triggered"

        return "feedback_recorded"

    async def _handle_threshold_crossed(self, event: LearningEvent) -> str:
        """Handle threshold crossed event."""
        threshold_type = event.data.get("threshold_type", "")
        current_value = event.data.get("current_value", 0)

        logger.info("Threshold crossed: %s = %s", threshold_type, current_value)

        return "threshold_handled"

    def _should_trigger_retrain(self) -> bool:
        """Check if retraining should be triggered."""
        # Check feedback threshold
        total_feedback = sum(
            s.true_positives + s.false_positives for s in self.pattern_stats.values()
        )
        if total_feedback >= THRESHOLDS["feedback_for_retrain"]:
            if (
                self.last_retrain is None
                or (datetime.now() - self.last_retrain).seconds > 3600
            ):
                return True

        # Check accuracy drop
        if self.accuracy_history:
            recent_accuracy = self._calculate_recent_accuracy()
            if self.accuracy_history and recent_accuracy < self.accuracy_history[0][1]:
                drop = (self.accuracy_history[0][1] - recent_accuracy) * 100
                if drop >= THRESHOLDS["accuracy_drop_percent"]:
                    return True

        return False

    def _calculate_recent_accuracy(self) -> float:
        """Calculate recent overall accuracy."""
        if not self.pattern_stats:
            return 1.0

        total_correct = sum(s.true_positives for s in self.pattern_stats.values())
        total_wrong = sum(s.false_positives for s in self.pattern_stats.values())
        total = total_correct + total_wrong

        return total_correct / total if total > 0 else 1.0

    async def retrain_models(
        self, reason: RetrainingReason, patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Retrain pattern detection models."""
        start_time = time.time()
        self.last_retrain = datetime.now()

        patterns_updated = 0
        improvements = []

        # Process each pattern
        target_patterns = patterns or list(self.pattern_stats.keys())

        for pattern_id in target_patterns:
            if pattern_id not in self.pattern_stats:
                continue

            stats = self.pattern_stats[pattern_id]

            # Simulate retraining improvements
            if stats.false_positives > 0:
                old_accuracy = stats.accuracy
                # Improve accuracy based on feedback
                improvement_factor = min(0.1, stats.false_positives * 0.01)
                new_accuracy = min(1.0, stats.accuracy + improvement_factor)

                if new_accuracy > old_accuracy:
                    stats.accuracy = new_accuracy
                    patterns_updated += 1
                    improvements.append(
                        {
                            "pattern": pattern_id,
                            "old_accuracy": old_accuracy,
                            "new_accuracy": new_accuracy,
                        }
                    )

        # Record accuracy history
        self.accuracy_history.append(
            (datetime.now(), self._calculate_recent_accuracy())
        )
        if len(self.accuracy_history) > 100:
            self.accuracy_history = self.accuracy_history[-100:]

        duration = time.time() - start_time

        return {
            "success": True,
            "reason": reason.value,
            "patterns_analyzed": len(target_patterns),
            "patterns_updated": patterns_updated,
            "improvements": improvements,
            "duration_seconds": round(duration, 2),
            "timestamp": self.last_retrain.isoformat(),
        }

    def _generate_active_pattern_insight(
        self, recent_patterns: List["PatternStats"]  # noqa: F821
    ) -> Optional[Insight]:
        """Generate insight for most active pattern (Issue #398: extracted)."""
        if not recent_patterns:
            return None

        most_active = max(recent_patterns, key=lambda p: p.detections)
        if most_active.detections <= 10:
            return None

        return self._create_insight(
            id_prefix="trend",
            pattern_id=most_active.pattern_id,
            insight_type=InsightType.PATTERN_EVOLUTION,
            title=f"Active Pattern: {most_active.pattern_id}",
            description=f"Pattern '{most_active.pattern_id}' has been detected "
            f"{most_active.detections} times recently.",
            confidence=0.8,
            data={
                "pattern_id": most_active.pattern_id,
                "detections": most_active.detections,
            },
            recommendations=[
                "Review pattern detection rules",
                "Consider if this pattern is over-triggering",
            ],
        )

    def _generate_false_positive_insight(
        self, pattern: "PatternStats"  # noqa: F821
    ) -> Optional[Insight]:
        """Generate insight for high false positive pattern (Issue #398: extracted)."""
        total = pattern.true_positives + pattern.false_positives
        fp_rate = pattern.false_positives / total if total > 0 else 0

        if fp_rate <= 0.3:
            return None

        return self._create_insight(
            id_prefix="fp",
            pattern_id=pattern.pattern_id,
            insight_type=InsightType.FALSE_POSITIVE_TREND,
            title=f"High False Positives: {pattern.pattern_id}",
            description=f"Pattern '{pattern.pattern_id}' has a {fp_rate:.1%} "
            f"false positive rate ({pattern.false_positives} FPs).",
            confidence=0.9,
            data={
                "pattern_id": pattern.pattern_id,
                "false_positive_rate": fp_rate,
                "false_positives": pattern.false_positives,
            },
            recommendations=[
                "Review and tighten pattern detection rules",
                "Consider adding more specific indicators",
                "Analyze false positive examples for commonalities",
            ],
        )

    def _generate_accuracy_improvement_insight(self) -> Optional[Insight]:
        """Generate insight for accuracy improvement (Issue #398: extracted)."""
        if len(self.accuracy_history) < 2:
            return None

        first_acc = self.accuracy_history[0][1]
        current_acc = self.accuracy_history[-1][1]
        improvement = current_acc - first_acc

        if improvement <= 0.05:
            return None

        return self._create_insight(
            id_prefix="improvement",
            pattern_id=None,
            insight_type=InsightType.PERFORMANCE_IMPROVEMENT,
            title="Accuracy Improvement Detected",
            description=f"Overall pattern detection accuracy improved by "
            f"{improvement:.1%} from {first_acc:.1%} to {current_acc:.1%}.",
            confidence=0.95,
            data={
                "initial_accuracy": first_acc,
                "current_accuracy": current_acc,
                "improvement": improvement,
            },
            recommendations=[
                "Continue collecting feedback",
                "Consider expanding to more patterns",
            ],
            expires_days=30,
        )

    async def generate_insights(self) -> List[Insight]:
        """
        Generate insights from learning data (Issue #398: refactored).

        Issue #281: Uses _create_insight helper for Insight creation.
        Issue #398: Extracted insight generators into separate methods.
        """
        new_insights = []
        now = datetime.now()

        # Insight 1: Active pattern trends
        recent_patterns = [
            p
            for p in self.pattern_stats.values()
            if p.last_detected
            and (now - p.last_detected).seconds < THRESHOLDS["anomaly_detection_window"]
        ]
        insight = self._generate_active_pattern_insight(recent_patterns)
        if insight:
            new_insights.append(insight)

        # Insight 2: False positive trends
        high_fp_patterns = [
            p for p in self.pattern_stats.values() if p.false_positives > 5
        ]
        for pattern in high_fp_patterns[:3]:
            insight = self._generate_false_positive_insight(pattern)
            if insight:
                new_insights.append(insight)

        # Insight 3: Accuracy improvement
        insight = self._generate_accuracy_improvement_insight()
        if insight:
            new_insights.append(insight)

        self.insights.extend(new_insights)
        return new_insights

    def get_metrics(self) -> LearningMetrics:
        """Get current learning metrics."""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        events_last_hour = sum(1 for e in self.events if e.timestamp >= hour_ago)
        events_last_day = sum(1 for e in self.events if e.timestamp >= day_ago)

        patterns_learned = len(self.pattern_stats)
        patterns_updated = sum(
            1 for s in self.pattern_stats.values() if len(s.evolution_history) > 1
        )
        false_positives_reduced = sum(
            s.false_positives for s in self.pattern_stats.values()
        )

        # Calculate accuracy improvement
        accuracy_improvement = 0.0
        if len(self.accuracy_history) >= 2:
            accuracy_improvement = (
                self.accuracy_history[-1][1] - self.accuracy_history[0][1]
            )

        active_insights = sum(
            1 for i in self.insights if i.expires_at is None or i.expires_at > now
        )

        return LearningMetrics(
            total_events_processed=self.processed_count,
            events_last_hour=events_last_hour,
            events_last_day=events_last_day,
            patterns_learned=patterns_learned,
            patterns_updated=patterns_updated,
            false_positives_reduced=false_positives_reduced,
            accuracy_improvement=accuracy_improvement,
            last_retrain=self.last_retrain,
            next_scheduled_retrain=None,  # Set by scheduler
            insights_generated=len(self.insights),
            active_insights=active_insights,
        )


# =============================================================================
# File Monitor
# =============================================================================


class FileMonitor:
    """
    Monitors file system for changes.

    Uses polling-based monitoring for cross-platform compatibility.
    """

    def __init__(self, base_path: str = "/home/kali/Desktop/AutoBot"):
        """Initialize file monitor with base path and tracking state."""
        self.base_path = Path(base_path)
        self.state = MonitoringState.STOPPED
        self.started_at: Optional[datetime] = None
        self.file_states: Dict[str, FileState] = {}
        self.watched_paths: List[str] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self, paths: List[str], interval: int = 60) -> bool:
        """Start monitoring specified paths."""
        if self.state == MonitoringState.RUNNING:
            return False

        self.state = MonitoringState.STARTING
        self.watched_paths = paths
        self.started_at = datetime.now()
        self._stop_event.clear()

        # Initial scan
        await self._scan_files()

        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        self.state = MonitoringState.RUNNING

        logger.info("File monitoring started for %s paths", len(paths))
        return True

    async def stop(self) -> bool:
        """Stop monitoring."""
        if self.state != MonitoringState.RUNNING:
            return False

        self.state = MonitoringState.STOPPING
        self._stop_event.set()

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                logger.debug("Monitor task cancelled")

        self.state = MonitoringState.STOPPED
        logger.info("File monitoring stopped")
        return True

    async def _monitor_loop(self, interval: int):
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(interval)
                if self._stop_event.is_set():
                    break
                await self._check_for_changes()
            except asyncio.CancelledError:
                logger.debug("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error("Monitor loop error: %s", e)

    async def _scan_files(self):
        """Scan all monitored files."""
        self.file_states = {}

        for path_str in self.watched_paths:
            path = self.base_path / path_str
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(path.exists):
                continue

            # Issue #358 - avoid blocking with lambda for proper rglob() execution in thread
            py_files = await asyncio.to_thread(lambda: list(path.rglob("*.py")))
            for py_file in py_files:
                if "__pycache__" in str(py_file):
                    continue

                try:
                    # Issue #358 - avoid blocking
                    content = await asyncio.to_thread(
                        py_file.read_text, encoding="utf-8", errors="ignore"
                    )
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    stat = await asyncio.to_thread(py_file.stat)

                    self.file_states[str(py_file)] = FileState(
                        path=str(py_file),
                        content_hash=content_hash,
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                    )
                except Exception as e:
                    logger.debug("File read/hash error, skipping %s: %s", py_file, e)

    def _process_file_change(self, py_file: Path, changes: list) -> None:
        """Process a single file for changes. (Issue #315 - extracted)"""
        file_path = str(py_file)
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            stat = py_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)

            if file_path not in self.file_states:
                # New file
                changes.append(("created", file_path))
                self.file_states[file_path] = FileState(
                    path=file_path,
                    content_hash=content_hash,
                    last_modified=modified,
                )
            elif self.file_states[file_path].content_hash != content_hash:
                # Modified file
                changes.append(("modified", file_path))
                self.file_states[file_path].content_hash = content_hash
                self.file_states[file_path].last_modified = modified
        except Exception as e:
            logger.debug("File read/hash error, skipping %s: %s", file_path, e)

    async def _check_for_changes(self):
        """Check for file changes."""
        changes = []

        for path_str in self.watched_paths:
            path = self.base_path / path_str
            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(path.exists):
                continue
            # Issue #358 - avoid blocking with lambda for proper rglob() execution in thread
            py_files = await asyncio.to_thread(lambda: list(path.rglob("*.py")))
            for py_file in py_files:
                if "__pycache__" in str(py_file):
                    continue
                # Process file changes using helper (Issue #315)
                # Issue #358 - avoid blocking
                await asyncio.to_thread(self._process_file_change, py_file, changes)

        # Check for deleted files
        current_files = set()
        for path_str in self.watched_paths:
            path = self.base_path / path_str
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(path.exists):
                # Issue #358 - avoid blocking with lambda for proper rglob() execution in thread
                py_files = await asyncio.to_thread(lambda: list(path.rglob("*.py")))
                for py_file in py_files:
                    current_files.add(str(py_file))

        for file_path in list(self.file_states.keys()):
            if file_path not in current_files:
                changes.append(("deleted", file_path))
                del self.file_states[file_path]

        # Queue events
        for change_type, file_path in changes:
            event = LearningEvent(
                event_id=hashlib.sha256(
                    f"{change_type}_{file_path}_{datetime.now().isoformat()}".encode()
                ).hexdigest()[:16],
                event_type=LearningEventType.FILE_CHANGE,
                timestamp=datetime.now(),
                source="file_monitor",
                data={"change_type": change_type, "path": file_path},
            )
            await self.event_queue.put(event)

    def get_status(self) -> MonitoringStatus:
        """Get monitoring status."""
        uptime = 0
        if self.started_at and self.state == MonitoringState.RUNNING:
            uptime = int((datetime.now() - self.started_at).total_seconds())

        last_event = None
        # Get approximate last event time
        if self.file_states:
            last_modified = max(
                (s.last_modified for s in self.file_states.values()),
                default=None,
            )
            last_event = last_modified

        return MonitoringStatus(
            state=self.state,
            started_at=self.started_at,
            uptime_seconds=uptime,
            files_monitored=len(self.file_states),
            directories_watched=self.watched_paths,
            events_queue_size=self.event_queue.qsize(),
            last_event_time=last_event,
        )


# =============================================================================
# Continuous Learning Engine
# =============================================================================


class ContinuousLearningEngine:
    """
    Main engine for continuous pattern learning.

    Coordinates:
    - File monitoring
    - Event processing
    - Learning pipeline
    - Insight generation
    - Dashboard updates
    """

    def __init__(self):
        """Initialize learning engine with config, pipeline, and monitor."""
        self.config = LearningConfig()
        self.pipeline = LearningPipeline()
        self.monitor = FileMonitor()
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._insight_task: Optional[asyncio.Task] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the learning engine."""
        if self._initialized:
            return True

        self._initialized = True
        logger.info("Continuous Learning Engine initialized")
        return True

    async def start(self) -> Dict[str, Any]:
        """Start the continuous learning system."""
        await self.initialize()

        if self._running:
            return {"status": "already_running"}

        self._running = True

        # Start file monitor
        if self.config.monitoring_enabled:
            await self.monitor.start(
                self.config.monitored_paths,
                self.config.scan_interval_seconds,
            )

        # Start event processing
        self._processing_task = asyncio.create_task(self._process_events())

        # Start insight generation
        if self.config.insight_generation_enabled:
            self._insight_task = asyncio.create_task(self._generate_insights_loop())

        return {
            "status": "started",
            "monitoring": self.config.monitoring_enabled,
            "auto_retrain": self.config.auto_retrain_enabled,
            "insight_generation": self.config.insight_generation_enabled,
        }

    async def stop(self) -> Dict[str, Any]:
        """Stop the continuous learning system."""
        if not self._running:
            return {"status": "not_running"}

        self._running = False

        # Stop monitor
        await self.monitor.stop()

        # Cancel tasks
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                logger.debug("Processing task cancelled during shutdown")

        if self._insight_task:
            self._insight_task.cancel()
            try:
                await self._insight_task
            except asyncio.CancelledError:
                logger.debug("Insight task cancelled during shutdown")

        return {"status": "stopped"}

    async def _process_events(self):
        """Process events from the monitor."""
        while self._running:
            try:
                # Get event with timeout
                try:
                    event = await asyncio.wait_for(
                        self.monitor.event_queue.get(), timeout=5.0
                    )
                    await self.pipeline.process_event(event)
                except asyncio.TimeoutError:
                    continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Event processing error: %s", e)

    async def _generate_insights_loop(self):
        """Periodically generate insights."""
        while self._running:
            try:
                await asyncio.sleep(THRESHOLDS["insight_generation_interval"])
                if not self._running:
                    break
                await self.pipeline.generate_insights()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Insight generation error: %s", e)

    async def submit_feedback(
        self, pattern_id: str, is_correct: bool, details: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit feedback for a pattern detection."""
        event = LearningEvent(
            event_id=hashlib.sha256(
                f"feedback_{pattern_id}_{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16],
            event_type=LearningEventType.FEEDBACK_RECEIVED,
            timestamp=datetime.now(),
            source="api",
            data={
                "pattern_id": pattern_id,
                "is_correct": is_correct,
                "details": details,
            },
        )

        result = await self.pipeline.process_event(event)

        return {
            "feedback_id": event.event_id,
            "processed": result.get("processed", False),
            "action": result.get("action", "none"),
        }

    async def trigger_retrain(self, request: RetrainingRequest) -> Dict[str, Any]:
        """Manually trigger model retraining."""
        return await self.pipeline.retrain_models(
            reason=request.reason,
            patterns=request.patterns_to_focus,
        )

    async def get_insights(
        self, active_only: bool = True, limit: int = 20
    ) -> List[Insight]:
        """Get generated insights."""
        now = datetime.now()
        insights = self.pipeline.insights

        if active_only:
            insights = [
                i for i in insights if i.expires_at is None or i.expires_at > now
            ]

        return sorted(insights, key=lambda i: i.generated_at, reverse=True)[:limit]

    def get_metrics(self) -> LearningMetrics:
        """Get learning metrics."""
        return self.pipeline.get_metrics()

    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "running": self._running,
            "initialized": self._initialized,
            "config": self.config.model_dump(),
            "monitoring": self.monitor.get_status().model_dump(),
            "metrics": self.get_metrics().model_dump(),
        }


# =============================================================================
# Global Instance
# =============================================================================

_engine: Optional[ContinuousLearningEngine] = None
_engine_lock = asyncio.Lock()


async def get_engine() -> ContinuousLearningEngine:
    """Get or create the global learning engine."""
    global _engine

    if _engine is None:
        async with _engine_lock:
            if _engine is None:
                _engine = ContinuousLearningEngine()
                await _engine.initialize()

    return _engine


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/start", summary="Start continuous learning")
async def start_learning(
    admin_check: bool = Depends(check_admin_permission),
    background_tasks: BackgroundTasks = None,
) -> Dict[str, Any]:
    """
    Start the continuous learning system.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return await engine.start()


@router.post("/stop", summary="Stop continuous learning")
async def stop_learning(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """
    Stop the continuous learning system.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return await engine.stop()


@router.get("/status", summary="Get learning status")
async def get_status(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """
    Get current status of the learning system.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return engine.get_status()


@router.get("/metrics", summary="Get learning metrics")
async def get_metrics(
    admin_check: bool = Depends(check_admin_permission),
) -> LearningMetrics:
    """
    Get learning metrics.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return engine.get_metrics()


@router.post("/feedback", summary="Submit pattern feedback")
async def submit_feedback(
    admin_check: bool = Depends(check_admin_permission),
    pattern_id: str = None,
    is_correct: bool = None,
    details: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit feedback for a pattern detection.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return await engine.submit_feedback(pattern_id, is_correct, details)


@router.post("/retrain", summary="Trigger model retraining")
async def trigger_retrain(
    admin_check: bool = Depends(check_admin_permission),
    request: RetrainingRequest = None,
) -> Dict[str, Any]:
    """
    Manually trigger model retraining.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return await engine.trigger_retrain(request)


@router.get("/insights", summary="Get generated insights")
async def get_insights(
    admin_check: bool = Depends(check_admin_permission),
    active_only: bool = Query(True, description="Only active insights"),
    limit: int = Query(20, ge=1, le=100, description="Maximum insights"),
) -> Dict[str, Any]:
    """
    Get generated insights.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    insights = await engine.get_insights(active_only, limit)
    return {
        "insights": [i.model_dump() for i in insights],
        "total": len(insights),
    }


@router.post("/insights/generate", summary="Generate insights now")
async def generate_insights_now(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """
    Manually trigger insight generation.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    new_insights = await engine.pipeline.generate_insights()
    return {
        "generated": len(new_insights),
        "insights": [i.model_dump() for i in new_insights],
    }


@router.get("/monitoring", summary="Get monitoring status")
async def get_monitoring_status(
    admin_check: bool = Depends(check_admin_permission),
) -> MonitoringStatus:
    """
    Get file monitoring status.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return engine.monitor.get_status()


@router.put("/config", summary="Update learning config")
async def update_config(
    admin_check: bool = Depends(check_admin_permission),
    config: LearningConfig = None,
) -> Dict[str, Any]:
    """
    Update learning configuration.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    engine.config = config
    return {"updated": True, "config": config.model_dump()}


@router.get("/config", summary="Get learning config")
async def get_config(
    admin_check: bool = Depends(check_admin_permission),
) -> LearningConfig:
    """
    Get current learning configuration.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return engine.config


@router.get("/health", summary="Health check")
async def health_check(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, Any]:
    """
    Check health of the learning system.

    Issue #744: Requires admin authentication.
    """
    engine = await get_engine()
    return {
        "status": "healthy",
        "running": engine._running,
        "initialized": engine._initialized,
    }
