# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Orchestration Types and Data Classes

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Issue #6951 Phase 3: ``WorkflowStep`` and ``WorkflowPlan`` are now aliases
to the canonical ``autobot_shared.workflow`` shapes — completing the
consolidation that #381 should have produced. Both shapes had zero
production callers (only re-exports through ``__init__.py``); the alias
preserves the import path so any future caller of ``orchestration.types``
gets the canonical type, per the wire-in-not-delete rule.

Issue #10666 Batch B3: Folded in symbols previously owned by
``enhanced_orchestration/types.py`` (FALLBACK_TIERS, WorkflowDependencies,
WorkflowPlan subclass with structured_criteria) as part of the full
enhanced_orchestration → orchestration consolidation.

Contains enums and dataclasses for agent orchestration.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet, List, Set

from autobot_shared.workflow import WorkflowPlan as _SharedWorkflowPlan
from autobot_shared.workflow import WorkflowTask as _WorkflowTask
from constants.status_enums import TaskStatus

if TYPE_CHECKING:
    from orchestration.success_criteria import SuccessCriteria

# Transitional aliases — Phase 3 of #6951 consolidates the two #381-derivative
# shapes here onto canonical types. ``orchestration.types`` had zero importers
# of these names by the time this landed (verified on Dev_new_gui), so the
# alias is risk-free and preserves the import path for any future caller.
WorkflowStep = _WorkflowTask

# Canonical set of fallback tier names (formerly enhanced_orchestration.types.FALLBACK_TIERS).
FALLBACK_TIERS: FrozenSet[str] = frozenset({"basic", "emergency"})


@dataclass
class WorkflowPlan(_SharedWorkflowPlan):
    """Enhanced workflow plan with structured success criteria.

    Inherits every field from ``autobot_shared.workflow.WorkflowPlan`` (#6951
    Phase 1b). ``structured_criteria`` (#3293) lives here — it depends on
    backend-only ``SuccessCriteria`` semantics for partial/full/failed evaluation.

    Folded in from enhanced_orchestration.types (issue #10666 B3).
    """

    structured_criteria: List["SuccessCriteria"] = field(default_factory=list)


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
    EXECUTION = "execution"
    MONITORING = "monitoring"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    OPTIMIZATION = "optimization"
    SECURITY = "security"


class DocumentationType(Enum):
    """Types of auto-generated documentation."""

    WORKFLOW_SUMMARY = "workflow_summary"
    AGENT_INTERACTION = "agent_interaction"
    DECISION_LOG = "decision_log"
    PERFORMANCE_REPORT = "performance_report"
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"
    ERROR_ANALYSIS = "error_analysis"


@dataclass
class AgentPerformance:
    """Track agent performance metrics."""

    agent_type: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    average_execution_time: float = 0.0
    reliability_score: float = 1.0
    capability_scores: Dict[AgentCapability, float] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)


@dataclass
class AgentProfile:
    """Runtime state for a specific agent instance (workload, success rate, availability).

    Distinct from ``AgentCapabilityDescriptor`` (agents.agent_orchestration.types),
    which is a static per-type descriptor (model_size, strengths, limitations).

    ``allowed_work``/``forbidden_work`` (GH#11139) are the declarative capability
    manifest — the single source for an agent's least-privilege boundary. Routing
    (orchestrator ``agent_capabilities``) and tool enforcement (agent loop
    ``forbidden_tools``) both derive from this profile rather than duplicating the
    boundary in separate places.
    """

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
    # GH#11139: declarative capability manifest — tool names this agent may / may
    # not invoke. ``forbidden_work`` is hard-blocked before approval in the loop.
    allowed_work: List[str] = field(default_factory=list)
    forbidden_work: List[str] = field(default_factory=list)


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
    outcome: str = TaskStatus.PENDING.value


@dataclass
class WorkflowDependencies:
    """Groups the callable dependencies injected into ExecutionStrategyHandler (#6422).

    Replaces 6 positional Callable params with a single named container, making
    the constructor testable and the dependency surface explicit.

    Folded in from enhanced_orchestration.types (issue #10666 B3).
    """

    execute_single_task: Callable
    topological_sort_tasks: Callable
    dependencies_met: Callable
    group_pipeline_stages: Callable
    enhance_task_for_collaboration: Callable
    coordinate_collaboration: Callable


# AgentTask is the canonical WorkflowTask alias — re-export for callers
# previously importing from enhanced_orchestration.types (issue #10666 B3).
AgentTask = _WorkflowTask
