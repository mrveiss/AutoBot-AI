# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard that TaskComplexity cannot silently collapse in a dict (issue #13806).

RESEARCH, INSTALL, and SECURITY_SCAN were removed because they were
aliases of COMPLEX.  A dict literal keyed on all five members collapsed
to two entries with last-write-wins behaviour.  This test asserts that
every current TaskComplexity member acts as a distinct dict key, and
that the scheduler applies the declared multiplier per complexity.
"""

from datetime import datetime, timezone

import pytest

from autobot_shared.status_enums import WorkflowStatus
from autobot_types import TaskComplexity
from constants.threshold_constants import WorkflowConfig
from workflow_scheduler import QueuedWorkflow, ScheduledWorkflow, WorkflowPriority, WorkflowQueue


def _make_workflow(complexity: TaskComplexity) -> ScheduledWorkflow:
    """Return a minimal ScheduledWorkflow for priority-score testing."""
    return ScheduledWorkflow(
        id="test-wf",
        name="test",
        template_id=None,
        user_message="test",
        scheduled_time=datetime.now(tz=timezone.utc),
        priority=WorkflowPriority.NORMAL,
        status=WorkflowStatus.SCHEDULED,
        created_at=datetime.now(tz=timezone.utc),
        complexity=complexity,
    )


def test_taskcomplexity_members_are_distinct_dict_keys():
    """Every member must act as its own dict key (no alias collapse)."""
    members = list(TaskComplexity)
    d = {m: m.value for m in members}
    assert len(d) == len(members), (
        f"Expected {len(members)} distinct dict keys, got {len(d)}. "
        f"Alias collapse detected: {d}"
    )
    assert TaskComplexity.SIMPLE in d
    assert TaskComplexity.COMPLEX in d


def test_calculate_priority_score_uses_complex_multiplier():
    """COMPLEX workflows get COMPLEXITY_COMPLEX, not a leaked alias value."""
    queue = WorkflowQueue()

    wf_complex = _make_workflow(TaskComplexity.COMPLEX)
    wf_simple = _make_workflow(TaskComplexity.SIMPLE)

    score_complex = queue._calculate_priority_score(wf_complex)
    score_simple = queue._calculate_priority_score(wf_simple)

    base = WorkflowPriority.NORMAL.value * WorkflowConfig.PRIORITY_BASE_MULTIPLIER
    expected_complex = base * WorkflowConfig.COMPLEXITY_COMPLEX
    expected_simple = base * WorkflowConfig.COMPLEXITY_SIMPLE

    assert score_complex == pytest.approx(expected_complex, rel=1e-9)
    assert score_simple == pytest.approx(expected_simple, rel=1e-9)
    assert score_complex > score_simple, (
        f"COMPLEX score ({score_complex}) should exceed SIMPLE ({score_simple})"
    )
