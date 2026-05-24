# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Execution Primitives  (#7379 boundary)

BOUNDARY: this package owns single-workflow execution building blocks.
Use it when you need to BUILD or RUN a single workflow.

The sibling `enhanced_orchestration/` package owns multi-agent coordination
(strategy selection, agent routing, Redis pub/sub collaboration, subagent
dispatch). New multi-agent features go there; new single-workflow primitives
go here.

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Provides agent orchestration, workflow planning, and auto-documentation.

This package contains:
- types: Enums and dataclasses for workflow plans, steps, and agents
- agent_registry: Agent registration and management
- workflow_planner: Map capability requirements to available agents
- workflow_executor: Execute a single workflow step by step
- workflow_documentation: Auto-documentation and knowledge extraction
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

from .agent_registry import AgentRegistry, get_default_agents
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
from .types import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    DocumentationType,
    WorkflowDocumentation,
    WorkflowPlan,
    WorkflowStep,
)
from .variable_resolver import StepOutput, VariableResolver, resolve_variables
from .workflow_documentation import WorkflowDocumenter
from .success_criteria import SuccessCriteriaEvaluator  # noqa: F401
from .workflow_executor import WorkflowExecutor
from .workflow_memory import WorkflowMemory
from .workflow_planner import WorkflowPlanner

# GH #6816: causal subsystem — wired as recoverable execution mode in StepErrorHandler
from .causal_models import CausalMetadata, EffectTrace
from .causal_error_recovery import CausalErrorRecovery, RecoveryPlan, get_recovery_recommender
from .causal_executor import CausalExecutor

__all__ = [
    # Types and dataclasses
    "AgentCapability",
    "AgentInteraction",
    "AgentProfile",
    "DocumentationType",
    "WorkflowDocumentation",
    "WorkflowPlan",
    "WorkflowStep",
    # Agent management
    "AgentRegistry",
    "get_default_agents",
    # Workflow components
    "WorkflowDocumenter",
    "WorkflowExecutor",
    "WorkflowMemory",
    "WorkflowPlanner",
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
    # Success criteria evaluation (GH #6832)
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
