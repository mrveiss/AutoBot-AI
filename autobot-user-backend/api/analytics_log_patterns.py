# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dynamic Pattern Mining from Logs API (Issue #226)
Provides endpoints for discovering patterns, anomalies, and trends in log data
"""

import asyncio
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/log-patterns", tags=["log-patterns", "analytics"])

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# Performance optimization: O(1) lookup for error levels and log level iteration (Issue #326)
ERROR_LEVELS = {"ERROR", "CRITICAL"}
LOG_LEVEL_PRIORITIES = ["CRITICAL", "ERROR", "WARNING", "WARN", "INFO", "DEBUG"]


# ============================================================================
# Pydantic Models
# ============================================================================


class LogPattern(BaseModel):
    """Represents a discovered log pattern"""

    pattern_id: str
    pattern_template: str
    occurrences: int
    first_seen: str
    last_seen: str
    log_levels: List[str]
    sources: List[str]
    sample_messages: List[str] = Field(default_factory=list, max_length=5)
    frequency_per_hour: float = 0.0
    is_error_pattern: bool = False
    is_anomaly: bool = False


class LogAnomaly(BaseModel):
    """Represents a detected anomaly in logs"""

    anomaly_id: str
    anomaly_type: str  # spike, gap, new_pattern, error_surge
    severity: str  # critical, high, medium, low
    description: str
    timestamp: str
    affected_sources: List[str]
    metric_before: float
    metric_after: float
    confidence: float


class LogTrend(BaseModel):
    """Represents a trend in log data"""

    trend_id: str
    metric_name: str
    direction: str  # increasing, decreasing, stable
    change_percent: float
    time_period: str
    data_points: List[Dict[str, Any]]


class PatternMiningResult(BaseModel):
    """Result of pattern mining operation"""

    patterns: List[LogPattern]
    anomalies: List[LogAnomaly]
    trends: List[LogTrend]
    summary: Dict[str, Any]
    analysis_time_ms: float
    logs_analyzed: int


# ============================================================================
# Pattern Mining Engine
# ============================================================================


class LogPatternMiner:
    """Engine for mining patterns from log data"""

    # Common log patterns to detect
    KNOWN_PATTERNS = [
        (
            r"ERROR.*?connection.*?refused",
            "connection_refused",
            "Connection refused errors",
        ),
        (r"ERROR.*?timeout", "timeout_error", "Timeout errors"),
        (r"ERROR.*?memory", "memory_error", "Memory-related errors"),
        (r"WARNING.*?deprecated", "deprecation_warning", "Deprecation warnings"),
        (r"ERROR.*?authentication", "auth_error", "Authentication failures"),
        (
            r"ERROR.*?permission.*?denied",
            "permission_error",
            "Permission denied errors",
        ),
        (r"ERROR.*?disk.*?space", "disk_space_error", "Disk space issues"),
        (r"ERROR.*?database", "database_error", "Database errors"),
        (r"ERROR.*?network", "network_error", "Network errors"),
        (r"WARNING.*?retry", "retry_warning", "Retry attempts"),
        (r"ERROR.*?exception", "exception_error", "Exception errors"),
        (r"ERROR.*?failed", "generic_failure", "Generic failures"),
        (r"INFO.*?started", "service_start", "Service start events"),
        (r"INFO.*?stopped", "service_stop", "Service stop events"),
        (r"INFO.*?request.*?completed", "request_complete", "Request completions"),
    ]

    # Variable parts to normalize in log messages
    VARIABLE_PATTERNS = [
        (r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>"),
        (r"\b\d+\.\d+\.\d+\.\d+\b", "<IP>"),
        (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>"),
        (r"\b[0-9a-f]{24,}\b", "<HEX_ID>"),
        (r'"/[^"]*"', '"<PATH>"'),
        (r"\b\d{5,}\b", "<NUM>"),
        (r"\b\d+ms\b", "<DURATION>"),
        (r"\b\d+\s*(KB|MB|GB|bytes)\b", "<SIZE>"),
    ]

    def __init__(self):
        """Initialize log pattern analyzer with empty pattern cache."""
        self.pattern_cache: Dict[str, LogPattern] = {}

    def normalize_message(self, message: str) -> str:
        """Normalize a log message by replacing variable parts with placeholders"""
        normalized = message
        for pattern, replacement in self.VARIABLE_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    def extract_log_level(self, line: str) -> str:
        """Extract log level from a log line"""
        line_upper = line.upper()
        for level in LOG_LEVEL_PRIORITIES:
            if level in line_upper:
                return "WARNING" if level == "WARN" else level
        return "INFO"

    def extract_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from a log line"""
        # Try common timestamp formats
        patterns = [
            r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})",
            r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    ts_str = match.group(1).replace("T", " ")
                    return datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
        return None

    def categorize_pattern(self, normalized: str) -> Tuple[str, str]:
        """Categorize a normalized log pattern"""
        for regex, pattern_id, description in self.KNOWN_PATTERNS:
            if re.search(regex, normalized, re.IGNORECASE):
                return pattern_id, description
        # Generate hash-based ID for unknown patterns
        pattern_hash = hex(hash(normalized[:100]) & 0xFFFFFFFF)[2:]
        return f"pattern_{pattern_hash}", "Auto-discovered pattern"

    async def mine_patterns(
        self,
        log_lines: List[Tuple[str, str, str]],  # (line, source, raw_timestamp)
        min_occurrences: int = 2,
    ) -> List[LogPattern]:
        """Mine patterns from log lines (Issue #665: refactored with helpers)."""
        pattern_data = self._collect_pattern_data(log_lines)

        # Convert to LogPattern objects
        patterns = [
            self._build_log_pattern(pattern_id, data)
            for pattern_id, data in pattern_data.items()
            if data["occurrences"] >= min_occurrences
        ]

        # Sort by occurrences
        patterns.sort(key=lambda p: p.occurrences, reverse=True)
        return patterns

    def _collect_pattern_data(
        self, log_lines: List[Tuple[str, str, str]]
    ) -> Dict[str, Dict]:
        """Collect pattern data from log lines (Issue #665: extracted helper)."""
        pattern_data: Dict[str, Dict] = defaultdict(
            lambda: {
                "occurrences": 0,
                "first_seen": None,
                "last_seen": None,
                "levels": set(),
                "sources": set(),
                "samples": [],
                "timestamps": [],
            }
        )

        for line, source, _ in log_lines:  # Issue #382: raw_ts unused
            normalized = self.normalize_message(line)
            level = self.extract_log_level(line)
            timestamp = self.extract_timestamp(line)

            pattern_id, _ = self.categorize_pattern(normalized)
            data = pattern_data[pattern_id]

            data["occurrences"] += 1
            data["levels"].add(level)
            data["sources"].add(source)
            data["template"] = normalized[:200]

            if timestamp:
                data["timestamps"].append(timestamp)
                if data["first_seen"] is None or timestamp < data["first_seen"]:
                    data["first_seen"] = timestamp
                if data["last_seen"] is None or timestamp > data["last_seen"]:
                    data["last_seen"] = timestamp

            if len(data["samples"]) < 5:
                data["samples"].append(line[:300])

        return pattern_data

    def _build_log_pattern(self, pattern_id: str, data: Dict) -> LogPattern:
        """Build LogPattern from collected data (Issue #665: extracted helper)."""
        # Calculate frequency per hour
        freq_per_hour = 0.0
        if data["first_seen"] and data["last_seen"]:
            duration = (data["last_seen"] - data["first_seen"]).total_seconds()
            if duration > 0:
                freq_per_hour = data["occurrences"] / (duration / 3600)

        is_error = any(level in ERROR_LEVELS for level in data["levels"])  # Issue #326

        return LogPattern(
            pattern_id=pattern_id,
            pattern_template=data.get("template", "Unknown"),
            occurrences=data["occurrences"],
            first_seen=(
                data["first_seen"].isoformat()
                if data["first_seen"]
                else datetime.now().isoformat()
            ),
            last_seen=(
                data["last_seen"].isoformat()
                if data["last_seen"]
                else datetime.now().isoformat()
            ),
            log_levels=list(data["levels"]),
            sources=list(data["sources"]),
            sample_messages=data["samples"],
            frequency_per_hour=round(freq_per_hour, 2),
            is_error_pattern=is_error,
            is_anomaly=False,
        )

    def _create_anomaly(
        self,
        anomaly_id: str,
        anomaly_type: str,
        severity: str,
        description: str,
        timestamp: str,
        affected_sources: List[str],
        metric_before: float,
        metric_after: float,
        confidence: float,
    ) -> LogAnomaly:
        """
        Create a LogAnomaly object with the given parameters.

        Issue #281: Extracted helper to reduce repetition in detect_anomalies.
        """
        return LogAnomaly(
            anomaly_id=anomaly_id,
            anomaly_type=anomaly_type,
            severity=severity,
            description=description,
            timestamp=timestamp,
            affected_sources=affected_sources,
            metric_before=metric_before,
            metric_after=metric_after,
            confidence=confidence,
        )

    def _detect_error_spikes(
        self,
        error_counts: Dict[str, int],
        hourly_counts: Dict[str, Dict[str, int]],
    ) -> List[LogAnomaly]:
        """
        Detect error spike anomalies in log data.

        Issue #665: Extracted from detect_anomalies to reduce function length.

        Args:
            error_counts: Error counts by hour
            hourly_counts: All log counts by hour and source

        Returns:
            List of error spike anomalies
        """
        anomalies = []
        if not error_counts:
            return anomalies

        avg_errors = sum(error_counts.values()) / len(error_counts)
        for hour, count in error_counts.items():
            if count > avg_errors * 3 and count > 5:  # 3x average and >5 errors
                anomalies.append(
                    self._create_anomaly(
                        anomaly_id=f"error_spike_{hour}",
                        anomaly_type="error_surge",
                        severity="high" if count > avg_errors * 5 else "medium",
                        description=f"Error spike detected: {count} errors vs {avg_errors:.1f} average",
                        timestamp=hour,
                        affected_sources=list(
                            set(s for lines in hourly_counts.values() for s in lines)
                        ),
                        metric_before=avg_errors,
                        metric_after=float(count),
                        confidence=min(0.95, 0.5 + (count / avg_errors) * 0.1),
                    )
                )
        return anomalies

    def _detect_new_error_patterns(
        self,
        patterns: List[LogPattern],
    ) -> List[LogAnomaly]:
        """
        Detect new high-frequency error pattern anomalies.

        Issue #665: Extracted from detect_anomalies to reduce function length.

        Args:
            patterns: List of log patterns to analyze

        Returns:
            List of new pattern anomalies
        """
        anomalies = []
        for pattern in patterns:
            if pattern.occurrences >= 10 and pattern.frequency_per_hour > 50:
                if pattern.is_error_pattern:
                    anomalies.append(
                        self._create_anomaly(
                            anomaly_id=f"new_error_{pattern.pattern_id}",
                            anomaly_type="new_pattern",
                            severity="high",
                            description=f"High-frequency error pattern detected: {pattern.pattern_template[:100]}",
                            timestamp=pattern.first_seen,
                            affected_sources=pattern.sources,
                            metric_before=0,
                            metric_after=pattern.frequency_per_hour,
                            confidence=0.85,
                        )
                    )
        return anomalies

    def _detect_log_gaps(
        self,
        hourly_counts: Dict[str, Dict[str, int]],
    ) -> List[LogAnomaly]:
        """
        Detect log gap anomalies (periods with no logs).

        Issue #665: Extracted from detect_anomalies to reduce function length.

        Args:
            hourly_counts: Log counts by hour and source

        Returns:
            List of log gap anomalies
        """
        anomalies = []
        if not hourly_counts:
            return anomalies

        hours = sorted(hourly_counts)
        for i in range(1, len(hours)):
            prev_hour = datetime.strptime(hours[i - 1], "%Y-%m-%d %H:00")
            curr_hour = datetime.strptime(hours[i], "%Y-%m-%d %H:00")
            gap = (curr_hour - prev_hour).total_seconds() / 3600

            if gap > 2:  # More than 2 hours gap
                anomalies.append(
                    self._create_anomaly(
                        anomaly_id=f"log_gap_{hours[i-1]}",
                        anomaly_type="gap",
                        severity="medium" if gap < 6 else "high",
                        description=f"Log gap detected: {gap:.1f} hours without logs",
                        timestamp=hours[i - 1],
                        affected_sources=list(hourly_counts[hours[i - 1]].keys()),
                        metric_before=sum(hourly_counts[hours[i - 1]].values()),
                        metric_after=0,
                        confidence=0.9,
                    )
                )
        return anomalies

    def detect_anomalies(
        self, log_lines: List[Tuple[str, str, str]], patterns: List[LogPattern]
    ) -> List[LogAnomaly]:
        """
        Detect anomalies in log data.

        Issue #665: Refactored to use extracted helper methods for each
        anomaly type detection.

        Args:
            log_lines: List of (line, source, context) tuples
            patterns: List of detected log patterns

        Returns:
            List of detected anomalies
        """
        # Group logs by hour for spike detection
        hourly_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        error_counts: Dict[str, int] = defaultdict(int)

        for line, source, _ in log_lines:
            ts = self.extract_timestamp(line)
            if ts:
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                hourly_counts[hour_key][source] += 1

                level = self.extract_log_level(line)
                if level in ERROR_LEVELS:  # O(1) lookup (Issue #326)
                    error_counts[hour_key] += 1

        # Issue #665: Use extracted helpers for each anomaly type
        anomalies = []
        anomalies.extend(self._detect_error_spikes(error_counts, hourly_counts))
        anomalies.extend(self._detect_new_error_patterns(patterns))
        anomalies.extend(self._detect_log_gaps(hourly_counts))

        return anomalies

    def _calculate_trend_direction(
        self,
        values: List[float],
        change_threshold: float = 10.0,
    ) -> Tuple[str, float]:
        """
        Calculate trend direction and change percent from time series values.

        Issue #281: Extracted helper to reduce repetition in analyze_trends.

        Args:
            values: Time series values to analyze
            change_threshold: Percent change threshold for direction (default: 10%)

        Returns:
            Tuple of (direction, change_percent) where direction is
            'increasing', 'decreasing', or 'stable'
        """
        if len(values) < 2:
            return ("stable", 0.0)

        # Split into halves and calculate averages
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / max(1, mid)
        second_half_avg = sum(values[mid:]) / max(1, len(values) - mid)

        # Calculate change percent
        if first_half_avg > 0:
            change = ((second_half_avg - first_half_avg) / first_half_avg) * 100
        else:
            change = 100.0 if second_half_avg > 0 else 0.0

        # Determine direction
        if change > change_threshold:
            direction = "increasing"
        elif change < -change_threshold:
            direction = "decreasing"
        else:
            direction = "stable"

        return (direction, round(change, 1))

    def _build_hourly_log_data(
        self, log_lines: List[Tuple[str, str, str]]
    ) -> Dict[str, Dict[str, int]]:
        """
        Group log lines by hour with counts (Issue #665: extracted helper).
        """
        hourly_data: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "errors": 0, "warnings": 0}
        )
        for line, source, _ in log_lines:
            ts = self.extract_timestamp(line)
            if ts:
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                hourly_data[hour_key]["total"] += 1
                level = self.extract_log_level(line)
                if level in ERROR_LEVELS:
                    hourly_data[hour_key]["errors"] += 1
                elif level == "WARNING":
                    hourly_data[hour_key]["warnings"] += 1
        return hourly_data

    def _build_volume_trend(
        self, hourly_data: Dict[str, Dict[str, int]], hours: List[str]
    ) -> Optional[LogTrend]:
        """
        Build log volume trend (Issue #665: extracted helper).
        """
        totals = [float(hourly_data[h]["total"]) for h in hours]
        if not totals:
            return None
        direction, change = self._calculate_trend_direction(
            totals, change_threshold=10.0
        )
        return LogTrend(
            trend_id="log_volume",
            metric_name="Total Log Volume",
            direction=direction,
            change_percent=change,
            time_period=f"{hours[0]} to {hours[-1]}",
            data_points=[
                {"hour": h, "count": hourly_data[h]["total"]} for h in hours[-24:]
            ],
        )

    def _build_error_rate_trend(
        self, hourly_data: Dict[str, Dict[str, int]], hours: List[str]
    ) -> Optional[LogTrend]:
        """
        Build error rate trend (Issue #665: extracted helper).
        """
        error_rates = [
            (
                hourly_data[h]["errors"] / hourly_data[h]["total"] * 100
                if hourly_data[h]["total"] > 0
                else 0.0
            )
            for h in hours
        ]
        if not error_rates:
            return None
        direction, change = self._calculate_trend_direction(
            error_rates, change_threshold=20.0
        )
        return LogTrend(
            trend_id="error_rate",
            metric_name="Error Rate",
            direction=direction,
            change_percent=change,
            time_period=f"{hours[0]} to {hours[-1]}",
            data_points=[
                {
                    "hour": h,
                    "error_rate": round(
                        (
                            hourly_data[h]["errors"] / hourly_data[h]["total"] * 100
                            if hourly_data[h]["total"] > 0
                            else 0
                        ),
                        2,
                    ),
                }
                for h in hours[-24:]
            ],
        )

    def analyze_trends(self, log_lines: List[Tuple[str, str, str]]) -> List[LogTrend]:
        """
        Analyze trends in log data.

        Issue #665: Refactored to use extracted helpers.
        """
        hourly_data = self._build_hourly_log_data(log_lines)
        if len(hourly_data) < 3:
            return []

        hours = sorted(hourly_data)
        trends = []

        volume_trend = self._build_volume_trend(hourly_data, hours)
        if volume_trend:
            trends.append(volume_trend)

        error_trend = self._build_error_rate_trend(hourly_data, hours)
        if error_trend:
            trends.append(error_trend)

        return trends


# Global miner instance
pattern_miner = LogPatternMiner()


# =============================================================================
# Log Processing Helpers (Issue #298, #315 - Reduce Deep Nesting)
# =============================================================================


def _filter_log_line(
    line: str,
    cutoff_time: Optional[datetime],
) -> Optional[Tuple[str, datetime]]:
    """Filter a single log line by timestamp (Issue #315 - extracted)."""
    if not line.strip():
        return None

    ts = pattern_miner.extract_timestamp(line)
    if cutoff_time and ts and ts < cutoff_time:
        return None

    if ts:
        return (line.strip(), ts)
    return None


async def _read_log_lines(
    file_path: Path,
    cutoff_time: Optional[datetime] = None,
    max_lines: Optional[int] = None,
) -> List[Tuple[str, datetime]]:
    """
    Read log lines from a file, filtering by timestamp.

    Returns list of (line, timestamp) tuples.
    """
    result = []
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            lines = content.splitlines()
            if max_lines:
                lines = lines[-max_lines:]

            for line in lines:
                filtered = _filter_log_line(line, cutoff_time)
                if filtered:
                    result.append(filtered)

    except OSError as e:
        logger.warning("Failed to read %s: %s", file_path, e)
    except Exception as e:
        logger.warning("Error reading %s: %s", file_path, e)

    return result


def _should_include_log_line(
    line: str, cutoff_time: Optional[datetime], pattern_filter: Optional[str]
) -> bool:
    """Check if a log line should be included. (Issue #315 - extracted)"""
    if not line.strip():
        return False
    ts = pattern_miner.extract_timestamp(line)
    if cutoff_time and ts and ts < cutoff_time:
        return False
    if pattern_filter:
        normalized = pattern_miner.normalize_message(line)
        pid, _ = pattern_miner.categorize_pattern(normalized)
        if pid != pattern_filter:
            return False
    return True


async def _read_log_lines_with_source(
    file_path: Path,
    cutoff_time: Optional[datetime] = None,
    source_filter: Optional[set] = None,
    pattern_filter: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    """
    Read log lines with source info, optional pattern filtering (Issue #315).

    Returns list of (line, source, raw_timestamp) tuples.
    """
    file_name = file_path.stem
    if source_filter and file_name not in source_filter:
        return []

    result = []
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            # Filter lines using helper (Issue #315 - reduced depth)
            for line in content.splitlines():
                if _should_include_log_line(line, cutoff_time, pattern_filter):
                    result.append((line.strip(), file_name, ""))

    except OSError as e:
        logger.warning("Failed to read %s: %s", file_path, e)
    except Exception as e:
        logger.warning("Error reading %s: %s", file_path, e)

    return result


async def _collect_all_log_lines(
    log_dir: Path,
    cutoff_time: datetime,
    source_filter: Optional[set] = None,
    pattern_filter: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    """Collect log lines from all log files in directory (Issue #315)."""
    all_lines: List[Tuple[str, str, str]] = []

    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(log_dir.exists):
        return all_lines

    # Issue #358 - avoid blocking with lambda for proper glob() execution in thread
    log_files = await asyncio.to_thread(lambda: list(log_dir.glob("*.log")))
    for file_path in log_files:
        file_lines = await _read_log_lines_with_source(
            file_path, cutoff_time, source_filter, pattern_filter
        )
        all_lines.extend(file_lines)

    return all_lines


def _process_error_hotspot_line(
    line: str,
    ts: datetime,
    hourly_errors: Dict[str, Dict],
) -> None:
    """Process a single log line for error hotspot analysis."""
    hour_key = ts.strftime("%Y-%m-%d %H:00")
    hourly_errors[hour_key]["total"] += 1

    level = pattern_miner.extract_log_level(line)
    if level in ERROR_LEVELS:  # Issue #326
        hourly_errors[hour_key]["errors"] += 1
        if len(hourly_errors[hour_key]["samples"]) < 5:
            hourly_errors[hour_key]["samples"].append(line[:200])


def _build_recent_log_entry(line: str, ts: datetime, source: str) -> Dict:
    """Build a recent log entry dictionary."""
    return {
        "timestamp": ts.isoformat(),
        "level": pattern_miner.extract_log_level(line),
        "source": source,
        "message": line[:200],
    }


async def _collect_log_files(
    log_dir: Path,
    pattern: str = "*.log",
) -> List[Path]:
    """Collect log file paths from directory."""
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(log_dir.exists):
        return []
    # Issue #358 - use lambda for proper glob() execution in thread
    return await asyncio.to_thread(lambda: list(log_dir.glob(pattern)))


# =============================================================================
# End of Log Processing Helpers
# =============================================================================


# ============================================================================
# API Endpoints
# ============================================================================


def _build_empty_mining_result(analysis_time_ms: float) -> PatternMiningResult:
    """Build empty result for when no logs are found (Issue #315)."""
    return PatternMiningResult(
        patterns=[],
        anomalies=[],
        trends=[],
        summary={
            "total_logs": 0,
            "unique_patterns": 0,
            "error_patterns": 0,
            "anomalies_detected": 0,
        },
        analysis_time_ms=analysis_time_ms,
        logs_analyzed=0,
    )


def _build_mining_summary(
    log_lines: List[Tuple[str, str, str]],
    patterns: List[LogPattern],
    anomalies: List[LogAnomaly],
    trends: List[LogTrend],
    hours: int,
) -> Dict[str, Any]:
    """Build summary dict for pattern mining result (Issue #315)."""
    error_patterns = len([p for p in patterns if p.is_error_pattern])
    return {
        "total_logs": len(log_lines),
        "unique_patterns": len(patterns),
        "error_patterns": error_patterns,
        "warning_patterns": len([p for p in patterns if "WARNING" in p.log_levels]),
        "anomalies_detected": len(anomalies),
        "trends_detected": len(trends),
        "sources_analyzed": list(set(line[1] for line in log_lines)),
        "time_range_hours": hours,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mine_log_patterns",
    error_code_prefix="LOGPAT",
)
@router.get("/mine", response_model=PatternMiningResult)
async def mine_log_patterns(
    sources: Optional[str] = Query(None, description="Comma-separated log sources"),
    hours: int = Query(24, ge=1, le=168, description="Hours of logs to analyze"),
    min_occurrences: int = Query(
        2, ge=1, le=100, description="Minimum pattern occurrences"
    ),
    include_anomalies: bool = Query(True, description="Include anomaly detection"),
    include_trends: bool = Query(True, description="Include trend analysis"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Mine patterns from log files.

    Discovers recurring patterns, detects anomalies, and analyzes trends
    in log data from the specified time period.

    Issue #744: Requires admin authentication.
    """
    import time

    start_time = time.time()

    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        source_filter = set(sources.split(",")) if sources else None

        # Use extracted helper for log collection (Issue #315)
        log_lines = await _collect_all_log_lines(LOG_DIR, cutoff_time, source_filter)

        if not log_lines:
            return _build_empty_mining_result(
                round((time.time() - start_time) * 1000, 2)
            )

        # Mine patterns
        patterns = await pattern_miner.mine_patterns(log_lines, min_occurrences)

        # Detect anomalies
        anomalies = (
            pattern_miner.detect_anomalies(log_lines, patterns)
            if include_anomalies
            else []
        )

        # Analyze trends
        trends = pattern_miner.analyze_trends(log_lines) if include_trends else []

        # Build summary using extracted helper
        summary = _build_mining_summary(log_lines, patterns, anomalies, trends, hours)

        return PatternMiningResult(
            patterns=patterns[:50],  # Limit to top 50 patterns
            anomalies=anomalies,
            trends=trends,
            summary=summary,
            analysis_time_ms=round((time.time() - start_time) * 1000, 2),
            logs_analyzed=len(log_lines),
        )

    except Exception as e:
        logger.error("Error mining log patterns: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_pattern_lines(
    log_lines: List[Tuple[str, str, str]],
) -> Tuple[List[datetime], Counter, Counter, Counter]:
    """Analyze matching log lines for pattern details (Issue #315)."""
    timestamps = []
    levels: Counter = Counter()
    sources: Counter = Counter()
    hourly_dist: Counter = Counter()

    for line, source, _ in log_lines:
        ts = pattern_miner.extract_timestamp(line)
        if ts:
            timestamps.append(ts)
            hourly_dist[ts.strftime("%Y-%m-%d %H:00")] += 1

        levels[pattern_miner.extract_log_level(line)] += 1
        sources[source] += 1

    return timestamps, levels, sources, hourly_dist


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_details",
    error_code_prefix="LOGPAT",
)
@router.get("/pattern/{pattern_id}")
async def get_pattern_details(
    pattern_id: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of logs to search"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get detailed information about a specific pattern.

    Issue #744: Requires admin authentication.
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Use extracted helper with pattern filter (Issue #315)
        log_lines = await _collect_all_log_lines(
            LOG_DIR, cutoff_time, pattern_filter=pattern_id
        )

        if not log_lines:
            raise HTTPException(
                status_code=404, detail=f"Pattern '{pattern_id}' not found"
            )

        # Analyze matching lines using extracted helper
        timestamps, levels, sources, hourly_dist = _analyze_pattern_lines(log_lines)

        return {
            "pattern_id": pattern_id,
            "total_occurrences": len(log_lines),
            "first_seen": min(timestamps).isoformat() if timestamps else None,
            "last_seen": max(timestamps).isoformat() if timestamps else None,
            "level_distribution": dict(levels),
            "source_distribution": dict(sources),
            "hourly_distribution": dict(sorted(hourly_dist.items())),
            "sample_messages": [line[0][:500] for line in log_lines[:20]],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting pattern details: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_hotspots",
    error_code_prefix="LOGPAT",
)
@router.get("/hotspots")
async def get_error_hotspots(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    limit: int = Query(10, ge=1, le=50, description="Number of hotspots to return"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get error hotspots - time periods with highest error rates.

    Issue #744: Requires admin authentication.
    """
    try:
        hourly_errors: Dict[str, Dict] = defaultdict(
            lambda: {"errors": 0, "total": 0, "samples": []}
        )
        cutoff_time = datetime.now() - timedelta(hours=hours)

        log_files = await _collect_log_files(LOG_DIR)
        for file_path in log_files:
            log_lines = await _read_log_lines(file_path, cutoff_time)
            for line, ts in log_lines:
                _process_error_hotspot_line(line, ts, hourly_errors)

        # Calculate error rates and find hotspots
        hotspots = []
        for hour, data in hourly_errors.items():
            if data["total"] > 0:
                error_rate = (data["errors"] / data["total"]) * 100
                hotspots.append(
                    {
                        "hour": hour,
                        "error_count": data["errors"],
                        "total_logs": data["total"],
                        "error_rate": round(error_rate, 2),
                        "sample_errors": data["samples"],
                    }
                )

        # Sort by error count and return top N
        hotspots.sort(key=lambda x: x["error_count"], reverse=True)

        return {
            "hotspots": hotspots[:limit],
            "total_hours_analyzed": len(hourly_errors),
            "time_range_hours": hours,
        }

    except Exception as e:
        logger.error("Error getting error hotspots: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _aggregate_log_stats(
    log_lines: List[Tuple[str, str, str]],
) -> Tuple[int, Counter, Counter, Counter, List[datetime]]:
    """Aggregate statistics from log lines (Issue #315)."""
    total = 0
    by_level: Counter = Counter()
    by_source: Counter = Counter()
    by_hour: Counter = Counter()
    timestamps = []

    for line, source, _ in log_lines:
        ts = pattern_miner.extract_timestamp(line)
        if ts:
            total += 1
            by_level[pattern_miner.extract_log_level(line)] += 1
            by_source[source] += 1
            by_hour[ts.strftime("%H:00")] += 1
            timestamps.append(ts)

    return total, by_level, by_source, by_hour, timestamps


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_log_stats",
    error_code_prefix="LOGPAT",
)
@router.get("/stats")
async def get_log_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """Get overall log statistics.

    Issue #744: Requires admin authentication.
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Use extracted helper for log collection (Issue #315)
        log_lines = await _collect_all_log_lines(LOG_DIR, cutoff_time)

        # Aggregate stats using extracted helper
        total, by_level, by_source, by_hour, timestamps = _aggregate_log_stats(
            log_lines
        )

        earliest = min(timestamps).isoformat() if timestamps else None
        latest = max(timestamps).isoformat() if timestamps else None

        return {
            "total_logs": total,
            "level_distribution": dict(by_level),
            "source_distribution": dict(by_source),
            "hourly_distribution": dict(sorted(by_hour.items())),
            "earliest_log": earliest,
            "latest_log": latest,
            "time_range_hours": hours,
            "avg_logs_per_hour": round(total / hours, 1) if total > 0 else 0,
        }

    except Exception as e:
        logger.error("Error getting log stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_realtime_summary",
    error_code_prefix="LOGPAT",
)
@router.get("/realtime")
async def get_realtime_summary(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get real-time log summary for last 5 minutes.

    Issue #744: Requires admin authentication.
    """
    try:
        cutoff = datetime.now() - timedelta(minutes=5)
        recent_logs = []

        log_files = await _collect_log_files(LOG_DIR)
        for file_path in log_files:
            log_lines = await _read_log_lines(file_path, cutoff, max_lines=500)
            for line, ts in log_lines:
                recent_logs.append(_build_recent_log_entry(line, ts, file_path.stem))

        # Sort by timestamp
        recent_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # Calculate summary
        level_counts = Counter(log["level"] for log in recent_logs)

        return {
            "logs_last_5min": len(recent_logs),
            "level_counts": dict(level_counts),
            "error_count": level_counts.get("ERROR", 0)
            + level_counts.get("CRITICAL", 0),
            "recent_errors": [
                log for log in recent_logs if log["level"] in ERROR_LEVELS  # Issue #326
            ][:10],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Error getting realtime summary: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
