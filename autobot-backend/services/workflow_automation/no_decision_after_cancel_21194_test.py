# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No step decision is accepted once cancellation has started (#21194).

Reuses the #21101 harness: a parked step, a recording gate and a recording metrics sink.
"""

# flake8: noqa: F811
import asyncio

import pytest

from .models import StepNotAwaitingApproval, WorkflowStepStatus
from .withdraw_after_accept_21101_test import _Metrics, _post, parked  # noqa: F401

_HANDLERS = {"approve_step": "_approve_step", "skip_step": "_skip_step"}


def _start_cancel(parked):
    """Cancellation has started: the flag is set before the executor's first await."""
    parked.workflow.is_cancelled = True
    parked.recorder.withdrawn.clear()


@pytest.mark.parametrize("action", list(_HANDLERS))
def test_a_decision_after_cancel_started_is_refused_on_the_route(parked, action):
    _start_cancel(parked)
    assert _post(parked, action).status_code == 409
    assert parked.recorder.withdrawn == []
    assert parked.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL
    assert parked.workflow.current_step_index == 0
    assert parked.ran == []


@pytest.mark.parametrize("action", list(_HANDLERS))
def test_a_decision_after_cancel_started_withdraws_nothing_and_records_no_metric(parked, action):
    _start_cancel(parked)
    controller = parked.manager.controller
    controller.prometheus_metrics = _Metrics()
    with pytest.raises(StepNotAwaitingApproval):
        asyncio.run(getattr(controller, _HANDLERS[action])(parked.workflow, "s1", parked.manager.active_workflows))
    assert parked.recorder.withdrawn == []
    assert controller.prometheus_metrics.decisions == []


def test_a_skip_before_cancel_still_works(parked):
    assert _post(parked, "skip_step").status_code == 200
    assert parked.statuses[0] == WorkflowStepStatus.SKIPPED


@pytest.mark.parametrize("cancel_first", [True, False])
def test_a_race_between_cancel_and_skip_resolves_to_one_outcome(parked, cancel_first):
    controller = parked.manager.controller
    controller.prometheus_metrics = _Metrics()
    workflows = parked.manager.active_workflows
    cancel = parked.manager.executor.cancel_workflow(parked.workflow, workflows)
    skip = controller._skip_step(parked.workflow, "s1", workflows)

    async def _race():
        return await asyncio.gather(*((cancel, skip) if cancel_first else (skip, cancel)), return_exceptions=True)

    results = asyncio.run(_race())
    refused = [r for r in results if isinstance(r, StepNotAwaitingApproval)]
    skipped = parked.statuses[0] == WorkflowStepStatus.SKIPPED
    if cancel_first:
        assert len(refused) == 1 and not skipped and controller.prometheus_metrics.decisions == []
    else:
        assert not refused and skipped and controller.prometheus_metrics.decisions == ["skipped"]
