# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LLM Provider Metrics Recorder — Issue #12648

Re-exports the canonical implementation from autobot_shared so that the
SLM-backend local metrics package stays in sync with the shared recorder.

Reconciliation note (#12648): the autobot_shared version was already the
superset (it additionally carries the Issue #3273 response-cache hit/miss
counters that this SLM copy never had) — no SLM-only behaviour needed
folding back into autobot_shared before shimming.
"""

from autobot_shared.monitoring.metrics.llm_provider import LLMProviderMetricsRecorder  # noqa: F401

__all__ = ["LLMProviderMetricsRecorder"]
