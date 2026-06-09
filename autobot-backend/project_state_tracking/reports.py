# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Project State Tracking Reports Module

Report generation and data export functions.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_relative_path
from autobot_shared.ssot_config import PROJECT_ROOT

from .models import StateSnapshot
from .types import TrackingMetric

logger = get_logger(__name__)


def _build_error_tracking_lines(error_data: Dict[str, Any]) -> List[str]:
    """
    Build report lines for error tracking metrics.

    Extracted from build_tracking_metrics_section() to reduce function length. Issue #620.

    Args:
        error_data: Error tracking data dictionary

    Returns:
        List of formatted report lines
    """
    return [
        f"- **Error Rate**: {error_data.get('current_error_rate', 0)}%",
        f"- **Total Errors**: {error_data.get('total_errors_tracked', 0)}",
    ]


def _build_api_tracking_lines(api_data: Dict[str, Any]) -> List[str]:
    """
    Build report lines for API tracking metrics.

    Extracted from build_tracking_metrics_section() to reduce function length. Issue #620.

    Args:
        api_data: API tracking data dictionary

    Returns:
        List of formatted report lines
    """
    return [
        f"- **API Calls (24h)**: {api_data.get('total_api_calls_24h', 0)}",
        f"- **Session API Calls**: {api_data.get('current_session_calls', 0)}",
    ]


def _build_interaction_tracking_lines(interaction_data: Dict[str, Any]) -> List[str]:
    """
    Build report lines for user interaction metrics.

    Extracted from build_tracking_metrics_section() to reduce function length. Issue #620.

    Args:
        interaction_data: User interaction data dictionary

    Returns:
        List of formatted report lines
    """
    return [
        f"- **User Interactions (24h)**: {interaction_data.get('total_interactions_24h', 0)}",
        f"- **Session Interactions**: {interaction_data.get('current_session_interactions', 0)}",
    ]


def build_tracking_metrics_section(tracking_metrics: Dict[str, Any]) -> List[str]:
    """
    Build the tracking metrics section of the state report.

    Issue #281: Extracted from generate_state_report to reduce function
    length and improve readability.

    Args:
        tracking_metrics: Dictionary of tracking metrics from summary

    Returns:
        List of formatted report lines for tracking metrics
    """
    lines = ["## System Tracking Metrics"]

    if "error_tracking" in tracking_metrics:
        lines.extend(_build_error_tracking_lines(tracking_metrics["error_tracking"]))

    if "api_tracking" in tracking_metrics:
        lines.extend(_build_api_tracking_lines(tracking_metrics["api_tracking"]))

    if "user_interactions" in tracking_metrics:
        lines.extend(_build_interaction_tracking_lines(tracking_metrics["user_interactions"]))

    if "system_health" in tracking_metrics:
        health_data = tracking_metrics["system_health"]
        redis_status = "✅ Connected" if health_data.get("redis_connected") else "❌ Disconnected"
        lines.append(f"- **Redis Status**: {redis_status}")

    lines.append("")
    return lines


def build_current_state_section(summary: Dict[str, Any]) -> List[str]:
    """Build the current system state section of the report."""
    lines = []
    lines.append("## Current System State")
    current = summary["current_state"]
    metrics = current["system_metrics"]

    lines.append(f"- **System Maturity**: {metrics.get('system_maturity', 0):.1f}%")
    lines.append(f"- **Phases Completed**: {metrics.get('phase_completion', 0)}/10")
    lines.append(f"- **Active Capabilities**: {metrics.get('capability_count', 0)}")
    lines.append(f"- **Validation Score**: {metrics.get('validation_score', 0):.1f}%")
    lines.append("")
    return lines


def build_milestones_section(summary: Dict[str, Any]) -> List[str]:
    """Build the milestones section of the report."""
    lines = []
    lines.append("## Milestones")
    for name, status in summary["milestones"].items():
        icon = "✅" if status["achieved"] else "⏳"
        lines.append(f"- {icon} **{name}**: {status['description']}")
        if status["achieved"]:
            lines.append(f"  - Achieved: {status['achieved_at']}")
    lines.append("")
    return lines


def build_trends_section(summary: Dict[str, Any]) -> List[str]:
    """Build the system trends section of the report."""
    lines = []
    lines.append("## System Trends")
    for metric_name, trend_data in summary["trends"].items():
        lines.append(f"- **{metric_name.replace('_', ' ').title()}**:")
        lines.append(f"  - Current: {trend_data['current']:.2f}")
        lines.append(f"  - Trend: {trend_data['trend']}")
        lines.append(f"  - Change: {trend_data['change']:+.2f}")
    lines.append("")
    return lines


def build_recent_changes_section(summary: Dict[str, Any]) -> List[str]:
    """Build the recent changes section of the report."""
    lines = []
    lines.append("## Recent Changes")
    for change in summary["recent_changes"][-5:]:
        lines.append(f"- {change['timestamp']}: {change['description']} ({change['type']})")
    lines.append("")
    return lines


def build_phase_status_section(summary: Dict[str, Any]) -> List[str]:
    """Build the phase status section of the report."""
    lines = []
    lines.append("## Phase Status")
    current = summary["current_state"]
    for phase_name, phase_data in current["phase_states"].items():
        status_icon = (
            "✅"
            if phase_data["completion_percentage"] >= 95
            else "🔄" if phase_data["completion_percentage"] >= 50 else "⏳"
        )
        lines.append(
            f"- {status_icon} **{phase_name}**: " f"{phase_data['completion_percentage']:.1f}% ({phase_data['status']})"
        )
    return lines


def generate_state_report_from_summary(summary: Dict[str, Any]) -> str:
    """
    Generate comprehensive state tracking report from summary data.

    Args:
        summary: State summary dictionary from get_state_summary()

    Returns:
        Formatted markdown report string
    """
    report = []
    report.append("# AutoBot Enhanced State Tracking Report")
    report.append(f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Build sections
    report.extend(build_current_state_section(summary))
    report.extend(build_milestones_section(summary))
    report.extend(build_trends_section(summary))
    report.extend(build_recent_changes_section(summary))

    # Tracking metrics section
    tracking_metrics = summary.get("tracking_metrics", {})
    report.extend(build_tracking_metrics_section(tracking_metrics))

    # Phase details
    report.extend(build_phase_status_section(summary))

    return "\n".join(report)


def calculate_trends(
    state_history: List[StateSnapshot],
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate trend data for all tracking metrics.

    Args:
        state_history: List of state snapshots

    Returns:
        Dictionary of trends for each metric
    """
    trends = {}
    for metric in TrackingMetric:
        recent_values = [
            (s.timestamp, s.system_metrics.get(metric, 0)) for s in state_history[-30:] if metric in s.system_metrics
        ]
        if len(recent_values) >= 2:
            first_value = recent_values[0][1]
            last_value = recent_values[-1][1]
            trend = "increasing" if last_value > first_value else "decreasing" if last_value < first_value else "stable"
            trends[metric.value] = {
                "current": last_value,
                "trend": trend,
                "change": last_value - first_value,
            }
    return trends


async def export_state_data_to_file(
    summary: Dict[str, Any],
    output_path: str,
    format: str = "json",
    report_generator=None,
) -> None:
    """
    Export state tracking data to file.

    Args:
        summary: State summary dictionary
        output_path: Path to output file
        format: Output format ('json' or 'markdown')
        report_generator: Optional async callable for markdown format
    """
    # Ensure output goes to data directory
    data_base = PROJECT_ROOT / "data/reports/state_tracking"  # #2163
    if not output_path.startswith("data/"):
        safe_name = Path(output_path).name
        output_file = validate_relative_path(safe_name, data_base)
    else:
        output_file = validate_relative_path(output_path, PROJECT_ROOT)

    # Issue #358 - avoid blocking
    await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

    try:
        if format == "json":
            async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(summary, indent=2, default=str))
        elif format == "markdown":
            if report_generator:
                report = await report_generator()
            else:
                report = generate_state_report_from_summary(summary)
            async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
                await f.write(report)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info("State data exported to %s", output_file)
    except OSError as e:
        logger.error("Failed to export state data to %s: %s", output_file, e)
        raise
