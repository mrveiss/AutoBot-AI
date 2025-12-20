# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Metrics Package

Domain-specific metrics recorders for Prometheus.
Extracted from PrometheusMetricsManager as part of Issue #394.

Package Structure:
- base.py: Base recorder class with shared functionality
- workflow.py: Workflow execution metrics
- github.py: GitHub operation metrics
- task.py: Task execution metrics
- system.py: System resource metrics
- claude_api.py: Claude API metrics
- service_health.py: Service health metrics
"""

from .base import BaseMetricsRecorder
from .workflow import WorkflowMetricsRecorder
from .github import GitHubMetricsRecorder
from .task import TaskMetricsRecorder
from .system import SystemMetricsRecorder
from .claude_api import ClaudeAPIMetricsRecorder
from .service_health import ServiceHealthMetricsRecorder

__all__ = [
    "BaseMetricsRecorder",
    "WorkflowMetricsRecorder",
    "GitHubMetricsRecorder",
    "TaskMetricsRecorder",
    "SystemMetricsRecorder",
    "ClaudeAPIMetricsRecorder",
    "ServiceHealthMetricsRecorder",
]
