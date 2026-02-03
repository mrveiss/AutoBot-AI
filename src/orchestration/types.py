# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Orchestration Types and Data Classes

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains enums and dataclasses for agent orchestration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Set


class AgentCapability(Enum):
    """Agent capabilities for dynamic task assignment."""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    DOCUMENTATION = "documentation"
    CODE_GENERATION = "code_generation"
    SYSTEM_OPERATIONS = "system_operations"
    DATA_PROCESSING = "data_processing"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    WORKFLOW_COORDINATION = "workflow_coordination"


class DocumentationType(Enum):
    """Types of auto-generated documentation."""

    WORKFLOW_SUMMARY = "workflow_summary"
    AGENT_INTERACTION = "agent_interaction"
    DECISION_LOG = "decision_log"
    PERFORMANCE_REPORT = "performance_report"
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"
    ERROR_ANALYSIS = "error_analysis"


@dataclass
class AgentProfile:
    """Enhanced agent profile with capabilities and performance metrics."""

    agent_id: str
    agent_type: str
    capabilities: Set[AgentCapability]
    specializations: List[str]
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    availability_status: str = "available"
    current_workload: int = 0
    max_concurrent_tasks: int = 3
    success_rate: float = 1.0
    average_completion_time: float = 0.0
    preferred_task_types: List[str] = field(default_factory=list)


@dataclass
class WorkflowDocumentation:
    """Auto-generated documentation for workflow execution."""

    workflow_id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    documentation_type: DocumentationType
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    related_workflows: List[str] = field(default_factory=list)
    knowledge_extracted: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentInteraction:
    """Record of interaction between agents."""

    interaction_id: str
    timestamp: datetime
    source_agent: str
    target_agent: str
    interaction_type: str  # request, response, notification, collaboration
    message: Dict[str, Any]
    context: Dict[str, Any]
    outcome: str = "pending"


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow plan."""

    step_id: str
    action: str
    description: str
    agent_id: str
    required_capabilities: Set[AgentCapability]
    estimated_duration: float
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowPlan:
    """Complete workflow execution plan."""

    workflow_id: str
    title: str
    description: str
    steps: List[WorkflowStep]
    created_at: datetime
    estimated_total_duration: float
    status: str = "pending"
    approval_required: bool = True
    approved: bool = False
