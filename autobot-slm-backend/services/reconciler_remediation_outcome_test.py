# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Remediation succeeds when the heartbeat returns, not when the restart exits 0 (#14344).

Observed live:

    14:24  Remediation successful for node <id>
    14:29  Remediation successful for node <id>
    ...    ten times, every five minutes
    15:13  Node <id> reachable but no heartbeat - marking degraded

The node never heartbeated once. Its agent was starting cleanly and being
rejected with a 401 (#14350), so the restart genuinely succeeded and the outcome
never happened.

The compounding part is the tracker: success **resets** the attempt counter, so
a restart that always "succeeds" can never reach `MAX_REMEDIATION_ATTEMPTS` and
`_create_max_attempts_event` never fires. It is not a remediation loop that
gives up — it is one that cannot.

These rules are structural because `reconciler.py` pulls in the DB layer, the
HTTP client and the service registry; the behaviour under test is which value
`success` is bound to, which is visible in the AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = (_BACKEND_ROOT / "services" / "reconciler.py").read_text(encoding="utf-8")
_TREE = ast.parse(_SOURCE)


def _function(name: str) -> ast.AST:
    for node in ast.walk(_TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found — this rule is pinned to the wrong name")


def test_the_functions_under_test_exist():
    """An empty parse would make every rule below vacuous."""
    assert _function("_remediate_node")
    assert _function("_heartbeat_returned")


def test_success_is_not_bound_to_the_restart_alone():
    """The defect verbatim: `success = await self._restart_service_via_ansible(...)`.

    Rebinding it that way is the whole bug, so it is asserted directly on the
    assignment rather than on the presence of the verification helper — a
    helper that exists but is not consulted would pass a weaker check.
    """
    func = _function("_remediate_node")

    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "success" not in targets:
            continue
        call_attrs = {
            getattr(inner.func, "attr", None) for inner in ast.walk(node.value) if isinstance(inner, ast.Call)
        }
        assert "_heartbeat_returned" in call_attrs, (
            "`success` is bound without consulting the heartbeat — a restart that achieves "
            "nothing would be recorded as remediation (#14344)"
        )


def test_the_restart_result_is_still_required():
    """Verification must be an AND, not a replacement.

    Treating a heartbeat as success without a successful restart would count an
    unrelated recovery — or a stale timestamp — as this remediation working.
    """
    func = _function("_remediate_node")
    names = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}

    assert "restarted" in names, "the restart result is no longer captured"
    assert "_restart_service_via_ansible" in _SOURCE


def test_a_failed_verification_returns_false_so_the_counter_advances():
    """Returning True on timeout would preserve the infinite-reset bug.

    The tracker resets `count` to 0 on success, so a verification that cannot
    fail leaves the loop unable to reach MAX_REMEDIATION_ATTEMPTS and unable to
    escalate — exactly the live behaviour.
    """
    func = _function("_heartbeat_returned")
    returns = [n for n in ast.walk(func) if isinstance(n, ast.Return)]
    constants = {n.value.value for n in returns if isinstance(n.value, ast.Constant)}

    assert False in constants, "_heartbeat_returned never returns False, so remediation can never fail"
    assert True in constants, "_heartbeat_returned never returns True, so it can never succeed"


def test_the_wait_is_bounded():
    """An unbounded wait would hang the reconciler loop for every degraded node."""
    func = _function("_heartbeat_returned")
    names = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}

    assert "REMEDIATION_HEARTBEAT_WAIT_S" in names, "the heartbeat wait is not bounded by the timeout constant"


@pytest.mark.parametrize(
    "constant",
    ["REMEDIATION_HEARTBEAT_WAIT_S", "REMEDIATION_HEARTBEAT_POLL_S"],
)
def test_the_timings_are_env_backed_not_hardcoded(constant):
    """Repo rule: TTLs and windows come from env-var-backed module constants.

    The right window depends on the agent's heartbeat interval on a given
    fleet, so it is not a value to bake in.
    """
    for node in _TREE.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == constant for t in node.targets):
            func_id = getattr(node.value.func, "id", None) if isinstance(node.value, ast.Call) else None
            assert func_id in ("env_int", "env_int_clamped"), f"{constant} is not env-backed"
            return
    raise AssertionError(f"{constant} is not defined at module level")


def _fstring_text(node: ast.AST) -> str:
    """Flatten an f-string to its literal parts, ignoring interpolations."""
    return " ".join(n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)).lower()


def test_the_success_message_reports_the_verified_outcome():
    """ "Successfully restarted" was true and misleading.

    It is the line an operator greps to ask whether self-healing worked, and it
    answered a narrower question in language claiming the broader one.

    Asserted on the SUCCESS branch specifically. An earlier version of this rule
    joined every message in the function and asked whether "heartbeat" appeared
    anywhere — which #14354's interim wording ("awaiting heartbeat", correct for
    the old semantics and wrong for these) would also have satisfied.
    """
    func = _function("_record_remediation_result")
    branch = next((n for n in ast.walk(func) if isinstance(n, ast.If)), None)
    assert branch is not None, "no success/failure branch — this rule is pinned to the wrong shape"

    text = " ".join(_fstring_text(n) for n in branch.body)

    assert "heartbeat" in text, "the success message does not report the heartbeat it verified"
    assert (
        "awaiting" not in text
    ), "the success message says the heartbeat is still awaited, but success now means it already returned"


def test_failure_distinguishes_the_restart_from_the_heartbeat():
    """The two failures need different responses from an operator.

    `restarted=False` is an unreachable or broken node. A clean restart with no
    heartbeat is an agent that runs and is rejected (#14350) — a credential
    problem. Reporting both as "failed to restart" sends the operator to the
    wrong layer, which is how #14350 stayed invisible for as long as it did.
    """
    func = _function("_record_remediation_result")
    args = {a.arg for a in func.args.args}
    assert "restarted" in args, "_record_remediation_result cannot tell the two failure stages apart"

    branch = next((n for n in ast.walk(func) if isinstance(n, ast.If)), None)
    text = " ".join(_fstring_text(n) for n in branch.orelse)

    assert "did not resume heartbeating" in text, "the heartbeat-stage failure is not reported distinctly"


def test_the_caller_passes_the_restart_stage_through():
    """A parameter with a default is only as good as the call site.

    `restarted: bool = True` defaults to the friendlier message, so a caller
    that forgets to pass it silently reports every failure as a heartbeat
    failure — including nodes that were never reachable.
    """
    func = _function("_remediate_node")

    calls = [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_record_remediation_result"
    ]
    assert calls, "_remediate_node no longer records a remediation result"

    for call in calls:
        passed = {kw.arg for kw in call.keywords} | {
            n.id for a in call.args for n in ast.walk(a) if isinstance(n, ast.Name)
        }
        assert "restarted" in passed, "the restart outcome is not passed through, so the stage is guessed"
