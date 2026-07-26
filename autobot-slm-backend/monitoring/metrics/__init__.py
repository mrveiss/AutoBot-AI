# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Metrics Package — Issue #12648

Domain-specific metrics recorders for Prometheus.

The recorders themselves now live exclusively in
``autobot_shared.monitoring.metrics``; every module in this package
(including this ``__init__``) is a thin re-export shim so the SLM-backend
local metrics package stays in sync with the shared canonical implementation
and no metric body is duplicated (Issue #12648, consolidating #10778's
established shim pattern across the whole package).

Package Structure (each module below is a re-export shim):
- base.py: Base recorder class with shared functionality
- workflow.py: Workflow execution metrics
- github.py: GitHub operation metrics
- task.py: Task execution metrics
- system.py: System resource metrics
- claude_api.py: Claude API metrics
- service_health.py: Service health metrics
- performance.py: GPU/NPU/Performance metrics (Issue #469)
- knowledge_base.py: Knowledge base and vector store metrics (Issue #470)
- llm_provider.py: LLM provider metrics (Issue #470)
- websocket.py: WebSocket connection metrics (Issue #470)
- redis.py: Redis operation metrics (Issue #470)
- frontend.py: Frontend RUM metrics (Issue #476)
- api_requests.py: HTTP API request counter (Issue #10778)
"""

from autobot_shared.monitoring.metrics import (
    ApiRequestsMetricsRecorder,
    BaseMetricsRecorder,
    ClaudeAPIMetricsRecorder,
    FrontendMetricsRecorder,
    GitHubMetricsRecorder,
    KnowledgeBaseMetricsRecorder,
    LLMProviderMetricsRecorder,
    PerformanceMetricsRecorder,
    RedisMetricsRecorder,
    ServiceHealthMetricsRecorder,
    SystemMetricsRecorder,
    TaskMetricsRecorder,
    WebSocketMetricsRecorder,
    WorkflowMetricsRecorder,
)

__all__ = [
    "BaseMetricsRecorder",
    # Issue #10778: HTTP API request counter
    "ApiRequestsMetricsRecorder",
    "WorkflowMetricsRecorder",
    "GitHubMetricsRecorder",
    "TaskMetricsRecorder",
    "SystemMetricsRecorder",
    "ClaudeAPIMetricsRecorder",
    "ServiceHealthMetricsRecorder",
    "PerformanceMetricsRecorder",
    # Issue #470: New recorders
    "KnowledgeBaseMetricsRecorder",
    "LLMProviderMetricsRecorder",
    "WebSocketMetricsRecorder",
    "RedisMetricsRecorder",
    # Issue #476: Frontend RUM recorder
    "FrontendMetricsRecorder",
]
