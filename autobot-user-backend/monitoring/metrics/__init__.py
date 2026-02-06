# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Metrics Package

Domain-specific metrics recorders for Prometheus.
Extracted from PrometheusMetricsManager as part of Issue #394.
Extended with PerformanceMetricsRecorder as part of Issue #469.
Extended with KnowledgeBase, LLMProvider, WebSocket, Redis recorders (Issue #470).
Extended with FrontendMetricsRecorder for RUM metrics (Issue #476).

Package Structure:
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
"""

from .base import BaseMetricsRecorder
from .workflow import WorkflowMetricsRecorder
from .github import GitHubMetricsRecorder
from .task import TaskMetricsRecorder
from .system import SystemMetricsRecorder
from .claude_api import ClaudeAPIMetricsRecorder
from .service_health import ServiceHealthMetricsRecorder
from .performance import PerformanceMetricsRecorder
# Issue #470: New domain-specific recorders
from .knowledge_base import KnowledgeBaseMetricsRecorder
from .llm_provider import LLMProviderMetricsRecorder
from .websocket import WebSocketMetricsRecorder
from .redis import RedisMetricsRecorder
# Issue #476: Frontend RUM metrics recorder
from .frontend import FrontendMetricsRecorder

__all__ = [
    "BaseMetricsRecorder",
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
