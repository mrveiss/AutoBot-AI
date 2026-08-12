# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Chat-driven workflow plans must reflect the request (#13809).

#13730 unblocked `create_workflow_from_chat_request`, which had returned `None`
— and therefore HTTP 500 — for every request. The path is live again, but what
it produces is the same three placeholder steps whatever was asked. A silent
no-op is harder to notice than a 500, so the fix traded a visible failure for an
invisible one.

Two independent reasons the request never reaches the command:

1. `orchestrator.plan_workflow_steps` returns a fixed skeleton with the actions
   `analyze_request` / `execute_plan` / `synthesize_results`. It puts the request
   in `inputs["query"]` and never derives an action from it. This is *not* the
   LLM planner — `orchestrator.create_workflow_plan` does real planning, and this
   path does not call it.
2. `_extract_command_from_step` looks for `inputs["command"]`, which this plan
   never sets, then keyword-matches the *action* — but the three fixed actions
   match none of its branches, so every step falls through to `echo 'Executing:
   {action}'`.

The two tests below are marked `xfail(strict=True)` deliberately. They describe
the behaviour the endpoint is supposed to have, so when #13809 is fixed they
XPASS — which *fails* — and whoever fixes it must remove the markers. A plain
assertion of today's broken behaviour would instead have to be rewritten, and a
non-strict xfail would go quietly green and re-arm, hiding any later regression.
That is the property #13866 established and #13686 proved out.
"""

import asyncio
from types import SimpleNamespace

import pytest

from autobot_types import TaskComplexity


def _plan(request: str):
    """The step skeleton this endpoint actually builds for *request*."""
    from orchestrator import Orchestrator

    planner = Orchestrator.plan_workflow_steps.__get__(SimpleNamespace())
    return asyncio.run(planner(request, TaskComplexity.COMPLEX))


def _commands(request: str):
    """The commands the chat path would execute for *request*."""
    from services.workflow_automation.manager import WorkflowAutomationManager

    extract = WorkflowAutomationManager._extract_command_from_step.__get__(SimpleNamespace())
    return [extract(step) for step in _plan(request)]


def test_the_plan_is_a_fixed_skeleton_today():
    """Characterises the defect so the claim is checked, not asserted in prose.

    This one is NOT xfail: it is the evidence that the two below describe a real
    gap rather than an imagined one. It fails when the skeleton stops being fixed,
    at which point it should be deleted along with the markers.
    """
    actions = [s.action for s in _plan("install docker and wipe logs")]

    assert actions == ["analyze_request", "execute_plan", "synthesize_results"]


@pytest.mark.xfail(
    strict=True,
    reason="#13809: plan_workflow_steps returns a fixed skeleton; the request only "
    "reaches inputs['query'] and never shapes an action",
)
def test_two_different_requests_produce_different_plans():
    """AC #13809: a chat request must produce steps that reflect the request."""
    install = [s.action for s in _plan("install docker")]
    report = [s.action for s in _plan("summarise last week's deploy failures")]

    assert install != report


@pytest.mark.xfail(
    strict=True,
    reason="#13809: every step falls through to echo — the fixed actions match no "
    "branch of _extract_command_from_step and inputs['command'] is never set",
)
def test_commands_are_not_all_echoes():
    """A workflow that only echoes its own step names does no work."""
    commands = _commands("install docker and wipe logs")

    assert not all(c.startswith("echo 'Executing:") for c in commands)


def test_the_user_request_never_reaches_a_command():
    """Security property worth pinning while the path is live (#13809).

    The endpoint generates shell commands and `auto_start` defaults to True, so
    it matters that hostile text cannot reach one. It cannot: the extractor only
    ever emits a literal echo of a fixed action name, or one of two hardcoded
    strings on keyword match. This test stays after #13809 is fixed — whatever
    planner the endpoint moves to must keep this true.
    """
    hostile = "install docker; rm -rf / #"

    for command in _commands(hostile):
        assert "rm -rf" not in command
        assert hostile not in command
