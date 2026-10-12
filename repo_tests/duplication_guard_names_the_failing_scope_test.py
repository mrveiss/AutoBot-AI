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

#16319: the pins are absolute duplicated-line counts, and the gate steps and
this step read jscpd's report through one parser, ``scripts/duplication_gate.py``.
"""

from __future__ import annotations

import importlib.util
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


def _job() -> dict:
    document = yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))
    return document["jobs"][next(iter(document["jobs"]))]


def _step(step_id: str) -> dict:
    for step in _job()["steps"]:
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"no step with id {step_id!r} in duplication-guard.yml")


def _run_explain(main_outcome: str, slm_outcome: str, **extra_env: str) -> str:
    """Execute the step's real script with the two step outcomes injected.

    Run from the repository root, as in CI: the step calls
    ``scripts/duplication_gate.py`` by relative path.
    """
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - every CI image has bash
        pytest.skip("bash unavailable")
    result = subprocess.run(
        [bash, "-c", _explain_step()["run"]],
        capture_output=True,
        text=True,
        cwd=repo_root(),
        env={
            "PATH": "/usr/bin:/bin",
            "MAIN_OUTCOME": main_outcome,
            "SLM_OUTCOME": slm_outcome,
            "MAX_DUP_LINES": "11723",
            "SLM_MAX_DUP_LINES": "4729",
            **extra_env,
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


@pytest.mark.parametrize(
    ("main_outcome", "slm_outcome", "named", "unnamed"),
    [
        ("failure", "success", "(env MAX_DUP_LINES)", "(env SLM_MAX_DUP_LINES)"),
        ("success", "failure", "(env SLM_MAX_DUP_LINES)", "(env MAX_DUP_LINES)"),
    ],
)
def test_the_failing_scope_names_its_own_env_var(main_outcome, slm_outcome, named, unnamed) -> None:
    """#16163 AC1: the value says how far over; the env var name says which knob.

    Matched as the whole `(env NAME)` token, because `MAX_DUP_LINES` is a
    substring of `SLM_MAX_DUP_LINES` and a bare substring check would pass either way.
    """
    output = _run_explain(main_outcome=main_outcome, slm_outcome=slm_outcome)
    assert named in output, f"the failing scope did not name {named}"
    assert unnamed not in output, f"named {unnamed}, the passing scope's knob"


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
    assert "no captured log" in output or "could not read jscpd totals" in output
    assert "OVER BY" not in output, "reported an overage with no log to measure from"


#: One real jscpd Total row, captured verbatim from run 34414434867 -- the run
#: whose 4729/259798 figures #16163 is written about. ANSI codes and U+2502 box
#: characters intact, because those are exactly what the first parser could not
#: read: it required an ASCII pipe, and real output contains none.
_REAL_JSCPD_TOTAL_ROW = (
    "\x1b[90m\u2502\x1b[39m \x1b[1mTotal:\x1b[22m     \x1b[90m\u2502\x1b[39m 759            "
    "\x1b[90m\u2502\x1b[39m 259798      \x1b[90m\u2502\x1b[39m 1227700      "
    "\x1b[90m\u2502\x1b[39m 135           \x1b[90m\u2502\x1b[39m 4729 (1.82%)   \x1b[90m\u2502\x1b[39m"
)


def _gate_module():
    """The parser the workflow runs, loaded from its file rather than re-implemented."""
    spec = importlib.util.spec_from_file_location("duplication_gate", repo_root() / "scripts" / "duplication_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_parser_reads_a_real_jscpd_row_not_a_synthetic_one() -> None:
    """#16163: the first parser passed its own fixtures and failed every real log.

    It matched on ASCII `|`. jscpd draws with U+2502 wrapped in ANSI colour, so
    there is not one ASCII pipe in real output. The fixture is therefore a
    captured production row, and since #16319 it is read by the workflow's own
    parser, not by a copy of it written here.

    Asserts the FIGURES, not that parsing succeeded: an off-by-one in the field
    split once read 1,227,700 tokens as the line count.
    """
    totals = _gate_module().parse_totals(_REAL_JSCPD_TOTAL_ROW + "\n")

    assert (totals.duplicated_lines, totals.lines, totals.clones) == (4729, 259798, 135)


def test_explain_reports_the_overage_in_lines_against_the_pin(tmp_path) -> None:
    """#16319 AC4: the failing scope's overage, in duplicated lines, against its pin."""
    log = tmp_path / "slm-gate.log"
    log.write_text(_REAL_JSCPD_TOTAL_ROW + "\n", encoding="utf-8")

    output = _run_explain("success", "failure", SLM_LOG=str(log), SLM_MAX_DUP_LINES="4728")

    assert "OVER BY:   1 lines" in output
    assert "(env SLM_MAX_DUP_LINES)" in output


@pytest.mark.parametrize(
    ("step_id", "trees", "log", "pin"),
    [
        ("main_scope", "autobot-backend autobot-frontend/src", "/tmp/main-dup.log", "MAX_DUP_LINES"),
        (
            "slm_scope",
            "autobot_shared autobot-slm-backend autobot-slm-frontend/src",
            "/tmp/slm-gate.log",
            "SLM_MAX_DUP_LINES",
        ),
    ],
)
def test_each_gate_scans_its_declared_scope_and_applies_its_own_pin(step_id, trees, log, pin) -> None:
    """The boundary a reader meets in the env comments must be the one scanned (RATCHET_BASELINES rule 2).

    Also pins that the percentage gate is gone: jscpd's own ``--threshold`` must
    not come back beside the count.
    """
    run = _step(step_id)["run"]

    assert trees in run
    assert f'scripts/duplication_gate.py {log} "${{{pin}}}"' in run
    assert "--threshold" not in run


def test_the_pins_are_duplicated_line_counts_not_percentages() -> None:
    env = _job()["env"]

    assert env["MAX_DUP_LINES"].isdigit() and env["SLM_MAX_DUP_LINES"].isdigit()
    assert "THRESHOLD" not in env and "SLM_THRESHOLD" not in env
