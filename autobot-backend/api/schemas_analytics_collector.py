# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Declared response shapes for the two AnalyticsController collector endpoints.

``GET /analytics/usage/statistics`` and ``GET /analytics/performance/metrics``
were modelled as bare ``BaseModel`` subclasses carrying nothing but
``extra="allow"`` (#5960). A model with no fields documents nothing in
``/openapi.json`` and gives a client no contract to be checked against, which is
how the Python SDK came to declare four fields for each of them that neither
route has ever emitted (#15116, #15118).

They live here rather than in ``api/schemas_analytics.py`` because that file's
size ceiling only ever moves downwards (``scripts/check_python_file_size.py``),
and declaring these shapes makes them longer. Moving the pair out lowers that
file instead of raising its ceiling.

``extra="allow"`` is retained on both. The names below are the blocks the
controller and the route always write; the keys *inside* each block rotate with
the collector implementation and are deliberately not pinned.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class AnalyticsPerformanceMetricsResponse(BaseModel):
    """Response for GET /analytics/performance/metrics.

    Every block is written by ``AnalyticsController.collect_performance_metrics``
    except ``historical_context``, which the route appends, and ``error``, which
    replaces the rest when collection raises.
    """

    model_config = {"extra": "allow"}

    system_performance: Dict[str, Any] | None = None
    api_performance: Dict[str, Any] | None = None
    advanced_metrics: Dict[str, Any] | None = None
    detailed_metrics: Dict[str, Any] | None = None
    hardware_performance: Dict[str, Any] | None = None
    network_io: Dict[str, Any] | None = None
    historical_context: Dict[str, Any] | None = None
    error: str | None = None


class AnalyticsUsageStatisticsResponse(BaseModel):
    """Response for GET /analytics/usage/statistics.

    Blocks come from ``AnalyticsController.get_usage_statistics``;
    ``analysis_period`` is appended by the route and ``error`` replaces the rest
    when collection raises.
    """

    model_config = {"extra": "allow"}

    api_usage: Dict[str, Any] | None = None
    websocket_usage: Dict[str, Any] | None = None
    system_usage: Dict[str, Any] | None = None
    knowledge_base_usage: Dict[str, Any] | None = None
    analysis_period: Dict[str, Any] | None = None
    error: str | None = None
