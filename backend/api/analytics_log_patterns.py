# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dynamic Pattern Mining from Logs API (Issue #226)
Provides endpoints for discovering patterns, anomalies, and trends in log data
"""

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/log-patterns", tags=["log-patterns", "analytics"])

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"


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
        (r"ERROR.*?permission.*?denied", "permission_error", "Permission denied errors"),
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
        for level in ["CRITICAL", "ERROR", "WARNING", "WARN", "INFO", "DEBUG"]:
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
        """Mine patterns from log lines"""
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

        for line, source, raw_ts in log_lines:
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

        # Convert to LogPattern objects
        patterns = []
        for pattern_id, data in pattern_data.items():
            if data["occurrences"] < min_occurrences:
                continue

            # Calculate frequency per hour
            freq_per_hour = 0.0
            if data["first_seen"] and data["last_seen"]:
                duration = (data["last_seen"] - data["first_seen"]).total_seconds()
                if duration > 0:
                    freq_per_hour = data["occurrences"] / (duration / 3600)

            is_error = any(l in ["ERROR", "CRITICAL"] for l in data["levels"])

            patterns.append(
                LogPattern(
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
            )

        # Sort by occurrences
        patterns.sort(key=lambda p: p.occurrences, reverse=True)
        return patterns

    def detect_anomalies(
        self, log_lines: List[Tuple[str, str, str]], patterns: List[LogPattern]
    ) -> List[LogAnomaly]:
        """Detect anomalies in log data"""
        anomalies = []

        # Group logs by hour for spike detection
        hourly_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        error_counts: Dict[str, int] = defaultdict(int)

        for line, source, _ in log_lines:
            ts = self.extract_timestamp(line)
            if ts:
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                hourly_counts[hour_key][source] += 1

                level = self.extract_log_level(line)
                if level in ["ERROR", "CRITICAL"]:
                    error_counts[hour_key] += 1

        # Detect error spikes
        if error_counts:
            avg_errors = sum(error_counts.values()) / len(error_counts)
            for hour, count in error_counts.items():
                if count > avg_errors * 3 and count > 5:  # 3x average and >5 errors
                    anomalies.append(
                        LogAnomaly(
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

        # Detect sudden pattern appearances (new patterns)
        for pattern in patterns:
            if pattern.occurrences >= 10 and pattern.frequency_per_hour > 50:
                if pattern.is_error_pattern:
                    anomalies.append(
                        LogAnomaly(
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

        # Detect log gaps (periods with no logs)
        if hourly_counts:
            hours = sorted(hourly_counts.keys())
            for i in range(1, len(hours)):
                prev_hour = datetime.strptime(hours[i - 1], "%Y-%m-%d %H:00")
                curr_hour = datetime.strptime(hours[i], "%Y-%m-%d %H:00")
                gap = (curr_hour - prev_hour).total_seconds() / 3600

                if gap > 2:  # More than 2 hours gap
                    anomalies.append(
                        LogAnomaly(
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

    def analyze_trends(
        self, log_lines: List[Tuple[str, str, str]]
    ) -> List[LogTrend]:
        """Analyze trends in log data"""
        trends = []

        # Group by hour
        hourly_data: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "errors": 0, "warnings": 0}
        )

        for line, source, _ in log_lines:
            ts = self.extract_timestamp(line)
            if ts:
                hour_key = ts.strftime("%Y-%m-%d %H:00")
                hourly_data[hour_key]["total"] += 1

                level = self.extract_log_level(line)
                if level in ["ERROR", "CRITICAL"]:
                    hourly_data[hour_key]["errors"] += 1
                elif level == "WARNING":
                    hourly_data[hour_key]["warnings"] += 1

        if len(hourly_data) < 3:
            return trends

        hours = sorted(hourly_data.keys())

        # Analyze total log volume trend
        totals = [hourly_data[h]["total"] for h in hours]
        if len(totals) >= 2:
            first_half = sum(totals[: len(totals) // 2]) / max(1, len(totals) // 2)
            second_half = sum(totals[len(totals) // 2 :]) / max(
                1, len(totals) - len(totals) // 2
            )

            if first_half > 0:
                change = ((second_half - first_half) / first_half) * 100
                direction = (
                    "increasing" if change > 10 else "decreasing" if change < -10 else "stable"
                )

                trends.append(
                    LogTrend(
                        trend_id="log_volume",
                        metric_name="Total Log Volume",
                        direction=direction,
                        change_percent=round(change, 1),
                        time_period=f"{hours[0]} to {hours[-1]}",
                        data_points=[
                            {"hour": h, "count": hourly_data[h]["total"]} for h in hours[-24:]
                        ],
                    )
                )

        # Analyze error rate trend
        error_rates = [
            (
                hourly_data[h]["errors"] / hourly_data[h]["total"] * 100
                if hourly_data[h]["total"] > 0
                else 0
            )
            for h in hours
        ]
        if len(error_rates) >= 2:
            first_half_err = sum(error_rates[: len(error_rates) // 2]) / max(
                1, len(error_rates) // 2
            )
            second_half_err = sum(error_rates[len(error_rates) // 2 :]) / max(
                1, len(error_rates) - len(error_rates) // 2
            )

            if first_half_err > 0:
                err_change = ((second_half_err - first_half_err) / first_half_err) * 100
            else:
                err_change = 100 if second_half_err > 0 else 0

            err_direction = (
                "increasing"
                if err_change > 20
                else "decreasing" if err_change < -20 else "stable"
            )

            trends.append(
                LogTrend(
                    trend_id="error_rate",
                    metric_name="Error Rate",
                    direction=err_direction,
                    change_percent=round(err_change, 1),
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
            )

        return trends


# Global miner instance
pattern_miner = LogPatternMiner()


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mine_log_patterns",
    error_code_prefix="LOGPAT",
)
@router.get("/mine", response_model=PatternMiningResult)
async def mine_log_patterns(
    sources: Optional[str] = Query(None, description="Comma-separated log sources"),
    hours: int = Query(24, ge=1, le=168, description="Hours of logs to analyze"),
    min_occurrences: int = Query(2, ge=1, le=100, description="Minimum pattern occurrences"),
    include_anomalies: bool = Query(True, description="Include anomaly detection"),
    include_trends: bool = Query(True, description="Include trend analysis"),
):
    """
    Mine patterns from log files.

    Discovers recurring patterns, detects anomalies, and analyzes trends
    in log data from the specified time period.
    """
    import time

    start_time = time.time()

    try:
        log_lines: List[Tuple[str, str, str]] = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Parse sources filter
        source_filter = set()
        if sources:
            source_filter = set(sources.split(","))

        # Read log files
        if LOG_DIR.exists():
            for file_path in LOG_DIR.glob("*.log"):
                file_name = file_path.stem
                if source_filter and file_name not in source_filter:
                    continue

                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        for line in content.splitlines():
                            if not line.strip():
                                continue

                            # Check if line is within time window
                            ts = pattern_miner.extract_timestamp(line)
                            if ts and ts < cutoff_time:
                                continue

                            log_lines.append((line.strip(), file_name, ""))
                except Exception as e:
                    logger.warning(f"Error reading log file {file_path}: {e}")

        if not log_lines:
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
                analysis_time_ms=round((time.time() - start_time) * 1000, 2),
                logs_analyzed=0,
            )

        # Mine patterns
        patterns = await pattern_miner.mine_patterns(log_lines, min_occurrences)

        # Detect anomalies
        anomalies = []
        if include_anomalies:
            anomalies = pattern_miner.detect_anomalies(log_lines, patterns)

        # Analyze trends
        trends = []
        if include_trends:
            trends = pattern_miner.analyze_trends(log_lines)

        # Build summary
        error_patterns = len([p for p in patterns if p.is_error_pattern])
        summary = {
            "total_logs": len(log_lines),
            "unique_patterns": len(patterns),
            "error_patterns": error_patterns,
            "warning_patterns": len(
                [p for p in patterns if "WARNING" in p.log_levels]
            ),
            "anomalies_detected": len(anomalies),
            "trends_detected": len(trends),
            "sources_analyzed": list(set(l[1] for l in log_lines)),
            "time_range_hours": hours,
        }

        return PatternMiningResult(
            patterns=patterns[:50],  # Limit to top 50 patterns
            anomalies=anomalies,
            trends=trends,
            summary=summary,
            analysis_time_ms=round((time.time() - start_time) * 1000, 2),
            logs_analyzed=len(log_lines),
        )

    except Exception as e:
        logger.error(f"Error mining log patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pattern_details",
    error_code_prefix="LOGPAT",
)
@router.get("/pattern/{pattern_id}")
async def get_pattern_details(
    pattern_id: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of logs to search"),
):
    """Get detailed information about a specific pattern"""
    try:
        log_lines: List[Tuple[str, str, str]] = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Read all log files
        if LOG_DIR.exists():
            for file_path in LOG_DIR.glob("*.log"):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        for line in content.splitlines():
                            if not line.strip():
                                continue

                            ts = pattern_miner.extract_timestamp(line)
                            if ts and ts < cutoff_time:
                                continue

                            # Check if this line matches the pattern
                            normalized = pattern_miner.normalize_message(line)
                            pid, _ = pattern_miner.categorize_pattern(normalized)
                            if pid == pattern_id:
                                log_lines.append((line.strip(), file_path.stem, ""))
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")

        if not log_lines:
            raise HTTPException(
                status_code=404, detail=f"Pattern '{pattern_id}' not found"
            )

        # Analyze matching lines
        timestamps = []
        levels = Counter()
        sources = Counter()
        hourly_dist = Counter()

        for line, source, _ in log_lines:
            ts = pattern_miner.extract_timestamp(line)
            if ts:
                timestamps.append(ts)
                hourly_dist[ts.strftime("%Y-%m-%d %H:00")] += 1

            levels[pattern_miner.extract_log_level(line)] += 1
            sources[source] += 1

        return {
            "pattern_id": pattern_id,
            "total_occurrences": len(log_lines),
            "first_seen": min(timestamps).isoformat() if timestamps else None,
            "last_seen": max(timestamps).isoformat() if timestamps else None,
            "level_distribution": dict(levels),
            "source_distribution": dict(sources),
            "hourly_distribution": dict(sorted(hourly_dist.items())),
            "sample_messages": [l[0][:500] for l in log_lines[:20]],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pattern details: {e}")
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
):
    """Get error hotspots - time periods with highest error rates"""
    try:
        hourly_errors: Dict[str, Dict] = defaultdict(
            lambda: {"errors": 0, "total": 0, "samples": []}
        )
        cutoff_time = datetime.now() - timedelta(hours=hours)

        if LOG_DIR.exists():
            for file_path in LOG_DIR.glob("*.log"):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        for line in content.splitlines():
                            if not line.strip():
                                continue

                            ts = pattern_miner.extract_timestamp(line)
                            if ts and ts >= cutoff_time:
                                hour_key = ts.strftime("%Y-%m-%d %H:00")
                                hourly_errors[hour_key]["total"] += 1

                                level = pattern_miner.extract_log_level(line)
                                if level in ["ERROR", "CRITICAL"]:
                                    hourly_errors[hour_key]["errors"] += 1
                                    if len(hourly_errors[hour_key]["samples"]) < 5:
                                        hourly_errors[hour_key]["samples"].append(
                                            line[:200]
                                        )
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")

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
        logger.error(f"Error getting error hotspots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_log_stats",
    error_code_prefix="LOGPAT",
)
@router.get("/stats")
async def get_log_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
):
    """Get overall log statistics"""
    try:
        stats = {
            "total_logs": 0,
            "by_level": Counter(),
            "by_source": Counter(),
            "by_hour": Counter(),
            "earliest": None,
            "latest": None,
        }

        cutoff_time = datetime.now() - timedelta(hours=hours)
        timestamps = []

        if LOG_DIR.exists():
            for file_path in LOG_DIR.glob("*.log"):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        for line in content.splitlines():
                            if not line.strip():
                                continue

                            ts = pattern_miner.extract_timestamp(line)
                            if ts and ts >= cutoff_time:
                                stats["total_logs"] += 1
                                stats["by_level"][pattern_miner.extract_log_level(line)] += 1
                                stats["by_source"][file_path.stem] += 1
                                stats["by_hour"][ts.strftime("%H:00")] += 1
                                timestamps.append(ts)
                except Exception as e:
                    logger.warning(f"Error reading {file_path}: {e}")

        if timestamps:
            stats["earliest"] = min(timestamps).isoformat()
            stats["latest"] = max(timestamps).isoformat()

        return {
            "total_logs": stats["total_logs"],
            "level_distribution": dict(stats["by_level"]),
            "source_distribution": dict(stats["by_source"]),
            "hourly_distribution": dict(sorted(stats["by_hour"].items())),
            "earliest_log": stats["earliest"],
            "latest_log": stats["latest"],
            "time_range_hours": hours,
            "avg_logs_per_hour": (
                round(stats["total_logs"] / hours, 1) if stats["total_logs"] > 0 else 0
            ),
        }

    except Exception as e:
        logger.error(f"Error getting log stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_realtime_summary",
    error_code_prefix="LOGPAT",
)
@router.get("/realtime")
async def get_realtime_summary():
    """Get real-time log summary for last 5 minutes"""
    try:
        cutoff = datetime.now() - timedelta(minutes=5)
        recent_logs = []

        if LOG_DIR.exists():
            for file_path in LOG_DIR.glob("*.log"):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        for line in content.splitlines()[-500:]:  # Check last 500 lines
                            if not line.strip():
                                continue

                            ts = pattern_miner.extract_timestamp(line)
                            if ts and ts >= cutoff:
                                recent_logs.append(
                                    {
                                        "timestamp": ts.isoformat(),
                                        "level": pattern_miner.extract_log_level(line),
                                        "source": file_path.stem,
                                        "message": line[:200],
                                    }
                                )
                except Exception as e:
                    logger.debug(f"Error reading {file_path}: {e}")

        # Sort by timestamp
        recent_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # Calculate summary
        level_counts = Counter(log["level"] for log in recent_logs)

        return {
            "logs_last_5min": len(recent_logs),
            "level_counts": dict(level_counts),
            "error_count": level_counts.get("ERROR", 0) + level_counts.get("CRITICAL", 0),
            "recent_errors": [
                log for log in recent_logs if log["level"] in ["ERROR", "CRITICAL"]
            ][:10],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting realtime summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
