# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified Orchestration Package  (#7379 boundary, #10666 B3 consolidation)

Issue #10666 Batch B3: enhanced_orchestration/ merged INTO orchestration/.
This is now the single package for ALL orchestration concerns — both
single-workflow execution primitives AND multi-agent coordination.

This package contains:
- types: Enums and dataclasses (AgentCapability, AgentPerformance,
  AgentTask/WorkflowTask alias, WorkflowPlan with structured_criteria,
  WorkflowDependencies, FALLBACK_TIERS, ...)
- agent_registry: Agent registration and management
- agent_router: TaskAgentScorer / AgentRouter — workflow-task scoring (#6819)
- workflow_planner: Map capability requirements to available agents
- workflow_planning: StrategyPlanner — multi-agent strategy & plan building
- workflow_runner: WorkflowRunner — multi-agent execution engine (#5058)
- workflow_executor: Execute a single workflow step by step
- workflow_documentation: Auto-documentation and knowledge extraction
- collaboration_coordinator: Redis pub/sub collaboration layer (#6393)
- subagent_dispatcher: Autonomous subagent spawning for parallel workstreams
- blocked_plan_resumer: Recovery for stalled multi-agent plans (#7431)
- execution_strategies/: Strategy implementations (sequential/parallel/
  pipeline/collaborative/adaptive) — ExecutionStrategyHandler dispatcher
- success_criteria: Structured success criteria evaluation (#3293)
- dag_executor: DAG-based execution with condition/branch routing (#2140)
- graph_runner: Unified graph model (AutoBotGraph, GraphRunner) (#3228)
- error_handler: Step-level error handling and checkpointing (#2154)
- execution_modes: Dry-run validation and debug mode (#2148)
- sub_workflow: Sub-workflow composition — workflows as reusable building blocks (#2143)
- variable_resolver: Cross-step variable piping (#2141)
- causal_executor / causal_error_recovery / causal_validator: Causal DAG
  execution with automated error recovery (#5058)
- workflow_memory: Per-run memory scoped to a workflow execution
- performance_tracker: Timing and cost metrics for workflow runs (#5058)
"""

from autobot_shared.workflow import ExecutionStrategy

from .agent_registry import AgentRegistry, get_default_agents
from .agent_router import AgentRouter, TaskAgentScorer
from .blocked_plan_resumer import BlockedPlanResumer
from .causal_error_recovery import CausalErrorRecovery, RecoveryPlan, get_recovery_recommender
from .causal_executor import CausalExecutor

# GH #6816: causal subsystem — wired as recoverable execution mode in StepErrorHandler
from .causal_models import CausalMetadata, EffectTrace
from .collaboration_coordinator import CollaborationCoordinator
from .dag_executor import (
    DAGExecutor,
    NodeType,
    WorkflowDAG,
    build_dag,
    workflow_has_condition_nodes,
)
from .dag_graph_adapter import DAGGraphExecutor, build_dag_graph
from .error_handler import (
    BackoffStrategy,
    StepCheckpoint,
    StepErrorAction,
    StepErrorConfig,
    StepErrorHandler,
    WorkflowCheckpointManager,
)
from .execution_modes import (
    DebugController,
    DryRunReport,
    DryRunValidator,
    ExecutionMode,
    StepPlan,
)
from .execution_strategies import ExecutionStrategyHandler
from .graph_runner import (
    END,
    START,
    AutoBotGraph,
    BackoffMode,
    CompiledGraph,
    GraphRunner,
    GraphStepEvent,
    NodeRetryConfig,
    StepEventEmitter,
    StepEventSink,
    StepEventType,
)
from .sub_workflow import (
    MAX_NESTING_DEPTH,
    SubWorkflowExecutor,
    SubWorkflowStep,
    extract_sub_workflow_step,
    is_sub_workflow_step,
)
from .subagent_dispatcher import SubagentDispatcher, SubagentTask, get_subagent_dispatcher
from .success_criteria import (  # noqa: F401
    CriteriaResult,
    EvaluationResult,
    SuccessCriteria,
    SuccessCriteriaEvaluator,
    SuccessCriteriaType,
)
from .types import (
    FALLBACK_TIERS,
    AgentCapability,
    AgentInteraction,
    AgentPerformance,
    AgentProfile,
    AgentTask,
    DocumentationType,
    WorkflowDependencies,
    WorkflowDocumentation,
    WorkflowPlan,
    WorkflowStep,
)
from .variable_resolver import StepOutput, VariableResolver, resolve_variables
from .workflow_documentation import WorkflowDocumenter
from .workflow_executor import WorkflowExecutor
from .workflow_memory import WorkflowMemory
from .workflow_planner import WorkflowPlanner
from .workflow_planning import StrategyPlanner
from .workflow_runner import WorkflowRunner

__all__ = [
    # Canonical strategy enum (re-exported from autobot_shared.workflow for convenience)
    "ExecutionStrategy",
    # Types and dataclasses (single-workflow)
    "AgentCapability",
    "AgentInteraction",
    "AgentPerformance",
    "AgentProfile",
    "DocumentationType",
    "WorkflowDocumentation",
    "WorkflowPlan",
    "WorkflowStep",
    # Multi-agent types (folded in from enhanced_orchestration #10666 B3)
    "FALLBACK_TIERS",
    "AgentTask",
    "WorkflowDependencies",
    # Agent management
    "AgentRegistry",
    "get_default_agents",
    # Agent routing / scoring (#6819)
    "TaskAgentScorer",
    "AgentRouter",
    # Workflow components (single-workflow)
    "WorkflowDocumenter",
    "WorkflowExecutor",
    "WorkflowMemory",
    "WorkflowPlanner",
    # Multi-agent coordination (folded in from enhanced_orchestration #10666 B3)
    "StrategyPlanner",
    "WorkflowRunner",
    "CollaborationCoordinator",
    "SubagentDispatcher",
    "SubagentTask",
    "get_subagent_dispatcher",
    "BlockedPlanResumer",
    "ExecutionStrategyHandler",
    # Unified graph model (#3228)
    "END",
    "START",
    "AutoBotGraph",
    "BackoffMode",
    "CompiledGraph",
    "DAGGraphExecutor",
    "GraphRunner",
    "GraphStepEvent",
    "NodeRetryConfig",
    "StepEventEmitter",
    "StepEventSink",
    "StepEventType",
    "build_dag_graph",
    # Sub-workflow composition (#2143)
    "MAX_NESTING_DEPTH",
    "SubWorkflowExecutor",
    "SubWorkflowStep",
    "extract_sub_workflow_step",
    "is_sub_workflow_step",
    # DAG execution (#2140)
    "DAGExecutor",
    "NodeType",
    "WorkflowDAG",
    "build_dag",
    "workflow_has_condition_nodes",
    # Variable piping (#2141)
    "StepOutput",
    "VariableResolver",
    "resolve_variables",
    # Error handling and checkpointing (#2154)
    "BackoffStrategy",
    "StepCheckpoint",
    "StepErrorAction",
    "StepErrorConfig",
    "StepErrorHandler",
    "WorkflowCheckpointManager",
    # Execution modes: dry-run + debug (#2148)
    "DebugController",
    "DryRunReport",
    "DryRunValidator",
    "ExecutionMode",
    "StepPlan",
    # Performance tracking (#5058)
    "PerformanceTracker",
    # Success criteria evaluation (GH #3293/#6832)
    "SuccessCriteriaType",
    "SuccessCriteria",
    "CriteriaResult",
    "EvaluationResult",
    "SuccessCriteriaEvaluator",
    # Causal DAG execution and error recovery (GH #6816)
    "CausalExecutor",
    "CausalErrorRecovery",
    "CausalMetadata",
    "EffectTrace",
    "RecoveryPlan",
    "get_recovery_recommender",
]

from .performance_tracker import PerformanceTracker
