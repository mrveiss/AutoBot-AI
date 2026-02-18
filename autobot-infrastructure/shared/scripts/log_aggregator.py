#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Log Aggregation System
==============================

Centralized logging configuration with aggregation, filtering, and analysis capabilities.

Features:
- Multi-source log collection (services, Docker containers, system logs)
- Real-time log streaming and aggregation
- Log level filtering and pattern matching
- Structured logging with JSON support
- Log rotation and archival
- Search and analysis capabilities
- Alert generation for critical events
- Export to various formats (JSON, CSV, syslog)

Usage:
    python scripts/log_aggregator.py --tail --services backend,ai-stack
    python scripts/log_aggregator.py --search "ERROR" --last-hours 24
    python scripts/log_aggregator.py --analyze --output-report logs_analysis.json
    python scripts/log_aggregator.py --export --format json --output logs_export.json
"""

import argparse
import asyncio
import json
import re
import sys
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


import aiofiles
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.script_utils import ScriptFormatter  # noqa: E402
from utils.service_registry import get_service_registry  # noqa: E402


class LogLevel:
    """Standard log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogSource:
    """Log source types."""

    FILE = "file"
    DOCKER = "docker"
    SYSTEMD = "systemd"
    SERVICE = "service"
    APPLICATION = "application"


class LogAggregator:
    """Centralized log aggregation and management system."""

    def __init__(self, logs_dir: str = "logs", archive_dir: str = "logs/archive"):
        """Initialize log aggregator with log sources and alert patterns."""
        self.project_root = Path(__file__).parent.parent
        self.logs_dir = self.project_root / logs_dir
        self.archive_dir = self.project_root / archive_dir
        self.logs_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)

        self.service_registry = get_service_registry()

        # Log sources configuration
        self.log_sources = self._configure_log_sources()

        # Log patterns for parsing
        self.log_patterns = {
            "timestamp": r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})",
            "level": r"(DEBUG|INFO|WARNING|ERROR|CRITICAL)",
            "module": r"\[([^\]]+)\]",
            "message": r"(.+)$",
        }

        # Lock for thread-safe alerts file access
        self._alerts_lock = threading.Lock()

        # Alert patterns
        self.alert_patterns = [
            {
                "pattern": r"CRITICAL",
                "level": "critical",
                "description": "Critical error",
            },
            {
                "pattern": r"ERROR.*database",
                "level": "high",
                "description": "Database error",
            },
            {
                "pattern": r"ERROR.*connection",
                "level": "high",
                "description": "Connection error",
            },
            {
                "pattern": r"WARNING.*memory",
                "level": "medium",
                "description": "Memory warning",
            },
            {
                "pattern": r"WARNING.*disk",
                "level": "medium",
                "description": "Disk warning",
            },
        ]

        logger.info("📊 AutoBot Log Aggregator initialized")
        logger.info(f"   Logs Directory: {self.logs_dir}")
        logger.info(f"   Archive Directory: {self.archive_dir}")

    def print_header(self, title: str):
        """Print formatted header."""
        ScriptFormatter.print_header(title)

    def print_step(self, step: str, status: str = "info"):
        """Print step with status."""
        ScriptFormatter.print_step(step, status)

    def _configure_log_sources(self) -> Dict[str, Dict[str, Any]]:
        """Configure log sources based on deployment."""
        sources = {
            "backend": {
                "type": LogSource.FILE,
                "path": self.logs_dir / "backend.log",
                "service": "backend",
                "format": "json",
            },
            "frontend": {
                "type": LogSource.FILE,
                "path": self.logs_dir / "frontend.log",
                "service": "frontend",
                "format": "text",
            },
            "ai-stack": {
                "type": LogSource.DOCKER,
                "container": "autobot-ai-stack",
                "service": "ai-stack",
                "format": "text",
            },
            "npu-worker": {
                "type": LogSource.DOCKER,
                "container": "autobot-npu-worker",
                "service": "npu-worker",
                "format": "json",
            },
            "redis": {
                "type": LogSource.DOCKER,
                "container": "autobot-redis",
                "service": "redis",
                "format": "text",
            },
            "playwright-vnc": {
                "type": LogSource.DOCKER,
                "container": "autobot-playwright-vnc",
                "service": "playwright-vnc",
                "format": "text",
            },
            "system": {
                "type": LogSource.FILE,
                "path": self.logs_dir / "system.log",
                "service": "system",
                "format": "json",
            },
        }

        # Add deployment-specific sources
        deployment_mode = self.service_registry.deployment_mode.value
        if deployment_mode == "kubernetes":
            sources.update(
                {
                    "kubernetes": {
                        "type": LogSource.SYSTEMD,
                        "service": "kubelet",
                        "format": "text",
                    }
                }
            )

        return sources

    def parse_log_line(self, line: str, format_type: str = "text") -> Dict[str, Any]:
        """Parse a log line into structured format."""
        if format_type == "json":
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass

        # Fallback to regex parsing
        parsed = {
            "raw": line,
            "timestamp": None,
            "level": "INFO",
            "module": None,
            "message": line,
        }

        # Extract timestamp
        timestamp_match = re.search(self.log_patterns["timestamp"], line)
        if timestamp_match:
            parsed["timestamp"] = timestamp_match.group(1)

        # Extract log level
        level_match = re.search(self.log_patterns["level"], line)
        if level_match:
            parsed["level"] = level_match.group(1)

        # Extract module
        module_match = re.search(self.log_patterns["module"], line)
        if module_match:
            parsed["module"] = module_match.group(1)

        # Extract message
        message_match = re.search(self.log_patterns["message"], line)
        if message_match:
            parsed["message"] = message_match.group(1)

        return parsed

    async def tail_logs(
        self,
        sources: List[str] = None,
        follow: bool = True,
        lines: int = 100,
        filter_level: str = None,
    ) -> None:
        """Tail logs from specified sources."""
        if not sources:
            sources = list(self.log_sources.keys())

        self.print_header(f"Tailing logs from: {', '.join(sources)}")

        # Start tailing tasks for each source
        tasks = []
        for source_name in sources:
            if source_name in self.log_sources:
                source_config = self.log_sources[source_name]
                task = asyncio.create_task(
                    self._tail_single_source(
                        source_name, source_config, follow, lines, filter_level
                    )
                )
                tasks.append(task)

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            self.print_step("Stopping log tail", "info")
            for task in tasks:
                task.cancel()

    async def _tail_single_source(
        self,
        source_name: str,
        source_config: Dict[str, Any],
        follow: bool,
        lines: int,
        filter_level: str,
    ) -> None:
        """Tail logs from a single source."""
        source_type = source_config["type"]

        if source_type == LogSource.FILE:
            await self._tail_file_source(
                source_name, source_config, follow, lines, filter_level
            )
        elif source_type == LogSource.DOCKER:
            await self._tail_docker_source(
                source_name, source_config, follow, lines, filter_level
            )
        elif source_type == LogSource.SYSTEMD:
            await self._tail_systemd_source(
                source_name, source_config, follow, lines, filter_level
            )

    async def _tail_file_source(
        self,
        source_name: str,
        config: Dict[str, Any],
        follow: bool,
        lines: int,
        filter_level: str,
    ) -> None:
        """Tail a file-based log source."""
        log_path = config["path"]
        format_type = config.get("format", "text")

        if not log_path.exists():
            self.print_step(f"Log file not found: {log_path}", "warning")
            return

        # Use tail command for efficiency
        cmd = ["tail", f"-n{lines}"]
        if follow:
            cmd.append("-f")
        cmd.append(str(log_path))

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_str = line.decode().strip()
            if line_str:
                parsed = self.parse_log_line(line_str, format_type)

                # Apply level filter
                if filter_level and not self._should_show_log(
                    parsed["level"], filter_level
                ):
                    continue

                # Format and print
                self._print_log_line(source_name, parsed)

    async def _tail_docker_source(
        self,
        source_name: str,
        config: Dict[str, Any],
        follow: bool,
        lines: int,
        filter_level: str,
    ) -> None:
        """Tail Docker container logs."""
        container = config["container"]
        format_type = config.get("format", "text")

        cmd = ["docker", "logs", f"--tail={lines}"]
        if follow:
            cmd.append("-f")
        cmd.append(container)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )

            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                if line_str:
                    parsed = self.parse_log_line(line_str, format_type)

                    if filter_level and not self._should_show_log(
                        parsed["level"], filter_level
                    ):
                        continue

                    self._print_log_line(source_name, parsed)

        except Exception as e:
            self.print_step(f"Error tailing Docker logs for {container}: {e}", "error")

    def _should_show_log(self, log_level: str, min_level: str) -> bool:
        """Check if log should be shown based on level filter."""
        level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }

        return level_order.get(log_level, 1) >= level_order.get(min_level, 0)

    def _print_log_line(self, source: str, parsed: Dict[str, Any]) -> None:
        """Print formatted log line."""
        timestamp = parsed.get(
            "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        level = parsed.get("level", "INFO")
        message = parsed.get("message", parsed.get("raw", ""))

        # Color coding for levels
        level_colors = {
            LogLevel.DEBUG: "\033[36m",  # Cyan
            LogLevel.INFO: "\033[32m",  # Green
            LogLevel.WARNING: "\033[33m",  # Yellow
            LogLevel.ERROR: "\033[31m",  # Red
            LogLevel.CRITICAL: "\033[35m",  # Magenta
        }
        reset_color = "\033[0m"

        color = level_colors.get(level, "")

        logger.info(f"{timestamp} [{source}] {color}{level:<8}{reset_color} {message}")

        # Check for alerts
        self._check_alerts(source, parsed)

    def _check_alerts(self, source: str, parsed: Dict[str, Any]) -> None:
        """Check log line against alert patterns."""
        message = parsed.get("message", "")

        for alert in self.alert_patterns:
            if re.search(alert["pattern"], message, re.IGNORECASE):
                self._trigger_alert(source, parsed, alert)

    def _trigger_alert(
        self, source: str, log_entry: Dict[str, Any], alert_config: Dict[str, Any]
    ) -> None:
        """Trigger an alert for matching pattern."""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "level": alert_config["level"],
            "description": alert_config["description"],
            "log_entry": log_entry,
        }

        # Save alert to file (thread-safe)
        alert_file = self.logs_dir / "alerts.json"

        with self._alerts_lock:
            alerts = []
            if alert_file.exists():
                try:
                    with open(alert_file, "r") as f:
                        alerts = json.load(f)
                except Exception:
                    alerts = []

            alerts.append(alert)

            # Keep last 1000 alerts
            if len(alerts) > 1000:
                alerts = alerts[-1000:]

            with open(alert_file, "w") as f:
                json.dump(alerts, f, indent=2)

        # Print alert notification
        logger.info(f"\n🚨 ALERT: {alert_config['description']} in {source}")

    async def search_logs(
        self,
        pattern: str,
        sources: List[str] = None,
        last_hours: int = 24,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search logs for pattern."""
        if not sources:
            sources = list(self.log_sources.keys())

        self.print_header(f"Searching logs for: {pattern}")

        results = []
        since_time = datetime.now() - timedelta(hours=last_hours)

        for source_name in sources:
            if source_name not in self.log_sources:
                continue

            source_config = self.log_sources[source_name]
            source_results = await self._search_single_source(
                source_name, source_config, pattern, since_time, case_sensitive
            )
            results.extend(source_results)

        self.print_step(f"Found {len(results)} matching entries", "success")
        return results

    async def _search_single_source(
        self,
        source_name: str,
        config: Dict[str, Any],
        pattern: str,
        since_time: datetime,
        case_sensitive: bool,
    ) -> List[Dict[str, Any]]:
        """Search a single log source."""
        # Early return for non-file sources (Issue #315 - refactored)
        if config["type"] != LogSource.FILE:
            return []

        log_path = config["path"]
        if not log_path.exists():
            return []

        return await self._search_file_source(
            source_name, log_path, config, pattern, since_time, case_sensitive
        )

    async def _search_file_source(
        self,
        source_name: str,
        log_path: Path,
        config: Dict[str, Any],
        pattern: str,
        since_time: datetime,
        case_sensitive: bool,
    ) -> List[Dict[str, Any]]:
        """Search a file-based log source. (Issue #315 - extracted)"""
        results = []
        regex_flags = 0 if case_sensitive else re.IGNORECASE

        try:
            async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
                async for line in f:
                    if not re.search(pattern, line, regex_flags):
                        continue

                    parsed = self.parse_log_line(line, config.get("format", "text"))
                    parsed["source"] = source_name

                    # Check timestamp if available (Issue #315 - refactored)
                    if not self._is_log_within_timeframe(parsed, since_time):
                        continue

                    results.append(parsed)
        except OSError as e:
            self.print_step(f"Failed to read log file {log_path}: {e}", "error")

        return results

    def _is_log_within_timeframe(
        self, parsed: Dict[str, Any], since_time: datetime
    ) -> bool:
        """Check if log entry is within the specified timeframe. (Issue #315 - extracted)"""
        if not parsed.get("timestamp"):
            return True  # Include logs without timestamps

        try:
            log_time = datetime.fromisoformat(parsed["timestamp"])
            return log_time >= since_time
        except Exception:
            return True  # Invalid timestamp, include log anyway

    def analyze_logs(
        self, sources: List[str] = None, last_hours: int = 24
    ) -> Dict[str, Any]:
        """Analyze log patterns and generate statistics."""
        if not sources:
            sources = list(self.log_sources.keys())

        self.print_header("Analyzing logs")

        analysis = {
            "period": {
                "start": (datetime.now() - timedelta(hours=last_hours)).isoformat(),
                "end": datetime.now().isoformat(),
                "hours": last_hours,
            },
            "sources": sources,
            "statistics": {
                "total_entries": 0,
                "by_level": defaultdict(int),
                "by_source": defaultdict(int),
                "errors_by_module": defaultdict(int),
                "top_errors": [],
            },
            "alerts": [],
            "performance": {
                "slow_queries": [],
                "memory_warnings": [],
                "connection_issues": [],
            },
        }

        # Load and analyze each source
        for source_name in sources:
            if source_name not in self.log_sources:
                continue

            self._analyze_source(source_name, analysis)

        # Sort top errors
        for source_name in sources:
            # Count unique errors (simplified for now)
            pass

        # Load recent alerts
        alert_file = self.logs_dir / "alerts.json"
        if alert_file.exists():
            try:
                with open(alert_file, "r") as f:
                    all_alerts = json.load(f)
                    # Filter recent alerts
                    cutoff_time = datetime.now() - timedelta(hours=last_hours)
                    analysis["alerts"] = [
                        a
                        for a in all_alerts
                        if datetime.fromisoformat(a["timestamp"]) > cutoff_time
                    ]
            except Exception:
                pass  # Alert filtering failed, alerts remain empty

        return analysis

    def _analyze_source(self, source_name: str, analysis: Dict[str, Any]) -> None:
        """Analyze a single log source."""
        config = self.log_sources[source_name]

        # Early return for non-file sources (Issue #315 - refactored)
        if config["type"] != LogSource.FILE:
            return

        log_path = config["path"]
        if not log_path.exists():
            return

        self._analyze_file_source(source_name, log_path, config, analysis)

    def _analyze_file_source(
        self,
        source_name: str,
        log_path: Path,
        config: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> None:
        """Analyze a file-based log source. (Issue #315 - extracted)"""
        with open(log_path, "r") as f:
            for line in f:
                parsed = self.parse_log_line(line, config.get("format", "text"))
                self._update_analysis_stats(source_name, parsed, analysis)

    def _update_analysis_stats(
        self, source_name: str, parsed: Dict[str, Any], analysis: Dict[str, Any]
    ) -> None:
        """Update analysis statistics with parsed log entry. (Issue #315 - extracted)"""
        analysis["statistics"]["total_entries"] += 1
        analysis["statistics"]["by_level"][parsed["level"]] += 1
        analysis["statistics"]["by_source"][source_name] += 1

        # Track errors by module
        if parsed["level"] in [LogLevel.ERROR, LogLevel.CRITICAL]:
            module = parsed.get("module", "unknown")
            analysis["statistics"]["errors_by_module"][module] += 1

    def export_logs(
        self,
        sources: List[str] = None,
        format_type: str = "json",
        last_hours: int = 24,
        output_file: str = None,
    ) -> str:
        """Export logs in specified format."""
        if not sources:
            sources = list(self.log_sources.keys())

        self.print_header(f"Exporting logs to {format_type}")

        # Collect logs
        logs = []
        since_time = datetime.now() - timedelta(hours=last_hours)

        for source_name in sources:
            if source_name not in self.log_sources:
                continue

            config = self.log_sources[source_name]
            source_logs = self._collect_source_logs(source_name, config, since_time)
            logs.extend(source_logs)

        # Export based on format
        if format_type == "json":
            output = json.dumps(
                {"logs": logs, "exported_at": datetime.now().isoformat()}, indent=2
            )
        elif format_type == "csv":
            import csv
            import io

            output_buffer = io.StringIO()
            if logs:
                writer = csv.DictWriter(output_buffer, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
            output = output_buffer.getvalue()
        else:
            output = "\n".join([str(log) for log in logs])

        # Save to file if specified
        if output_file:
            with open(output_file, "w") as f:
                f.write(output)
            self.print_step(f"Logs exported to: {output_file}", "success")

        return output

    def _collect_source_logs(
        self, source_name: str, config: Dict[str, Any], since_time: datetime
    ) -> List[Dict[str, Any]]:
        """Collect logs from a single source."""
        # Early return for non-file sources (Issue #315 - refactored)
        if config["type"] != LogSource.FILE:
            return []

        log_path = config["path"]
        if not log_path.exists():
            return []

        return self._collect_file_logs(source_name, log_path, config, since_time)

    def _collect_file_logs(
        self,
        source_name: str,
        log_path: Path,
        config: Dict[str, Any],
        since_time: datetime,
    ) -> List[Dict[str, Any]]:
        """Collect logs from a file-based source. (Issue #315 - extracted)"""
        logs = []

        with open(log_path, "r") as f:
            for line in f:
                parsed = self.parse_log_line(line, config.get("format", "text"))
                parsed["source"] = source_name

                # Check timestamp (Issue #315 - refactored)
                if not self._is_log_within_timeframe(parsed, since_time):
                    continue

                logs.append(parsed)

        return logs

    def setup_centralized_logging(self) -> Dict[str, Any]:
        """Setup centralized logging configuration for all services."""
        self.print_header("Setting up centralized logging")

        # Create logging configuration
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                },
                "standard": {
                    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
                },
            },
            "handlers": {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(self.logs_dir / "system.log"),
                    "maxBytes": 10485760,  # 10MB
                    "backupCount": 5,
                    "formatter": "json",
                },
                "console": {"class": "logging.StreamHandler", "formatter": "standard"},
            },
            "root": {"level": "INFO", "handlers": ["file", "console"]},
        }

        # Save configuration
        config_file = self.project_root / "config" / "logging.yml"
        config_file.parent.mkdir(exist_ok=True)

        with open(config_file, "w") as f:
            yaml.dump(log_config, f)

        self.print_step(f"Logging configuration saved to: {config_file}", "success")

        # Create log rotation script
        rotation_script = self.project_root / "scripts" / "rotate_logs.sh"
        rotation_script_content = """#!/bin/bash
# AutoBot Log Rotation Script

LOGS_DIR="{self.logs_dir}"
ARCHIVE_DIR="{self.archive_dir}"
MAX_AGE_DAYS=30

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

# Rotate logs
find "$LOGS_DIR" -name "*.log" -size +10M -exec gzip {{}} \\; -exec mv {{}}.gz "$ARCHIVE_DIR/" \\;

# Clean old archives
find "$ARCHIVE_DIR" -name "*.gz" -mtime +$MAX_AGE_DAYS -delete

echo "Log rotation completed at $(date)"
"""

        with open(rotation_script, "w") as f:
            f.write(rotation_script_content)

        rotation_script.chmod(0o755)
        self.print_step(f"Log rotation script created: {rotation_script}", "success")

        return {
            "config_file": str(config_file),
            "rotation_script": str(rotation_script),
            "logs_directory": str(self.logs_dir),
            "archive_directory": str(self.archive_dir),
        }


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser. (Issue #315 - extracted)"""
    parser = argparse.ArgumentParser(
        description="AutoBot Log Aggregation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/log_aggregator.py --tail --services backend,ai-stack
  python scripts/log_aggregator.py --search "ERROR" --last-hours 24
  python scripts/log_aggregator.py --analyze --output-report logs_analysis.json
  python scripts/log_aggregator.py --export --format json --output logs_export.json
  python scripts/log_aggregator.py --setup
        """,
    )

    # Actions
    parser.add_argument("--tail", action="store_true", help="Tail logs in real-time")
    parser.add_argument("--search", help="Search logs for pattern")
    parser.add_argument("--analyze", action="store_true", help="Analyze log patterns")
    parser.add_argument("--export", action="store_true", help="Export logs")
    parser.add_argument(
        "--setup", action="store_true", help="Setup centralized logging"
    )

    # Options
    parser.add_argument("--services", help="Comma-separated list of services")
    parser.add_argument("--last-hours", type=int, default=24, help="Hours to look back")
    parser.add_argument("--lines", type=int, default=100, help="Initial lines to show")
    parser.add_argument(
        "--follow", action="store_true", default=True, help="Follow log output"
    )
    parser.add_argument(
        "--no-follow", dest="follow", action="store_false", help="Don't follow"
    )
    parser.add_argument(
        "--filter-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum log level to show",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "text"],
        default="json",
        help="Export format",
    )
    parser.add_argument("--output", help="Output file for export/analysis")
    parser.add_argument(
        "--case-sensitive", action="store_true", help="Case-sensitive search"
    )

    return parser


async def _handle_search_command(
    log_aggregator: LogAggregator, args: argparse.Namespace, services: List[str]
) -> None:
    """Handle search command. (Issue #315 - extracted)"""
    results = await log_aggregator.search_logs(
        pattern=args.search,
        sources=services,
        last_hours=args.last_hours,
        case_sensitive=args.case_sensitive,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump({"results": results}, f, indent=2)
        logger.info(f"✅ Search results saved to: {args.output}")
    else:
        _print_search_results(log_aggregator, results)


def _print_search_results(
    log_aggregator: LogAggregator, results: List[Dict[str, Any]]
) -> None:
    """Print search results to console. (Issue #315 - extracted)"""
    for result in results[:50]:  # Show first 50 results
        log_aggregator._print_log_line(result.get("source", "unknown"), result)

    if len(results) > 50:
        logger.info(f"\n... and {len(results) - 50} more results")


def _handle_analyze_command(
    log_aggregator: LogAggregator, args: argparse.Namespace, services: List[str]
) -> None:
    """Handle analyze command. (Issue #315 - extracted)"""
    analysis = log_aggregator.analyze_logs(sources=services, last_hours=args.last_hours)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"✅ Analysis saved to: {args.output}")
    else:
        _print_analysis_summary(analysis)


def _print_analysis_summary(analysis: Dict[str, Any]) -> None:
    """Print analysis summary to console. (Issue #315 - extracted)"""
    logger.info("\n📊 Log Analysis Summary:")
    logger.info(f"   Total entries: {analysis['statistics']['total_entries']}")
    logger.info("   Log levels:")
    for level, count in analysis["statistics"]["by_level"].items():
        logger.info(f"     {level}: {count}")
    logger.info(f"   Recent alerts: {len(analysis['alerts'])}")


def _handle_export_command(
    log_aggregator: LogAggregator, args: argparse.Namespace, services: List[str]
) -> None:
    """Handle export command. (Issue #315 - extracted)"""
    output = log_aggregator.export_logs(
        sources=services,
        format_type=args.format,
        last_hours=args.last_hours,
        output_file=args.output,
    )

    if not args.output:
        logger.info(output)


def _handle_setup_command(log_aggregator: LogAggregator) -> None:
    """Handle setup command. (Issue #315 - extracted)"""
    result = log_aggregator.setup_centralized_logging()
    logger.info("\n✅ Centralized logging configured:")
    for key, value in result.items():
        logger.info(f"   {key}: {value}")


async def main():
    """Entry point for log aggregator CLI."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    # Early return if no action specified (Issue #315 - refactored)
    if not any([args.tail, args.search, args.analyze, args.export, args.setup]):
        parser.print_help()
        return 1

    # Parse services list
    services = [s.strip() for s in args.services.split(",")] if args.services else None

    log_aggregator = LogAggregator()

    try:
        # Command dispatch table (Issue #315 - refactored)
        if args.tail:
            await log_aggregator.tail_logs(
                sources=services,
                follow=args.follow,
                lines=args.lines,
                filter_level=args.filter_level,
            )
        elif args.search:
            await _handle_search_command(log_aggregator, args, services)
        elif args.analyze:
            _handle_analyze_command(log_aggregator, args, services)
        elif args.export:
            _handle_export_command(log_aggregator, args, services)
        elif args.setup:
            _handle_setup_command(log_aggregator)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
