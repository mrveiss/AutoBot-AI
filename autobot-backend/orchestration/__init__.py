# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Orchestration Package

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Provides agent orchestration, workflow planning, and auto-documentation.

This package contains:
- types: Enums and dataclasses for orchestration
- agent_registry: Agent registration and management
- workflow_planner: Workflow step planning and estimation
- workflow_executor: Workflow execution with agent coordination
- workflow_documentation: Auto-documentation and knowledge extraction
- dag_executor: DAG-based execution with condition/branch routing (#2140)
"""

from .agent_registry import AgentRegistry, get_default_agents
from .dag_executor import DAGExecutor, NodeType, WorkflowDAG, build_dag, workflow_has_condition_nodes
from .types import (
    AgentCapability,
    AgentInteraction,
    AgentProfile,
    DocumentationType,
    WorkflowDocumentation,
    WorkflowPlan,
    WorkflowStep,
)
from .workflow_documentation import WorkflowDocumenter
from .workflow_executor import WorkflowExecutor
from .workflow_planner import WorkflowPlanner

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
    "WorkflowPlanner",
    # DAG execution (#2140)
    "DAGExecutor",
    "NodeType",
    "WorkflowDAG",
    "build_dag",
    "workflow_has_condition_nodes",
]
