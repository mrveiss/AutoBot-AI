# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Multi-Agent Orchestrator — backward-compatibility shim.

Issue #3393: The implementation has been moved to the enhanced_orchestration/
package (enhanced_orchestration/orchestrator.py).  This file re-exports the
public API so that any remaining callers continue to work during the transition.

Do NOT add new code here.  Import directly from enhanced_orchestration instead.
"""

# Re-export entire public API from the consolidated package
from enhanced_orchestration import (  # noqa: F401
    FALLBACK_TIERS,
    AgentCapability,
    AgentPerformance,
    AgentTask,
    CriteriaResult,
    EnhancedMultiAgentOrchestrator,
    EvaluationResult,
    ExecutionStrategy,
    SuccessCriteria,
    SuccessCriteriaEvaluator,
    SuccessCriteriaType,
    WorkflowPlan,
    WorkflowPlanner,
    create_and_execute_workflow,
    enhanced_orchestrator,
)

__all__ = [
    "AgentCapability",
    "ExecutionStrategy",
    "AgentTask",
    "WorkflowPlan",
    "AgentPerformance",
    "EnhancedMultiAgentOrchestrator",
    "enhanced_orchestrator",
    "create_and_execute_workflow",
    "FALLBACK_TIERS",
    "SuccessCriteriaType",
    "SuccessCriteria",
    "CriteriaResult",
    "EvaluationResult",
    "SuccessCriteriaEvaluator",
]
