# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The duplication guard must name WHICH scope failed (#16163).

The step this covers used to say, in its own output, that it could not tell:

    A duplication scope exceeded its baseline. There are TWO,
    and this step cannot tell which failed -- read the step above.

A correct verdict the reader cannot attribute costs the same investigation as a
wrong one. These tests run the step's real shell with each outcome in turn,
rather than reasoning about which branch would be taken -- the reasoning is what
produced the original defect.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

WORKFLOW = Path(".github/workflows/duplication-guard.yml")

MAIN_SCOPE = "autobot-backend + autobot-frontend/src"
SLM_SCOPE = "autobot_shared + autobot-slm-backend + autobot-slm-frontend/src"


def _explain_step() -> dict:
    """The `Explain failure` step, located by name rather than by index."""
    document = yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))
    job = document["jobs"][next(iter(document["jobs"]))]
    for step in job["steps"]:
        if step.get("name") == "Explain failure":
            return step
    raise AssertionError("no step named 'Explain failure' in duplication-guard.yml")


def _run_explain(main_outcome: str, slm_outcome: str) -> str:
    """Execute the step's real script with the two step outcomes injected."""
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - every CI image has bash
        pytest.skip("bash unavailable")
    result = subprocess.run(
        [bash, "-c", _explain_step()["run"]],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "MAIN_OUTCOME": main_outcome,
            "SLM_OUTCOME": slm_outcome,
            "THRESHOLD": "1.05",
            "SLM_THRESHOLD": "1.82",
        },
    )
    return result.stdout + result.stderr


def test_both_gating_steps_carry_an_id() -> None:
    """Attribution depends on the ids; without them the step cannot tell."""
    document = yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))
    job = document["jobs"][next(iter(document["jobs"]))]
    ids = {step.get("id") for step in job["steps"]}
    assert {"main_scope", "slm_scope"} <= ids, f"gating step ids missing, found {sorted(i for i in ids if i)}"


def test_the_step_no_longer_says_it_cannot_tell_which_failed() -> None:
    """The admission of blindness must go once the blindness is fixed.

    Leaving it in is worse than harmless: a reader who sees it stops looking for
    the attribution that is now right there.
    """
    body = _explain_step()["run"]
    assert "cannot tell which failed" not in body
    assert "read the step above" not in body


def test_only_the_failing_scope_is_named_when_main_fails() -> None:
    """#16163 AC: a scope passing while the other fails names ONLY the failing one."""
    output = _run_explain(main_outcome="failure", slm_outcome="success")
    assert MAIN_SCOPE in output
    assert SLM_SCOPE not in output, "named the passing scope -- the reader cannot tell which to fix"


def test_only_the_failing_scope_is_named_when_slm_fails() -> None:
    """The same, in the other direction.

    Run in turn rather than asserted once, because a script that names whichever
    scope it checks first passes a single-direction test.
    """
    output = _run_explain(main_outcome="success", slm_outcome="failure")
    assert SLM_SCOPE in output
    assert MAIN_SCOPE not in output, "named the passing scope -- the reader cannot tell which to fix"


def test_both_are_named_when_both_fail() -> None:
    """Neither may be dropped when both exceeded."""
    output = _run_explain(main_outcome="failure", slm_outcome="failure")
    assert MAIN_SCOPE in output
    assert SLM_SCOPE in output


def test_a_failure_outside_both_gates_says_so_rather_than_blaming_duplication() -> None:
    """`if: failure()` fires for ANY earlier failure -- checkout, node, npx.

    Reporting a duplication error then would be a guess, and it is the guess a
    reader would act on. The honest output names the outcomes and says the cause
    is elsewhere.
    """
    output = _run_explain(main_outcome="success", slm_outcome="success")
    assert "outside both duplication gates" in output
    assert MAIN_SCOPE not in output
    assert SLM_SCOPE not in output


def test_a_missing_log_reports_no_figure_rather_than_a_guessed_one() -> None:
    """With no captured log there is no measurement, and none is invented.

    The tests above run without the jscpd logs present, so this is the path they
    all take -- asserted explicitly so a future change that starts printing a
    default or a zero is caught here rather than believed in a PR comment.
    """
    output = _run_explain(main_outcome="failure", slm_outcome="success")
    assert "no captured log" in output or "could not parse" in output
    assert "OVER BY" not in output, "reported an overage with no log to measure from"
