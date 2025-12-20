# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking Package

Comprehensive tracking of project state, phase progression,
capabilities, and system evolution.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional

# Types and enums
from .types import (
    REDIS_METRIC_KEYS,
    SIGNIFICANT_CHANGES,
    SIGNIFICANT_INTERACTIONS,
    StateChangeType,
    TrackingMetric,
)

# Data models
from .models import ProjectMilestone, StateChange, StateSnapshot

# Database operations
from .database import (
    DATABASE_SCHEMA_INDICES,
    DATABASE_SCHEMA_TABLES,
    init_database,
    load_milestones_from_db,
    load_snapshots_from_db,
    record_state_change_sync,
    save_milestone_sync,
    save_snapshot_sync,
)

# Metrics
from .metrics import (
    calculate_progression_velocity,
    get_api_calls_count,
    get_error_rate,
    get_metrics_summary,
    get_redis_metric,
    get_user_interactions_count,
)

# Milestones
from .milestones import (
    check_single_criterion,
    define_default_milestones,
    evaluate_milestone_criteria,
)

# Tracking functions
from .tracking import (
    error_tracking_decorator,
    is_significant_interaction,
    track_api_call_to_redis,
    track_error_to_redis,
    track_user_interaction_to_redis,
)

# Reports
from .reports import (
    build_tracking_metrics_section,
    calculate_trends,
    export_state_data_to_file,
    generate_state_report_from_summary,
)

# Main tracker class
from .tracker import EnhancedProjectStateTracker, get_state_tracker

logger = logging.getLogger(__name__)


# ============================================================================
# Convenience functions for easy integration
# ============================================================================


async def track_system_error(
    error: Exception, context: Optional[Dict[str, Any]] = None
):
    """Convenience function to track system errors from anywhere in the codebase."""
    try:
        tracker = get_state_tracker()
        await tracker.track_error(error, context)
    except Exception as e:
        logger.error("Failed to track system error: %s", e)


async def track_api_request(
    endpoint: str, method: str = "GET", status_code: Optional[int] = None
):
    """Convenience function to track API requests from middleware or endpoints."""
    try:
        tracker = get_state_tracker()
        await tracker.track_api_call(endpoint, method, status_code)
    except Exception as e:
        logger.error("Failed to track API request: %s", e)


async def track_user_action(
    action_type: str,
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
):
    """Convenience function to track user actions from frontend or API."""
    try:
        tracker = get_state_tracker()
        await tracker.track_user_interaction(action_type, user_id, context)
    except Exception as e:
        logger.error("Failed to track user action: %s", e)


# ============================================================================
# CLI Command Handlers (use sys.stdout for intentional CLI output)
# ============================================================================


def _cli_output(message: str) -> None:
    """Write message to stdout for CLI output (intentional, not logging)."""
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


async def _handle_snapshot_command(tracker):
    """Handle snapshot command."""
    _cli_output("Capturing state snapshot...")
    snapshot = await tracker.capture_state_snapshot()
    _cli_output(f"Snapshot captured at {snapshot.timestamp}")
    _cli_output(
        f"System maturity: {snapshot.system_metrics[TrackingMetric.SYSTEM_MATURITY]}%"
    )


async def _handle_summary_command(tracker):
    """Handle summary command."""
    summary = await tracker.get_state_summary()
    _cli_output(json.dumps(summary, indent=2, default=str))


async def _handle_report_command(tracker):
    """Handle report command."""
    report = await tracker.generate_state_report()
    _cli_output(report)


async def _handle_metrics_command(tracker):
    """Handle metrics command."""
    metrics = await tracker.get_metrics_summary()
    _cli_output(json.dumps(metrics, indent=2, default=str))


async def _handle_test_tracking_command(tracker):
    """Handle test-tracking command."""
    _cli_output("Testing tracking functionality...")

    test_error = ValueError("Test error for tracking")
    await tracker.track_error(test_error, {"test": True})
    _cli_output("✅ Error tracking tested")

    await tracker.track_api_call("/api/test", "POST", 200)
    _cli_output("✅ API call tracking tested")

    await tracker.track_user_interaction(
        "test_interaction", "test_user", {"test": True}
    )
    _cli_output("✅ User interaction tracking tested")

    metrics = await tracker.get_metrics_summary()
    _cli_output("\nUpdated metrics:")
    _cli_output(json.dumps(metrics, indent=2, default=str))


async def _handle_export_command(tracker, args):
    """Handle export command."""
    output_path = (
        args[2] if len(args) > 2 else "reports/state_tracking_export.json"
    )
    await tracker.export_state_data(output_path)
    _cli_output(f"Data exported to {output_path}")


# Command dispatch map
COMMAND_HANDLERS = {
    "snapshot": _handle_snapshot_command,
    "summary": _handle_summary_command,
    "report": _handle_report_command,
    "metrics": _handle_metrics_command,
    "test-tracking": _handle_test_tracking_command,
}


# ============================================================================
# Backward compatibility aliases for internal sync functions
# ============================================================================

_save_snapshot_sync = save_snapshot_sync
_record_state_change_sync = record_state_change_sync
_save_milestone_sync = save_milestone_sync


__all__ = [
    # Types
    "StateChangeType",
    "TrackingMetric",
    "SIGNIFICANT_CHANGES",
    "SIGNIFICANT_INTERACTIONS",
    "REDIS_METRIC_KEYS",
    # Models
    "StateSnapshot",
    "StateChange",
    "ProjectMilestone",
    # Database
    "DATABASE_SCHEMA_TABLES",
    "DATABASE_SCHEMA_INDICES",
    "init_database",
    "save_snapshot_sync",
    "record_state_change_sync",
    "save_milestone_sync",
    "load_snapshots_from_db",
    "load_milestones_from_db",
    # Metrics
    "get_redis_metric",
    "get_error_rate",
    "get_user_interactions_count",
    "get_api_calls_count",
    "calculate_progression_velocity",
    "get_metrics_summary",
    # Milestones
    "define_default_milestones",
    "evaluate_milestone_criteria",
    "check_single_criterion",
    # Tracking
    "track_error_to_redis",
    "track_api_call_to_redis",
    "track_user_interaction_to_redis",
    "is_significant_interaction",
    "error_tracking_decorator",
    # Reports
    "build_tracking_metrics_section",
    "generate_state_report_from_summary",
    "calculate_trends",
    "export_state_data_to_file",
    # Main tracker
    "EnhancedProjectStateTracker",
    "get_state_tracker",
    # Convenience functions
    "track_system_error",
    "track_api_request",
    "track_user_action",
    # CLI handlers
    "COMMAND_HANDLERS",
    "_handle_snapshot_command",
    "_handle_summary_command",
    "_handle_report_command",
    "_handle_metrics_command",
    "_handle_test_tracking_command",
    "_handle_export_command",
    # Backward compatibility
    "_save_snapshot_sync",
    "_record_state_change_sync",
    "_save_milestone_sync",
]
