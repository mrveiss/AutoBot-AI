# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration Package

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Provides advanced orchestration system with improved agent coordination.

- types.py: Enums and dataclasses (AgentCapability, ExecutionStrategy, AgentTask, etc.)
- execution_strategies.py: Strategy implementations (sequential, parallel, pipeline, etc.)
- workflow_planning.py: Workflow planning, building, and utilities
"""

from .execution_strategies import ExecutionStrategyHandler
from .types import (
    FALLBACK_TIERS,
    AgentCapability,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from .workflow_planning import WorkflowPlanner

__all__ = [
    # Types and enums
    "AgentCapability",
    "ExecutionStrategy",
    "AgentTask",
    "WorkflowPlan",
    "AgentPerformance",
    "FALLBACK_TIERS",
    # Strategy handler
    "ExecutionStrategyHandler",
    # Workflow planner
    "WorkflowPlanner",
]
