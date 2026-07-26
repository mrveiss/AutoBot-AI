# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Task Metrics Recorder — Issue #12648

Re-exports the canonical implementation from autobot_shared so that the
SLM-backend local metrics package stays in sync with the shared recorder.
"""

from autobot_shared.monitoring.metrics.task import TaskMetricsRecorder  # noqa: F401

__all__ = ["TaskMetricsRecorder"]
