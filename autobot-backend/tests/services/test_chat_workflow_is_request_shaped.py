# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Chat-driven workflow plans must reflect the request (#13809).

#13730 unblocked `create_workflow_from_chat_request`, which had returned `None`
— and therefore HTTP 500 — for every request. What it then produced was the
same three placeholder steps whatever was asked: `plan_workflow_steps` returned
a fixed skeleton, and every step fell through to `echo 'Executing: {action}'`.

The chat path now plans with `create_workflow_plan`, the canonical LLM planner,
with the shell-command contract on (owner ruling 2026-10-03, recorded on #13809).
These tests drive the REAL planner -- prompt builder, response parser and plan
builder -- with only the LLM call replaced. The fake LLM derives its plan from
the goal it finds in the prompt, so a request that never reached the prompt, or
a plan that never reached the steps, fails here.

The old security test asserted that user text never reaches a generated
command. That held only because the endpoint was hollow: with a real planner the
command is LLM-authored from the user's text by design. It is replaced by the
property that does hold -- no generated command runs without human approval.
"""

import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.llm_failsafe_agent import LLMTier

_GOAL = re.compile(r"^\s*Goal: (.*)$", re.MULTILINE)


class _FakeLLM:
    """Plans one task per request, its command built from the goal in the prompt."""

    def __init__(self, with_command: bool = True):
        self.with_command = with_command
        self.prompts: list[str] = []

    async def __call__(self, prompt, context=None):
        self.prompts.append(prompt)
        goal = _GOAL.search(prompt).group(1)
        inputs = {"command": f"planned-for: {goal}"} if self.with_command else {}
        plan = {"strategy": "sequential", "tasks": [{"agent": "system", "action": f"do {goal}", "inputs": inputs}]}
        return SimpleNamespace(tier_used=LLMTier.PRIMARY, content=json.dumps(plan))


@pytest.fixture
def chat(monkeypatch):
    """A manager on a real Orchestrator whose only fake is the LLM call."""
    from orchestrator import Orchestrator
    from services.workflow_automation.manager import WorkflowAutomationManager

    llm = _FakeLLM()
    monkeypatch.setattr("agents.llm_failsafe_agent.get_robust_llm_response", llm)
    orchestrator = Orchestrator()
    # Retrieval and skill binding are advisory and best-effort; neither is under test.
    orchestrator._fetch_planning_context = AsyncMock(side_effect=lambda *_a, **_k: {})
    orchestrator._strategy_planner._bind_skill_to_task = AsyncMock(return_value=None)
    manager = object.__new__(WorkflowAutomationManager)
    manager.orchestrator = orchestrator
    manager.create_automated_workflow = AsyncMock(return_value="workflow-1")
    return SimpleNamespace(manager=manager, llm=llm)


def _steps(chat, request: str):
    chat.manager.create_automated_workflow.reset_mock()
    workflow_id = asyncio.run(chat.manager.create_workflow_from_chat_request(request, "session-1"))
    assert workflow_id == "workflow-1", f"no workflow was created for {request!r}"
    return chat.manager.create_automated_workflow.await_args.kwargs["steps"]


def test_two_different_requests_produce_different_plans(chat):
    """AC #13809: a chat request must produce steps that reflect the request."""
    install = [s.command for s in _steps(chat, "install docker")]
    report = [s.command for s in _steps(chat, "summarise last week's deploy failures")]

    assert install != report
    assert install == ["planned-for: install docker"]


def test_commands_are_not_all_echoes(chat):
    """A workflow that only echoes its own step names does no work."""
    commands = [s.command for s in _steps(chat, "install docker and wipe logs")]

    assert commands and not any(c.startswith("echo 'Executing:") for c in commands)


def test_the_chat_path_asks_the_planner_for_commands(chat):
    """The planner's default prompt asks for agent tasks; only this path asks for commands."""
    from orchestration.orchestrator_prompts import _SHELL_COMMAND_CONTRACT, build_planning_prompt

    _steps(chat, "install docker")

    assert _SHELL_COMMAND_CONTRACT in chat.llm.prompts[-1]
    assert _SHELL_COMMAND_CONTRACT not in build_planning_prompt("install docker", "{}")


def test_a_plan_with_no_command_creates_no_workflow(chat):
    """The hollow workflow is refused, not replaced by placeholder echoes."""
    chat.llm.with_command = False

    workflow_id = asyncio.run(chat.manager.create_workflow_from_chat_request("install docker", "s"))

    assert workflow_id is None
    chat.manager.create_automated_workflow.assert_not_awaited()


def test_a_generated_command_requires_confirmation_on_its_step(chat):
    """Owner ruling #13809: user text reaches the command by design, so the step is gated."""
    hostile = "install docker; rm -rf / #"

    steps = _steps(chat, hostile)

    assert [s.command for s in steps] == [f"planned-for: {hostile}"]
    assert all(s.requires_confirmation is True for s in steps)


def test_the_route_starts_nothing_unless_asked(monkeypatch):
    """Owner ruling #13809: by default the plan is presented for approval, never started."""
    from services.workflow_automation import routes

    manager = SimpleNamespace(
        create_workflow_from_chat_request=AsyncMock(return_value="workflow-1"),
        present_plan_for_approval=AsyncMock(return_value=None),
        start_workflow_execution=AsyncMock(),
    )
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)

    body = {"user_request": "install docker", "session_id": "s"}
    result = asyncio.run(routes.create_workflow_from_chat(body, current_user={"username": "u"}))

    assert result["status"] == "awaiting_approval"
    manager.present_plan_for_approval.assert_awaited_once()
    manager.start_workflow_execution.assert_not_awaited()


# ---------------------------------------------------------------------------
# #13809 review: what counts as a runnable command, and what happens to a
# dependency the planner could never have resolved.
# ---------------------------------------------------------------------------


def _task(task_id: str, inputs, dependencies=None):
    return SimpleNamespace(task_id=task_id, action=f"act {task_id}", inputs=inputs, dependencies=dependencies or [])


@pytest.mark.parametrize(
    "label,inputs,expected",
    [
        ("a plain string command", {"command": "ls -la"}, "ls -la"),
        ("a list command", {"command": ["ls", "-la"]}, None),
        ("a dict command", {"command": {"argv": ["ls"]}}, None),
        ("an integer command", {"command": 7}, None),
        ("an empty string", {"command": ""}, None),
        ("whitespace only", {"command": "   "}, None),
        ("no command key at all", {}, None),
        ("inputs is a string, not a dict", "command=ls", None),
        ("inputs is None", None, None),
    ],
)
def test_only_a_non_empty_string_command_is_runnable(label, inputs, expected):
    """`WorkflowStep.command` is declared `str` and not validated at runtime.

    The filter used to be truthiness alone, so a non-empty list or dict passed
    it and travelled into workflow status and snapshots as a `command`. A
    non-dict `inputs` raised `AttributeError` into the broad handler and became
    a plain `return None` -- the #13730 shape, an error disappearing into a
    "no workflow" result.
    """
    from services.workflow_automation.manager import _planned_command

    assert _planned_command(_task("t1", inputs)) == expected, (
        f"{label} should map to {expected!r}; a truthiness check accepts the "
        "non-string cases and puts a non-str into a field typed str"
    )


def test_a_dependency_that_cannot_resolve_is_logged_rather_than_dropped_in_silence(caplog):
    """The planner's schema asks for ids it never gives the model.

    `dependencies: ["task_ids"]` is requested, but no task carries an id field
    the model can assign -- ids are generated server-side. So every reference
    the model writes is unresolvable by construction, and filtering it left two
    steps that look independent when the plan said one waits for the other.
    The filter is still right; the silence was not. Root cause: #17979.
    """
    from services.workflow_automation.manager import WorkflowAutomationManager

    manager = object.__new__(WorkflowAutomationManager)
    tasks = [
        _task("gen-1", {"command": "first"}),
        _task("gen-2", {"command": "second"}, dependencies=["task_0", "gen-1"]),
    ]

    with caplog.at_level("WARNING"):
        steps = manager._steps_from_plan(tasks, "do the thing")

    assert [s.step_id for s in steps] == ["step_1", "step_2"]
    # The resolvable one survives; only the model-invented id is dropped.
    assert steps[1].dependencies == ["step_1"]

    warnings = " ".join(r.getMessage() for r in caplog.records if r.levelname == "WARNING")
    assert "task_0" in warnings, (
        "an unresolvable dependency was filtered without a word in the log, so a plan whose "
        f"ordering was silently discarded looks identical to one that had none: {warnings!r}"
    )
    assert "gen-1" not in warnings.replace(
        "step_1", ""
    ), "a dependency that DID resolve must not be reported as dropped"


def test_nothing_is_logged_when_every_dependency_resolves(caplog):
    """The contrast pair: without it the assertion above is satisfied by a
    module that warns on every plan, which would train the warning away."""
    from services.workflow_automation.manager import WorkflowAutomationManager

    manager = object.__new__(WorkflowAutomationManager)
    tasks = [
        _task("gen-1", {"command": "first"}),
        _task("gen-2", {"command": "second"}, dependencies=["gen-1"]),
    ]

    with caplog.at_level("WARNING"):
        manager._steps_from_plan(tasks, "do the thing")

    dropped = [r.getMessage() for r in caplog.records if "did not resolve" in r.getMessage()]
    assert not dropped, f"a fully resolvable plan reported dropped dependencies: {dropped}"
