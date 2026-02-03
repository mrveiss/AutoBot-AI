#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Project State Tracking System - Facade Module

This module provides backward compatibility by re-exporting all public APIs
from the refactored src.project_state_tracking package.

Part of Issue #381 - God Class Refactoring
Original file: 1,505 lines → Package with focused modules
"""

import asyncio
import sys

# Re-export all public APIs from the package
from src.project_state_tracking import (
    # Types and enums
    REDIS_METRIC_KEYS,
    SIGNIFICANT_CHANGES,
    SIGNIFICANT_INTERACTIONS,
    StateChangeType,
    TrackingMetric,
    # Models
    ProjectMilestone,
    StateChange,
    StateSnapshot,
    # Database
    DATABASE_SCHEMA_INDICES,
    DATABASE_SCHEMA_TABLES,
    # Main tracker
    EnhancedProjectStateTracker,
    get_state_tracker,
    # Convenience functions
    error_tracking_decorator,
    track_api_request,
    track_system_error,
    track_user_action,
    # CLI handlers
    COMMAND_HANDLERS,
    _handle_export_command,
    _handle_metrics_command,
    _handle_report_command,
    _handle_snapshot_command,
    _handle_summary_command,
    _handle_test_tracking_command,
    # Backward compatibility aliases for sync functions
    _record_state_change_sync,
    _save_milestone_sync,
    _save_snapshot_sync,
)

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
    # Database schema
    "DATABASE_SCHEMA_TABLES",
    "DATABASE_SCHEMA_INDICES",
    # Main tracker
    "EnhancedProjectStateTracker",
    "get_state_tracker",
    # Convenience functions
    "track_system_error",
    "track_api_request",
    "track_user_action",
    "error_tracking_decorator",
    # CLI
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


# CLI entry point
if __name__ == "__main__":

    async def main():
        """Run state tracker CLI commands."""
        tracker = get_state_tracker()

        if len(sys.argv) <= 1:
            await _handle_summary_command(tracker)
            return

        command = sys.argv[1]

        if command == "export":
            await _handle_export_command(tracker, sys.argv)
            return

        handler = COMMAND_HANDLERS.get(command)
        if handler:
            await handler(tracker)
        else:
            print(f"Unknown command: {command}")
            print(
                "Available commands: snapshot, summary, report, metrics, test-tracking, export"
            )

    asyncio.run(main())
