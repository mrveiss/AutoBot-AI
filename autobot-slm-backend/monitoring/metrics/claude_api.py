# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Claude API Metrics Recorder — Issue #12648

Re-exports the canonical implementation from autobot_shared so that the
SLM-backend local metrics package stays in sync with the shared recorder.
"""

from autobot_shared.monitoring.metrics.claude_api import ClaudeAPIMetricsRecorder  # noqa: F401

__all__ = ["ClaudeAPIMetricsRecorder"]
