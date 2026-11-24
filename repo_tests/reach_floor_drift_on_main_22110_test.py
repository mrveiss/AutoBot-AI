# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A floor that drifts into its bottom band is caught on main, not on an unrelated PR (#22110).

Two halves, one mechanism (the reach registry's own ``staleness`` rule, never a second one):

* B -- main's own CI run enforces it. ``ci.yml`` sets ``AUTOBOT_REACH_AUDIT=1`` on a push to main
  and on a merge group, so the merge that crossed the line is the one that goes red.
* A -- ``repin-reach-floors.yml`` runs ``scripts/repin_reach_floors.py`` on main and opens, or
  updates, ONE pull request.

The detector is proved by contrast: a floor in the band is refused, one just above it is not.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import REACH_AUDIT_ENV, Reach, ReachFloorError

from autobot_shared.isolated_git import make_repo

_ROOT = Path("/nonexistent-root-never-read")
_WORKFLOWS = repo_root() / ".github" / "workflows"
# growth=200 -> the band is the bottom 20 of the window (ceil(200 * 0.10)).
_POPULATION, _GROWTH = 1000, 200
_BAND_EDGE = _POPULATION - _GROWTH + 20  # the lowest floor OUTSIDE the band


def _reach(floor: int) -> Reach:
    return Reach(
        name=f"drift-{floor}",
        discover=lambda _root: list(range(_POPULATION)),
        pinned_floor=floor,
        what="synthetic items",
        growth=_GROWTH,
    )


def test_a_floor_in_the_bottom_band_is_flagged_and_one_just_above_is_not() -> None:
    assert "bottom 20 of its window" in (_reach(_BAND_EDGE - 1).staleness(_ROOT) or "")
    assert _reach(_BAND_EDGE).staleness(_ROOT) is None


def test_on_main_the_flagged_floor_fails_and_the_one_above_it_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REACH_AUDIT_ENV, "1")
    with pytest.raises(ReachFloorError):
        _reach(_BAND_EDGE - 1).verify_floor(_ROOT)
    _reach(_BAND_EDGE).verify_floor(_ROOT)


def test_off_main_the_same_floor_only_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unrelated PR stays green: no audit, so the flagged floor warns instead of failing."""
    monkeypatch.delenv(REACH_AUDIT_ENV, raising=False)
    with pytest.warns(UserWarning):
        _reach(_BAND_EDGE - 1).verify_floor(_ROOT)


def _audit_step() -> dict:
    steps = yaml.safe_load((_WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["jobs"]["python-shard"]["steps"]
    found = [s for s in steps if f"{REACH_AUDIT_ENV}=1" in str(s.get("run", ""))]
    assert len(found) == 1, "exactly one step sets the reach audit"
    return found[0]


def _evaluate(expr: str, **context: str) -> bool:
    """Evaluate a workflow ``if:`` expression over one context (no substring matching)."""
    for name in ("head_ref", "event_name", "ref"):
        expr = expr.replace(f"github.{name}", name)
    expr = re.sub(r"steps\.repin\.outputs\.(\w+)", r"out_\1", expr)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    values = {"head_ref": "", "event_name": "", "ref": "", "out_changed": "", "out_stale_left": ""}
    functions = {"startsWith": lambda text, prefix: text.startswith(prefix), "always": lambda: True}
    return bool(
        eval(expr, {"__builtins__": {}}, {**values, **functions, **context})
    )  # noqa: S307 - this repo's own workflow text


def _audit_applies(**context: str) -> bool:
    return _evaluate(str(_audit_step()["if"]), **context)


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({"event_name": "pull_request", "head_ref": "issue-1-feature", "ref": "refs/pull/1/merge"}, False),
        ({"event_name": "push", "ref": "refs/heads/main"}, True),
        ({"event_name": "merge_group", "ref": "refs/heads/gh-readonly-queue/main/pr-1"}, True),
        ({"event_name": "pull_request", "head_ref": "train-t1", "ref": "refs/pull/2/merge"}, True),
        ({"event_name": "push", "ref": "refs/heads/issue-1-feature"}, False),
    ],
)
def test_ci_enforces_the_audit_only_where_main_is_judged(context: dict, expected: bool) -> None:
    assert _audit_applies(**context) is expected


def _repin() -> dict:
    return yaml.safe_load((_WORKFLOWS / "repin-reach-floors.yml").read_text(encoding="utf-8"))


def _step(name_part: str) -> dict:
    found = [s for s in _repin()["jobs"]["repin"]["steps"] if name_part in str(s.get("name", ""))]
    assert len(found) == 1, name_part
    return found[0]


def test_the_repin_workflow_runs_on_main_and_on_a_schedule() -> None:
    triggers = _repin()[True]  # YAML parses the bare key `on` as the boolean True
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["schedule"] and "workflow_dispatch" in triggers


def test_the_repin_workflow_pushes_only_the_bot_branch_and_looks_up_open_prs() -> None:
    text = (_WORKFLOWS / "repin-reach-floors.yml").read_text(encoding="utf-8")
    pushes = [line.strip() for line in text.splitlines() if line.strip().startswith("git push")]
    assert pushes, "the workflow no longer pushes the bot branch"
    for line in pushes:
        assert line.split()[-1] == '"$BRANCH"', f"a push whose refspec is not the bot branch: {line}"
        assert "main" not in line.split(), line
    assert _repin()["env"]["BRANCH"] not in ("main", "release")
    for step in _repin()["jobs"]["repin"]["steps"]:
        assert "BRANCH" not in step.get("env", {}), "BRANCH is declared once, at the workflow level"
    assert 'gh pr list --head "$BRANCH" --state open' in text, "gh pr view matches closed PRs too (#20057)"
    assert "gh pr view" not in _step("Open or update")["run"]
    assert "gh pr close" not in text, "no PR is closed without a merge"
    assert "gh pr comment" in _step("no longer needed")["run"], "an obsolete re-pin PR gets a comment, never a close"
    assert "secrets.GITHUB_TOKEN" not in text


def test_the_bot_pr_carries_the_milestone_label_and_a_proof_table() -> None:
    run = _step("Open or update")["run"]
    assert '--milestone "$PR_MILESTONE" --label "$PR_PHASE_LABEL"' in run
    env = _repin()["env"]
    assert env["PR_MILESTONE"].startswith("M5") and env["PR_PHASE_LABEL"] == "phase:M5.7"
    assert "| AC | Precondition | Postcondition | Establishing lines | Argument | Reviewer |" in run
    assert "| pending |" in run


# The default `run:` shell on the runner when no `shell:` key is set: errexit is on there, so it is on here.
_RUNNER_SHELL = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"]


def _run_step(step: dict, tmp_path: Path, exit_code: int) -> subprocess.CompletedProcess:
    """Run a workflow step's shell with a stub ``python`` that exits *exit_code* after a SKIP line."""
    make_repo(tmp_path, default_branch="main")
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "python").write_text(f'#!/bin/sh\necho "SKIP  floor-x: reason"\nexit {exit_code}\n', encoding="utf-8")
    (stub / "python").chmod(0o755)
    out = tmp_path / "out"
    out.touch()
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "GITHUB_OUTPUT": str(out)}
    return subprocess.run([*_RUNNER_SHELL, step["run"]], cwd=tmp_path, env=env, capture_output=True, text=True)


def test_a_floor_left_stale_fails_the_job_and_names_it(tmp_path: Path) -> None:
    first = _run_step(_step("Re-pin every stale floor"), tmp_path, exit_code=1)
    assert first.returncode == 0, "the PR for the floors that WERE re-pinned must still open"
    assert "stale_left=true" in (tmp_path / "out").read_text(encoding="utf-8")
    last = _step("Fail while a floor stays stale")
    assert "steps.repin.outputs.stale_left == 'true'" in last["if"]
    assert "always()" in last["if"], "a failed earlier step must not skip the signal"
    failed = subprocess.run([*_RUNNER_SHELL, last["run"]], cwd=tmp_path, capture_output=True, text=True)
    assert failed.returncode == 1
    assert "::error::reach floor needs a hand re-pin: floor-x: reason" in failed.stdout


def test_a_clean_run_sets_no_stale_flag_and_an_unmeasured_guard_fails(tmp_path: Path) -> None:
    clean = _run_step(_step("Re-pin every stale floor"), tmp_path, exit_code=0)
    assert clean.returncode == 0
    assert "stale_left" not in (tmp_path / "out").read_text(encoding="utf-8")
    broken = _run_step(_step("Re-pin every stale floor"), tmp_path, exit_code=2)
    assert broken.returncode == 2, "an import failure is never read as clean"


@pytest.mark.parametrize(
    ("changed", "stale_left", "comments"),
    [("true", "", False), ("true", "true", False), ("false", "", True), ("false", "true", False)],
)
def test_the_no_longer_needed_comment_fires_only_when_nothing_is_stale(
    changed: str, stale_left: str, comments: bool
) -> None:
    """A floor still stale means the open re-pin PR may still be needed: no comment then."""
    expr = str(_step("no longer needed")["if"])
    assert _evaluate(expr, out_changed=changed, out_stale_left=stale_left) is comments


def _pin_cell(tmp_path: Path, log: str) -> tuple[subprocess.CompletedProcess, str]:
    (tmp_path / "repin.log").write_text(log, encoding="utf-8")
    out = tmp_path / "out"
    out.write_text("", encoding="utf-8")
    env = {**os.environ, "GITHUB_OUTPUT": str(out)}
    step = _step("Collect the re-pinned")
    done = subprocess.run([*_RUNNER_SHELL, step["run"]], cwd=tmp_path, env=env, capture_output=True, text=True)
    return done, out.read_text(encoding="utf-8").strip()


def test_the_proof_cell_is_built_from_the_pin_lines(tmp_path: Path) -> None:
    log = "PIN   a: floor -> 459 (population 479) in repo_tests/a_test.py:37\nSKIP  b: reason\n"
    done, cell = _pin_cell(tmp_path, log)
    assert done.returncode == 0 and cell == "lines=repo_tests/a_test.py:37" and "|" not in cell


def test_a_value_repeated_in_one_file_still_gives_two_distinct_lines(tmp_path: Path) -> None:
    log = (
        "PIN   a: floor -> 204 (population 219) in repo_tests/v_test.py:161\n"
        "PIN   b: floor -> 204 (population 219) in repo_tests/v_test.py:168\n"
    )
    _, cell = _pin_cell(tmp_path, log)
    assert cell == "lines=repo_tests/v_test.py:161; repo_tests/v_test.py:168"


def test_no_pin_line_falls_back_to_a_true_cell_and_the_step_does_not_fail(tmp_path: Path) -> None:
    done, cell = _pin_cell(tmp_path, "SKIP  b: reason\n")
    assert done.returncode == 0
    assert cell == "lines=see repin.log (no PIN line)"
    assert "|" not in cell
