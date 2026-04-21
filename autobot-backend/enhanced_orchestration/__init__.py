# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration Package — re-exports only.

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Issue #4048: EnhancedMultiAgentOrchestrator inlined here from orchestrator.py.
Issue #5040: EnhancedMultiAgentOrchestrator merged into the single Orchestrator conductor.
             This package now re-exports types and sub-components only.

Sub-modules:
- types.py: Enums and dataclasses (AgentCapability, ExecutionStrategy, AgentTask, etc.)
- execution_strategies.py: Strategy implementations (sequential, parallel, pipeline, etc.)
- workflow_planning.py: Workflow planning, building, and utilities
- success_criteria.py: Structured success criteria evaluation
"""

from .execution_strategies import ExecutionStrategyHandler
from .success_criteria import (
    CriteriaResult,
    EvaluationResult,
    SuccessCriteria,
    SuccessCriteriaEvaluator,
    SuccessCriteriaType,
)
from .types import (
    FALLBACK_TIERS,
    AgentCapability,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from .workflow_planning import WorkflowPlanner

# Backward compatibility alias
_FALLBACK_TIERS = FALLBACK_TIERS

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
    # Issue #3293: success criteria
    "SuccessCriteriaType",
    "SuccessCriteria",
    "CriteriaResult",
    "EvaluationResult",
    "SuccessCriteriaEvaluator",
]
