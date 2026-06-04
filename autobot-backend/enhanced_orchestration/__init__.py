# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-Agent Coordination  (#7379 boundary)

BOUNDARY: this package owns multi-agent coordination — strategy selection,
agent routing, Redis pub/sub collaboration, and subagent dispatch.
Use it when you need to COORDINATE multiple agents across a run.

The sibling `orchestration/` package owns single-workflow execution primitives
(DAG/graph execution, error handling, variable piping, causal recovery).
New single-workflow primitives go there; new multi-agent coordination goes here.

`AgentCapability` is defined canonically in `orchestration/types.py`; this
package re-exports it for backwards compatibility (see import below).

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Issue #4048: EnhancedMultiAgentOrchestrator inlined here from orchestrator.py.
Issue #5040: EnhancedMultiAgentOrchestrator merged into the single Orchestrator conductor.
             This package now re-exports types and sub-components only.

Sub-modules:
- types.py: Enums and dataclasses (ExecutionStrategy, AgentTask, AgentPerformance, etc.)
- execution_strategies.py: Strategy implementations (sequential, parallel, pipeline, etc.)
- workflow_planning.py: Multi-agent strategy planning (StrategyPlanner)
- workflow_runner.py: Multi-agent workflow execution engine (WorkflowRunner)
- success_criteria.py: Structured success criteria evaluation
- collaboration_coordinator.py: Redis pub/sub collaboration layer (#6393)
- agent_router.py: Agent selection, resolution, capability coverage (#6393/#6392)
- subagent_dispatcher.py: Autonomous subagent spawning for parallel workstreams (#6822)
- blocked_plan_resumer.py: Recovery for stalled multi-agent plans
"""

from orchestration.types import AgentCapability  # canonical definition (#6192)

from .agent_router import AgentRouter, TaskAgentScorer
from .collaboration_coordinator import CollaborationCoordinator
from .execution_strategies import ExecutionStrategyHandler
from .subagent_dispatcher import SubagentDispatcher
from .success_criteria import (
    CriteriaResult,
    EvaluationResult,
    SuccessCriteria,
    SuccessCriteriaEvaluator,
    SuccessCriteriaType,
)
from .types import (
    FALLBACK_TIERS,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    WorkflowPlan,
)
from .workflow_planning import StrategyPlanner
from .workflow_runner import WorkflowRunner

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
    "StrategyPlanner",
    # Issue #3293: success criteria
    "SuccessCriteriaType",
    "SuccessCriteria",
    "CriteriaResult",
    "EvaluationResult",
    "SuccessCriteriaEvaluator",
    # Execution engine (#5058)
    "WorkflowRunner",
    # Collaborators extracted from WorkflowRunner (#6393/#6392)
    # GH #6819: AgentRouter renamed → TaskAgentScorer; AgentRouter kept as compat alias.
    "TaskAgentScorer",
    "AgentRouter",
    "CollaborationCoordinator",
    # Subagent dispatcher relocated from services/orchestration (#6822)
    "SubagentDispatcher",
]
