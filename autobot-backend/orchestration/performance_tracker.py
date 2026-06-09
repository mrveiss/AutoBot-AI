# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unified agent performance tracker for orchestration."""

import time
from typing import TYPE_CHECKING, Any, Dict

from autobot_shared.logging_manager import get_logger
from orchestration.types import AgentPerformance

if TYPE_CHECKING:
    from enhanced_orchestration.types import WorkflowPlan

logger = get_logger("performance_tracker")


class PerformanceTracker:
    """Tracks AgentPerformance for the multi-agent execution engine.

    Single source of truth for per-agent success/failure/timing metrics.
    Replaces the three separate performance-update methods that existed in
    Orchestrator prior to issue #5058.
    """

    def __init__(self, agent_capabilities: Dict[str, Any]) -> None:
        self.agent_performance: Dict[str, Any] = {
            agent: AgentPerformance(agent_type=agent) for agent in agent_capabilities
        }

    def update(self, agent_type: str, success: bool, execution_time: float) -> None:
        """Record one task outcome for the given agent type."""
        if agent_type not in self.agent_performance:
            return
        perf = self.agent_performance[agent_type]
        perf.total_tasks += 1
        if success:
            perf.successful_tasks += 1
        else:
            perf.failed_tasks += 1
        perf.average_execution_time = (
            perf.average_execution_time * (perf.total_tasks - 1) + execution_time
        ) / perf.total_tasks
        perf.reliability_score = perf.successful_tasks / perf.total_tasks
        perf.last_update = time.time()

    def update_from_plan(self, plan: "WorkflowPlan", results: Dict[str, Any]) -> None:
        """Bulk-update performance from a completed WorkflowPlan result set."""
        for task in plan.tasks:
            result = results.get(task.task_id, {})
            if result:
                self.update(
                    task.agent_type,
                    result.get("status") == "completed",
                    result.get("execution_time", 0),
                )

    def report(self) -> Dict[str, Any]:
        """Return serialisable performance summary keyed by agent type."""
        return {
            agent: {
                "total_tasks": perf.total_tasks,
                "success_rate": perf.reliability_score,
                "average_time": perf.average_execution_time,
                "last_update": perf.last_update,
            }
            for agent, perf in self.agent_performance.items()
        }
