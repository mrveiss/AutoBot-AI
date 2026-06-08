# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration Types Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Issue #6951 Phase 2B: ``AgentTask`` and ``WorkflowPlan`` are now thin subclasses
of the canonical ``autobot_shared.workflow.WorkflowTask`` / ``WorkflowPlan``.
The local definitions only add behaviour the canonical shapes intentionally
omit (task lifecycle methods + structured success criteria), keeping fields
in one place.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, FrozenSet, List

if TYPE_CHECKING:
    from orchestration.success_criteria import SuccessCriteria

from autobot_shared.workflow import ExecutionStrategy as ExecutionStrategy  # noqa: F401  # re-export
from autobot_shared.workflow import WorkflowPlan as _SharedWorkflowPlan
from autobot_shared.workflow import WorkflowTask
from orchestration.types import AgentCapability as AgentCapability  # noqa: F401  # re-export
from orchestration.types import AgentPerformance as AgentPerformance  # noqa: F401  # re-export

# Module-level frozenset for fallback tier checks
FALLBACK_TIERS: FrozenSet[str] = frozenset({"basic", "emergency"})


# #7121: lifecycle methods (start_execution, complete_execution,
# fail_execution, get_execution_time, can_retry, increment_retry,
# get_enhanced_inputs, to_completed_result, to_failed_result) moved
# to canonical WorkflowTask in autobot_shared/workflow/types.py.
# AgentTask is now a pure alias preserving the historical name —
# every consumer of `enhanced_orchestration.types.AgentTask` gets the
# canonical type with all 9 lifecycle methods inherited automatically.
# Original extraction: Issue #372 (feature-envy reduction).
AgentTask = WorkflowTask


@dataclass
class WorkflowPlan(_SharedWorkflowPlan):
    """Enhanced workflow plan with structured success criteria.

    Inherits every field from ``autobot_shared.workflow.WorkflowPlan`` (#6951
    Phase 1b). ``structured_criteria`` (#3293) lives here, not on the canonical
    shape, because it depends on backend-only ``SuccessCriteria`` semantics for
    partial/full/failed evaluation.
    """

    structured_criteria: List["SuccessCriteria"] = field(default_factory=list)


@dataclass
class WorkflowDependencies:
    """Groups the callable dependencies injected into ExecutionStrategyHandler (#6422).

    Replaces 6 positional Callable params with a single named container, making
    the constructor testable and the dependency surface explicit.
    """

    execute_single_task: Callable
    topological_sort_tasks: Callable
    dependencies_met: Callable
    group_pipeline_stages: Callable
    enhance_task_for_collaboration: Callable
    coordinate_collaboration: Callable
