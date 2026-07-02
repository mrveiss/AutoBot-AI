# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Requests Metrics Recorder — Issue #10778

Re-exports the canonical implementation from autobot_shared so that the
SLM-backend local metrics package stays in sync with the shared recorder.
"""

from autobot_shared.monitoring.metrics.api_requests import ApiRequestsMetricsRecorder  # noqa: F401

__all__ = ["ApiRequestsMetricsRecorder"]
