# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dynamic Pattern Mining from Logs (Issue #226)

Extracts patterns from runtime logs to understand application behavior,
identify issues, and find performance bottlenecks.

Part of EPIC #217 - Advanced Code Intelligence Methods

Features:
- Multi-format log parsing (standard, JSON, syslog)
- Pattern extraction and frequency analysis
- Error sequence detection
- Performance bottleneck identification
- Anomaly detection
- API usage pattern analysis
- Session flow tracking
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Data Classes
# ============================================================================


class LogLevel(Enum):
    """Log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Module-level constants for repeated level checks (Issue #380)
_ERROR_CRITICAL_LEVELS = (LogLevel.ERROR, LogLevel.CRITICAL)
_ERROR_CRITICAL_WARNING_LEVELS = (LogLevel.ERROR, LogLevel.CRITICAL, LogLevel.WARNING)

# Pre-compiled regex patterns for _normalize_error_message() (Issue #380)
# Called per error entry, so pre-compilation avoids repeated compilation
_NORMALIZE_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_NORMALIZE_ID_RE = re.compile(r"[a-f0-9]{24,}")
_NORMALIZE_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_NORMALIZE_PATH_RE = re.compile(r"[/\\][\w/\\.-]+\.\w+")
_NORMALIZE_NUMBER_RE = re.compile(r"\b\d+\b")


class PatternType(Enum):
    """Types of detected patterns."""

    ERROR_SEQUENCE = "error_sequence"
    PERFORMANCE_BOTTLENECK = "performance_bottleneck"
    API_USAGE = "api_usage"
    SESSION_FLOW = "session_flow"
    RECURRING_ERROR = "recurring_error"
    ANOMALY = "anomaly"
    REDIS_OPERATION = "redis_operation"
    LLM_CALL = "llm_call"


class AnomalyType(Enum):
    """Types of anomalies detected."""

    SPIKE = "spike"
    DROP = "drop"
    UNUSUAL_PATTERN = "unusual_pattern"
    THRESHOLD_EXCEEDED = "threshold_exceeded"
    SEQUENCE_BREAK = "sequence_break"


@dataclass
class LogEntry:
    """Parsed log entry."""

    timestamp: datetime
    level: LogLevel
    logger_name: str
    message: str
    raw_line: str
    line_number: int
    file_path: Optional[str] = None
    session_id: Optional[str] = None
    duration_ms: Optional[float] = None
    endpoint: Optional[str] = None
    status_code: Optional[int] = None
    extra_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "logger_name": self.logger_name,
            "message": self.message,
            "line_number": self.line_number,
            "file_path": self.file_path,
            "session_id": self.session_id,
            "duration_ms": self.duration_ms,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "extra_data": self.extra_data,
        }


@dataclass
class LogPattern:
    """Detected pattern in logs."""

    id: str
    pattern_type: PatternType
    description: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    affected_components: list[str] = field(default_factory=list)
    sample_entries: list[LogEntry] = field(default_factory=list)
    severity: LogLevel = LogLevel.INFO
    extra_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "occurrences": self.occurrences,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "affected_components": self.affected_components,
            "sample_entries": [e.to_dict() for e in self.sample_entries[:5]],
            "severity": self.severity.value,
            "extra_data": self.extra_data,
        }


@dataclass
class Anomaly:
    """Detected anomaly in logs."""

    id: str
    anomaly_type: AnomalyType
    description: str
    detected_at: datetime
    severity: LogLevel
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_percent: float
    related_entries: list[LogEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "anomaly_type": self.anomaly_type.value,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
            "severity": self.severity.value,
            "metric_name": self.metric_name,
            "expected_value": round(self.expected_value, 2),
            "actual_value": round(self.actual_value, 2),
            "deviation_percent": round(self.deviation_percent, 2),
            "related_entries": [e.to_dict() for e in self.related_entries[:3]],
        }


@dataclass
class SessionFlow:
    """User session flow pattern."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    endpoints: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_duration_ms: float = 0.0
    request_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "endpoints": self.endpoints,
            "errors": self.errors,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "request_count": self.request_count,
        }


@dataclass
class MiningResult:
    """Complete log mining result."""

    id: str
    timestamp: datetime
    files_analyzed: int
    total_entries: int
    time_range: tuple[datetime, datetime]
    patterns: list[LogPattern] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    sessions: list[SessionFlow] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "files_analyzed": self.files_analyzed,
            "total_entries": self.total_entries,
            "time_range": {
                "start": self.time_range[0].isoformat(),
                "end": self.time_range[1].isoformat(),
            },
            "patterns": [p.to_dict() for p in self.patterns],
            "anomalies": [a.to_dict() for a in self.anomalies],
            "sessions": [s.to_dict() for s in self.sessions[:20]],
            "statistics": self.statistics,
            "summary": self.summary,
        }


# ============================================================================
# Log Parsers
# ============================================================================


class LogParser:
    """Base log parser with common patterns."""

    # Standard AutoBot log format: 2025-09-07 21:36:47 - RUM - INFO - message
    STANDARD_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"  # timestamp
        r"\s+-\s+"
        r"(\w+(?:\.\w+)*)"  # logger name
        r"\s+-\s+"
        r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)"  # level
        r"\s+-\s+"
        r"(.+)$",  # message
        re.IGNORECASE,
    )

    # Python logging format: LEVEL:logger:message
    PYTHON_PATTERN = re.compile(
        r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL):(\w+(?:\.\w+)*):(.+)$",
        re.IGNORECASE,
    )

    # Session ID pattern
    SESSION_PATTERN = re.compile(r"SESSION=(\S+)")

    # API call pattern with duration
    API_CALL_PATTERN = re.compile(
        r"API_CALL:\s+(GET|POST|PUT|DELETE|PATCH)\s+(\S+)\s+"
        r"DURATION=(\d+\.?\d*)ms\s+STATUS=(\d+)"
    )

    # Duration pattern
    DURATION_PATTERN = re.compile(r"DURATION[=:]?\s*(\d+\.?\d*)\s*ms", re.IGNORECASE)

    # Error patterns
    ERROR_PATTERNS = {
        "exception": re.compile(r"(?:Exception|Error):\s*(.+)", re.IGNORECASE),
        "traceback": re.compile(r"Traceback \(most recent call last\)"),
        "failed": re.compile(r"(?:failed|failure):\s*(.+)", re.IGNORECASE),
    }

    # Performance threshold patterns
    SLOW_REQUEST_THRESHOLD_MS = 100.0

    @classmethod
    def parse_line(
        cls, line: str, line_number: int, file_path: Optional[str] = None
    ) -> Optional[LogEntry]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None

        # Try standard AutoBot format first
        match = cls.STANDARD_PATTERN.match(line)
        if match:
            return cls._create_entry_from_standard(match, line, line_number, file_path)

        # Try Python logging format
        match = cls.PYTHON_PATTERN.match(line)
        if match:
            return cls._create_entry_from_python(match, line, line_number, file_path)

        return None

    @classmethod
    def _create_entry_from_standard(
        cls,
        match: re.Match,
        raw_line: str,
        line_number: int,
        file_path: Optional[str],
    ) -> LogEntry:
        """Create LogEntry from standard format match."""
        timestamp_str, logger_name, level_str, message = match.groups()

        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            timestamp = datetime.now()

        level = LogLevel(level_str.lower())

        # Extract additional info from message
        session_id = None
        session_match = cls.SESSION_PATTERN.search(message)
        if session_match:
            session_id = session_match.group(1)

        duration_ms = None
        endpoint = None
        status_code = None

        api_match = cls.API_CALL_PATTERN.search(message)
        if api_match:
            method, endpoint, duration_str, status_str = api_match.groups()
            endpoint = f"{method} {endpoint}"
            duration_ms = float(duration_str)
            status_code = int(status_str)
        else:
            duration_match = cls.DURATION_PATTERN.search(message)
            if duration_match:
                duration_ms = float(duration_match.group(1))

        return LogEntry(
            timestamp=timestamp,
            level=level,
            logger_name=logger_name,
            message=message,
            raw_line=raw_line,
            line_number=line_number,
            file_path=file_path,
            session_id=session_id,
            duration_ms=duration_ms,
            endpoint=endpoint,
            status_code=status_code,
        )

    @classmethod
    def _create_entry_from_python(
        cls,
        match: re.Match,
        raw_line: str,
        line_number: int,
        file_path: Optional[str],
    ) -> LogEntry:
        """Create LogEntry from Python logging format match."""
        level_str, logger_name, message = match.groups()

        return LogEntry(
            timestamp=datetime.now(),
            level=LogLevel(level_str.lower()),
            logger_name=logger_name,
            message=message,
            raw_line=raw_line,
            line_number=line_number,
            file_path=file_path,
        )


# ============================================================================
# Log Pattern Miner
# ============================================================================


class LogPatternMiner:
    """
    Dynamic pattern miner for runtime logs.

    Analyzes log files to extract patterns, detect anomalies,
    and identify performance bottlenecks.
    """

    def __init__(
        self,
        slow_request_threshold_ms: float = 100.0,
        error_threshold: int = 5,
        anomaly_deviation_threshold: float = 2.0,
        min_pattern_occurrences: int = 3,
    ):
        """
        Initialize Log Pattern Miner.

        Args:
            slow_request_threshold_ms: Threshold for slow request detection
            error_threshold: Minimum errors to flag as pattern
            anomaly_deviation_threshold: Standard deviations for anomaly
            min_pattern_occurrences: Minimum occurrences for pattern detection
        """
        self.slow_request_threshold_ms = slow_request_threshold_ms
        self.error_threshold = error_threshold
        self.anomaly_deviation_threshold = anomaly_deviation_threshold
        self.min_pattern_occurrences = min_pattern_occurrences

        self.entries: list[LogEntry] = []
        self.patterns: list[LogPattern] = []
        self.anomalies: list[Anomaly] = []
        self.sessions: dict[str, SessionFlow] = {}

    def parse_file(self, file_path: str) -> list[LogEntry]:
        """
        Parse a log file.

        Args:
            file_path: Path to the log file

        Returns:
            List of parsed log entries
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("Log file not found: %s", file_path)
            return []

        entries = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line_number, line in enumerate(f, 1):
                    entry = LogParser.parse_line(line, line_number, file_path)
                    if entry:
                        entries.append(entry)
        except Exception as e:
            logger.warning("Failed to parse log file %s: %s", file_path, e)

        return entries

    def parse_content(self, content: str, source: str = "inline") -> list[LogEntry]:
        """
        Parse log content from string.

        Args:
            content: Log content string
            source: Source identifier

        Returns:
            List of parsed log entries
        """
        entries = []
        for line_number, line in enumerate(content.split("\n"), 1):
            entry = LogParser.parse_line(line, line_number, source)
            if entry:
                entries.append(entry)
        return entries

    def _parse_all_sources(
        self, log_files: Optional[list[str]], content: Optional[str]
    ) -> int:
        """Parse all log sources and populate entries.

        Args:
            log_files: List of log file paths
            content: Direct log content string

        Returns:
            Number of files successfully analyzed.

        Issue #620.
        """
        files_analyzed = 0

        if log_files:
            for file_path in log_files:
                entries = self.parse_file(file_path)
                self.entries.extend(entries)
                if entries:
                    files_analyzed += 1

        if content:
            entries = self.parse_content(content)
            self.entries.extend(entries)
            if entries:
                files_analyzed += 1

        return files_analyzed

    def _create_empty_result(self) -> MiningResult:
        """Create an empty MiningResult when no entries are found.

        Returns:
            MiningResult with empty/default values.

        Issue #620.
        """
        return MiningResult(
            id=f"mining-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(),
            files_analyzed=0,
            total_entries=0,
            time_range=(datetime.now(), datetime.now()),
            patterns=[],
            anomalies=[],
            sessions=[],
            statistics={},
            summary={"message": "No log entries found"},
        )

    def _build_mining_result(self, files_analyzed: int) -> MiningResult:
        """Build the final MiningResult with all extracted data.

        Args:
            files_analyzed: Number of files successfully analyzed.

        Returns:
            Complete MiningResult with patterns, anomalies, and statistics.

        Issue #620.
        """
        statistics = self._calculate_statistics()
        summary = self._generate_summary()
        time_range = (self.entries[0].timestamp, self.entries[-1].timestamp)

        return MiningResult(
            id=f"mining-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(),
            files_analyzed=files_analyzed,
            total_entries=len(self.entries),
            time_range=time_range,
            patterns=self.patterns,
            anomalies=self.anomalies,
            sessions=list(self.sessions.values()),
            statistics=statistics,
            summary=summary,
        )

    def analyze(
        self, log_files: Optional[list[str]] = None, content: Optional[str] = None
    ) -> MiningResult:
        """Analyze logs and extract patterns.

        Args:
            log_files: List of log file paths
            content: Direct log content string

        Returns:
            MiningResult with all findings
        """
        self.entries = []
        self.patterns = []
        self.anomalies = []
        self.sessions = {}

        files_analyzed = self._parse_all_sources(log_files, content)

        if not self.entries:
            return self._create_empty_result()

        # Sort by timestamp
        self.entries.sort(key=lambda e: e.timestamp)

        # Extract patterns
        self._extract_error_patterns()
        self._extract_performance_patterns()
        self._extract_api_patterns()
        self._extract_session_flows()
        self._detect_anomalies()

        return self._build_mining_result(files_analyzed)

    def _extract_error_patterns(self) -> None:
        """Extract recurring error patterns."""
        error_entries = [
            e for e in self.entries if e.level in _ERROR_CRITICAL_WARNING_LEVELS
        ]

        if not error_entries:
            return

        # Group errors by normalized message
        error_groups: dict[str, list[LogEntry]] = defaultdict(list)

        for entry in error_entries:
            # Normalize message by removing variable parts
            normalized = self._normalize_error_message(entry.message)
            error_groups[normalized].append(entry)

        # Create patterns for recurring errors
        for normalized_msg, entries in error_groups.items():
            if len(entries) >= self.min_pattern_occurrences:
                affected_components = list(set(e.logger_name for e in entries))

                self.patterns.append(
                    LogPattern(
                        id=f"ERR-{len(self.patterns) + 1}",
                        pattern_type=PatternType.RECURRING_ERROR,
                        description=f"Recurring error: {normalized_msg[:100]}",
                        occurrences=len(entries),
                        first_seen=entries[0].timestamp,
                        last_seen=entries[-1].timestamp,
                        affected_components=affected_components,
                        sample_entries=entries[:5],
                        severity=entries[0].level,
                        extra_data={
                            "normalized_message": normalized_msg,
                            "unique_messages": len(set(e.message for e in entries)),
                        },
                    )
                )

    def _extract_performance_patterns(self) -> None:
        """Extract performance bottleneck patterns."""
        slow_requests = [
            e
            for e in self.entries
            if e.duration_ms and e.duration_ms > self.slow_request_threshold_ms
        ]

        if not slow_requests:
            return

        # Group by endpoint
        endpoint_groups: dict[str, list[LogEntry]] = defaultdict(list)

        for entry in slow_requests:
            key = entry.endpoint or entry.logger_name
            endpoint_groups[key].append(entry)

        # Create patterns for slow endpoints
        for endpoint, entries in endpoint_groups.items():
            if len(entries) >= self.min_pattern_occurrences:
                durations = [e.duration_ms for e in entries if e.duration_ms]
                avg_duration = mean(durations) if durations else 0

                self.patterns.append(
                    LogPattern(
                        id=f"PERF-{len(self.patterns) + 1}",
                        pattern_type=PatternType.PERFORMANCE_BOTTLENECK,
                        description=f"Slow endpoint: {endpoint} (avg: {avg_duration:.1f}ms)",
                        occurrences=len(entries),
                        first_seen=entries[0].timestamp,
                        last_seen=entries[-1].timestamp,
                        affected_components=[endpoint],
                        sample_entries=entries[:5],
                        severity=LogLevel.WARNING,
                        extra_data={
                            "avg_duration_ms": round(avg_duration, 2),
                            "max_duration_ms": max(durations) if durations else 0,
                            "min_duration_ms": min(durations) if durations else 0,
                            "threshold_ms": self.slow_request_threshold_ms,
                        },
                    )
                )

    def _extract_api_patterns(self) -> None:
        """Extract API usage patterns."""
        api_entries = [e for e in self.entries if e.endpoint]

        if not api_entries:
            return

        # Group by endpoint
        endpoint_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "durations": [], "status_codes": [], "entries": []}
        )

        for entry in api_entries:
            stats = endpoint_stats[entry.endpoint]
            stats["count"] += 1
            stats["entries"].append(entry)
            if entry.duration_ms:
                stats["durations"].append(entry.duration_ms)
            if entry.status_code:
                stats["status_codes"].append(entry.status_code)

        # Find high-traffic endpoints
        sorted_endpoints = sorted(
            endpoint_stats.items(), key=lambda x: x[1]["count"], reverse=True
        )

        for endpoint, stats in sorted_endpoints[:10]:
            if stats["count"] >= self.min_pattern_occurrences:
                durations = stats["durations"]
                error_count = len([c for c in stats["status_codes"] if c >= 400])

                self.patterns.append(
                    LogPattern(
                        id=f"API-{len(self.patterns) + 1}",
                        pattern_type=PatternType.API_USAGE,
                        description=f"High-traffic endpoint: {endpoint}",
                        occurrences=stats["count"],
                        first_seen=stats["entries"][0].timestamp,
                        last_seen=stats["entries"][-1].timestamp,
                        affected_components=[
                            endpoint.split()[1] if " " in endpoint else endpoint
                        ],
                        sample_entries=stats["entries"][:3],
                        severity=LogLevel.WARNING if error_count > 0 else LogLevel.INFO,
                        extra_data={
                            "avg_duration_ms": round(mean(durations), 2)
                            if durations
                            else 0,
                            "error_count": error_count,
                            "success_rate": round(
                                (stats["count"] - error_count) / stats["count"] * 100, 1
                            ),
                        },
                    )
                )

    def _extract_session_flows(self) -> None:
        """Extract user session flow patterns."""
        session_entries = [e for e in self.entries if e.session_id]

        if not session_entries:
            return

        # Group by session ID
        for entry in session_entries:
            session_id = entry.session_id
            if session_id not in self.sessions:
                self.sessions[session_id] = SessionFlow(
                    session_id=session_id,
                    start_time=entry.timestamp,
                    end_time=None,
                )

            session = self.sessions[session_id]
            session.end_time = entry.timestamp
            session.request_count += 1

            if entry.endpoint:
                session.endpoints.append(entry.endpoint)

            if entry.duration_ms:
                session.total_duration_ms += entry.duration_ms

            if entry.level in _ERROR_CRITICAL_LEVELS:
                session.errors.append(entry.message[:100])

        # Create session flow patterns for sessions with errors
        error_sessions = [s for s in self.sessions.values() if s.errors]
        if len(error_sessions) >= self.min_pattern_occurrences:
            self.patterns.append(
                LogPattern(
                    id=f"SESS-{len(self.patterns) + 1}",
                    pattern_type=PatternType.SESSION_FLOW,
                    description=f"Sessions with errors: {len(error_sessions)} sessions",
                    occurrences=len(error_sessions),
                    first_seen=min(s.start_time for s in error_sessions),
                    last_seen=max(s.end_time or s.start_time for s in error_sessions),
                    affected_components=list(
                        set(e for s in error_sessions for e in s.endpoints[:3])
                    ),
                    severity=LogLevel.WARNING,
                    extra_data={
                        "total_sessions": len(self.sessions),
                        "error_session_count": len(error_sessions),
                        "error_rate": round(
                            len(error_sessions) / len(self.sessions) * 100, 1
                        ),
                    },
                )
            )

    def _detect_anomalies(self) -> None:
        """Detect anomalies in log patterns."""
        self._detect_duration_anomalies()
        self._detect_error_rate_anomalies()

    def _detect_duration_anomalies(self) -> None:
        """
        Detect request duration anomalies using statistical deviation.

        Identifies entries with durations that deviate significantly
        from the average, flagging them as spikes or drops.

        Issue #620.
        """
        entries_with_duration = [e for e in self.entries if e.duration_ms]

        if len(entries_with_duration) < 10:
            return

        durations = [e.duration_ms for e in entries_with_duration]
        avg = mean(durations)
        std = stdev(durations) if len(durations) > 1 else 0

        if std <= 0:
            return

        for entry in entries_with_duration:
            deviation = (entry.duration_ms - avg) / std
            if abs(deviation) > self.anomaly_deviation_threshold:
                anomaly_type = AnomalyType.SPIKE if deviation > 0 else AnomalyType.DROP
                self.anomalies.append(
                    Anomaly(
                        id=f"ANOM-{len(self.anomalies) + 1}",
                        anomaly_type=anomaly_type,
                        description=(
                            f"Unusual duration: {entry.duration_ms:.1f}ms "
                            f"(expected: {avg:.1f}ms)"
                        ),
                        detected_at=entry.timestamp,
                        severity=LogLevel.WARNING,
                        metric_name="request_duration",
                        expected_value=avg,
                        actual_value=entry.duration_ms,
                        deviation_percent=abs(deviation) * 100,
                        related_entries=[entry],
                    )
                )

    def _detect_error_rate_anomalies(self) -> None:
        """
        Detect hourly error rate anomalies using statistical deviation.

        Identifies hours with error rates that deviate significantly
        from the average hourly error rate.

        Issue #620.
        """
        hourly_errors, hourly_total = self._compute_hourly_error_counts()

        if len(hourly_errors) < 3:
            return

        error_rates = [
            hourly_errors[h] / hourly_total[h] * 100
            for h in hourly_total
            if hourly_total[h] > 0
        ]
        avg_rate = mean(error_rates)
        std_rate = stdev(error_rates) if len(error_rates) > 1 else 0

        if std_rate <= 0:
            return

        for hour, total in hourly_total.items():
            rate = hourly_errors[hour] / total * 100 if total > 0 else 0
            deviation = (rate - avg_rate) / std_rate
            if deviation > self.anomaly_deviation_threshold:
                self.anomalies.append(
                    Anomaly(
                        id=f"ANOM-{len(self.anomalies) + 1}",
                        anomaly_type=AnomalyType.SPIKE,
                        description=f"High error rate: {rate:.1f}% at {hour}",
                        detected_at=datetime.strptime(hour, "%Y-%m-%d %H:00"),
                        severity=LogLevel.ERROR,
                        metric_name="error_rate",
                        expected_value=avg_rate,
                        actual_value=rate,
                        deviation_percent=abs(deviation) * 100,
                    )
                )

    def _compute_hourly_error_counts(self) -> tuple[dict[str, int], dict[str, int]]:
        """
        Compute hourly error and total entry counts.

        Returns:
            Tuple of (hourly_errors, hourly_total) dictionaries.

        Issue #620.
        """
        hourly_errors: dict[str, int] = defaultdict(int)
        hourly_total: dict[str, int] = defaultdict(int)

        for entry in self.entries:
            hour_key = entry.timestamp.strftime("%Y-%m-%d %H:00")
            hourly_total[hour_key] += 1
            if entry.level in _ERROR_CRITICAL_LEVELS:
                hourly_errors[hour_key] += 1

        return hourly_errors, hourly_total

    def _normalize_error_message(self, message: str) -> str:
        """Normalize error message by removing variable parts."""
        # Use pre-compiled patterns (Issue #380)
        normalized = _NORMALIZE_TIMESTAMP_RE.sub("<TIMESTAMP>", message)
        normalized = _NORMALIZE_ID_RE.sub("<ID>", normalized)
        normalized = _NORMALIZE_IP_RE.sub("<IP>", normalized)
        normalized = _NORMALIZE_PATH_RE.sub("<PATH>", normalized)
        normalized = _NORMALIZE_NUMBER_RE.sub("<NUM>", normalized)

        return normalized

    def _calculate_statistics(self) -> dict[str, Any]:
        """Calculate log statistics."""
        level_counts = Counter(e.level.value for e in self.entries)
        logger_counts = Counter(e.logger_name for e in self.entries)
        hourly_counts = Counter(e.timestamp.strftime("%H:00") for e in self.entries)

        durations = [e.duration_ms for e in self.entries if e.duration_ms]

        return {
            "by_level": dict(level_counts),
            "by_logger": dict(logger_counts.most_common(10)),
            "by_hour": dict(sorted(hourly_counts.items())),
            "total_errors": level_counts.get("error", 0)
            + level_counts.get("critical", 0),
            "total_warnings": level_counts.get("warning", 0),
            "avg_duration_ms": round(mean(durations), 2) if durations else 0,
            "max_duration_ms": max(durations) if durations else 0,
            "min_duration_ms": min(durations) if durations else 0,
            "unique_sessions": len(self.sessions),
            "unique_endpoints": len(
                set(e.endpoint for e in self.entries if e.endpoint)
            ),
        }

    def _generate_summary(self) -> dict[str, Any]:
        """Generate analysis summary."""
        critical_patterns = [
            p for p in self.patterns if p.severity in _ERROR_CRITICAL_LEVELS
        ]
        warning_patterns = [p for p in self.patterns if p.severity == LogLevel.WARNING]

        return {
            "total_patterns": len(self.patterns),
            "critical_patterns": len(critical_patterns),
            "warning_patterns": len(warning_patterns),
            "total_anomalies": len(self.anomalies),
            "sessions_analyzed": len(self.sessions),
            "top_issues": [
                {
                    "type": p.pattern_type.value,
                    "description": p.description[:80],
                    "occurrences": p.occurrences,
                }
                for p in sorted(
                    self.patterns, key=lambda x: x.occurrences, reverse=True
                )[:5]
            ],
            "health_score": self._calculate_health_score(),
        }

    def _calculate_health_score(self) -> float:
        """Calculate overall log health score (0-100)."""
        if not self.entries:
            return 100.0

        score = 100.0

        # Deduct for errors
        error_rate = sum(
            1 for e in self.entries if e.level in _ERROR_CRITICAL_LEVELS
        ) / len(self.entries)
        score -= min(30, error_rate * 100)

        # Deduct for patterns
        score -= min(20, len(self.patterns) * 2)

        # Deduct for anomalies
        score -= min(20, len(self.anomalies) * 3)

        # Deduct for slow requests
        slow_rate = sum(
            1
            for e in self.entries
            if e.duration_ms and e.duration_ms > self.slow_request_threshold_ms
        ) / len(self.entries)
        score -= min(15, slow_rate * 100)

        return max(0, round(score, 1))


# ============================================================================
# Convenience Functions
# ============================================================================


def analyze_logs(
    log_files: Optional[list[str]] = None,
    content: Optional[str] = None,
    slow_threshold_ms: float = 100.0,
) -> MiningResult:
    """
    Analyze log files for patterns and anomalies.

    Args:
        log_files: List of log file paths
        content: Direct log content string
        slow_threshold_ms: Threshold for slow request detection

    Returns:
        MiningResult with all findings
    """
    miner = LogPatternMiner(slow_request_threshold_ms=slow_threshold_ms)
    return miner.analyze(log_files, content)


def get_pattern_types() -> list[dict[str, Any]]:
    """
    Get all pattern types.

    Returns:
        List of pattern type definitions
    """
    descriptions = {
        PatternType.ERROR_SEQUENCE: "Sequence of related errors",
        PatternType.PERFORMANCE_BOTTLENECK: "Slow performance patterns",
        PatternType.API_USAGE: "API usage and traffic patterns",
        PatternType.SESSION_FLOW: "User session flow patterns",
        PatternType.RECURRING_ERROR: "Frequently occurring errors",
        PatternType.ANOMALY: "Unusual behavior patterns",
        PatternType.REDIS_OPERATION: "Redis operation patterns",
        PatternType.LLM_CALL: "LLM API call patterns",
    }

    return [
        {
            "id": pt.value,
            "name": pt.value.replace("_", " ").title(),
            "description": descriptions.get(pt, ""),
        }
        for pt in PatternType
    ]


def get_anomaly_types() -> list[dict[str, Any]]:
    """
    Get all anomaly types.

    Returns:
        List of anomaly type definitions
    """
    descriptions = {
        AnomalyType.SPIKE: "Sudden increase in metric value",
        AnomalyType.DROP: "Sudden decrease in metric value",
        AnomalyType.UNUSUAL_PATTERN: "Pattern deviating from normal",
        AnomalyType.THRESHOLD_EXCEEDED: "Value exceeded defined threshold",
        AnomalyType.SEQUENCE_BREAK: "Expected sequence not followed",
    }

    return [
        {
            "id": at.value,
            "name": at.value.replace("_", " ").title(),
            "description": descriptions.get(at, ""),
        }
        for at in AnomalyType
    ]


def get_log_levels() -> list[dict[str, Any]]:
    """
    Get all log levels.

    Returns:
        List of log level definitions
    """
    weights = {
        LogLevel.DEBUG: 1,
        LogLevel.INFO: 2,
        LogLevel.WARNING: 3,
        LogLevel.ERROR: 4,
        LogLevel.CRITICAL: 5,
    }

    return [
        {
            "level": ll.value,
            "weight": weights.get(ll, 0),
        }
        for ll in LogLevel
    ]
