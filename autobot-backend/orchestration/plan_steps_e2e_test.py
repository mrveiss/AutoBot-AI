#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""End-to-end coverage for ``Orchestrator.plan_workflow_steps``.

#13730: this file used to print a step count inside a bare ``except Exception``
and assert nothing at all, so it reported success for the entire period
``plan_workflow_steps`` returned an empty list on every call (#13699). It now
asserts the plan it claims to exercise, and reads the canonical
``WorkflowTask`` field names whose absence broke every caller.
"""

import asyncio

from autobot_shared.workflow import WorkflowTask
from orchestrator import Orchestrator, TaskComplexity

# ``TaskComplexity.RESEARCH`` / ``INSTALL`` / ``SECURITY_SCAN`` all carry the
# value "complex", which makes them Enum *aliases* of ``COMPLEX`` rather than
# distinct members. SIMPLE and COMPLEX are therefore the only two plans that
# exist; the previous four-element list exercised COMPLEX three times.
EXPECTED_STEP_COUNT = {TaskComplexity.SIMPLE: 1, TaskComplexity.COMPLEX: 3}


async def test_plan_workflow_steps_returns_a_real_plan():
    """Every complexity produces a populated plan of canonical WorkflowTasks."""
    orchestrator = Orchestrator()

    for complexity, expected in EXPECTED_STEP_COUNT.items():
        steps = await orchestrator.plan_workflow_steps("test message", complexity)

        assert len(steps) == expected, f"{complexity.value}: expected {expected} steps, got {len(steps)}"
        assert all(isinstance(step, WorkflowTask) for step in steps)

        # Canonical names only — the retired ``id`` / ``user_approval_required``
        # are exactly what every caller was still reading (#13730).
        assert [step.task_id for step in steps] == [f"step_{i + 1}" for i in range(expected)]
        assert all(step.action for step in steps)
        assert all(isinstance(step.requires_approval, bool) for step in steps)
        assert all(step.inputs.get("query") == "test message" for step in steps)
        assert all(step.estimated_duration_seconds > 0 for step in steps)


async def test_complex_plan_dependencies_resolve_within_the_plan():
    """Dependency ids must name real tasks — callers build their edges from them."""
    orchestrator = Orchestrator()
    steps = await orchestrator.plan_workflow_steps("test message", TaskComplexity.COMPLEX)

    task_ids = {step.task_id for step in steps}
    for step in steps:
        for dependency in step.dependencies:
            assert dependency in task_ids, f"{step.task_id} depends on unknown task {dependency}"

    # The COMPLEX plan is a chain, so at least one edge must exist; a plan with
    # no dependencies at all would mean the ordering contract was lost.
    assert any(step.dependencies for step in steps)


if __name__ == "__main__":
    asyncio.run(test_plan_workflow_steps_returns_a_real_plan())
    asyncio.run(test_complex_plan_dependencies_resolve_within_the_plan())
