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
Extended with MCPWorkerMetricsRecorder for worker restart budget tracking (Issue #4109).
Extended with VoiceRealtimeMetricsRecorder for Realtime WebRTC session metrics (Issue #7421).

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
- mcp_worker.py: MCP worker lifecycle metrics (Issue #4109)
"""

from .base import BaseMetricsRecorder

# Phase 4 (#7590): Chat SSOT observability recorder
from .chat import ChatMetricsRecorder
from .claude_api import ClaudeAPIMetricsRecorder

# Issue #476: Frontend RUM metrics recorder
from .frontend import FrontendMetricsRecorder
from .github import GitHubMetricsRecorder

# Issue #1956: Inference profiler metrics recorder
from .inference_profiler import InferenceProfilerMetricsRecorder

# Issue #470: New domain-specific recorders
from .knowledge_base import KnowledgeBaseMetricsRecorder
from .llm_provider import LLMProviderMetricsRecorder

# Issue #4109: MCP worker restart budget exhaustion metrics
from .mcp_worker import MCPWorkerMetricsRecorder
from .performance import PerformanceMetricsRecorder
from .redis import RedisMetricsRecorder
from .service_health import ServiceHealthMetricsRecorder
from .system import SystemMetricsRecorder
from .task import TaskMetricsRecorder
from .voice_realtime import VoiceRealtimeMetricsRecorder
from .websocket import WebSocketMetricsRecorder
from .workflow import WorkflowMetricsRecorder

__all__ = [
    "BaseMetricsRecorder",
    # Phase 4 (#7590): Chat SSOT observability
    "ChatMetricsRecorder",
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
    # Issue #1956: Inference profiler recorder
    "InferenceProfilerMetricsRecorder",
    # Issue #4109: MCP worker metrics
    "MCPWorkerMetricsRecorder",
    # Issue #7421: Voice Realtime WebRTC session metrics
    "VoiceRealtimeMetricsRecorder",
]
