# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The runaway PR-queue detector must warn, and must never fail a check.

#14718: `check-pr-limit` in `.github/workflows/pr-queue-gate.yml` calls itself
a warn-only runaway detector — its own notice text ends "It never blocks a
merge." It built the open-PR list by passing `--argjson` to `gh pr list`, which
has no such flag, so `gh` errored and `set -e` killed the step. The check went
red every time the threshold was crossed, and the notice was never posted once:
the step died before reaching `gh pr comment`.

Two properties are covered here, both by execution rather than by reading the
YAML:

* the list builder produces the right list, and rejects input it cannot trust;
* the workflow's own `run` block exits 0 even when `gh` fails underneath it,
  because a detector whose failure can redden a required check is worse than
  no detector.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "pipeline-scripts" / "pr-queue-open-list.sh"
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "pr-queue-gate.yml"

# Enough open PRs to put the stubbed repo past the workflow's threshold, so the
# tests exercise the runaway branch rather than the quiet one.
_OPEN_PRS = [{"number": 100 + i, "title": f"pr number {100 + i}"} for i in range(30)]


def _write_gh_stub(
    directory: Path, *, count_rc: int = 0, list_rc: int = 0, comment_rc: int = 0
) -> None:
    """Put a fake `gh` on PATH that mimics the three calls the gate makes.

    The gate calls `gh pr list` TWICE and they must be controllable
    separately. The first asks jq for `length` to get the count; the second
    (inside `pr-queue-open-list.sh`) fetches the list itself and only happens
    on the runaway branch. A single failure switch for both made the count
    fail first, which sent the gate down the quiet path — so the case meant to
    exercise the list fallback never reached it, and passed for the wrong
    reason.
    """
    payload = "".join(
        f'{{"number": {p["number"]}, "title": "{p["title"]}"}},' for p in _OPEN_PRS
    ).rstrip(",")
    stub = directory / "gh"
    stub.write_text(
        "#!/bin/bash\n"
        # Real `gh pr list` has no --argjson; it takes the next token as the
        # value of --jq and then rejects the leftovers. Emulating that is what
        # makes this stub able to reproduce #14718 at all.
        'for a in "$@"; do [ "$a" = "--argjson" ] && {\n'
        '  echo "unknown arguments; please quote all values that have spaces" >&2\n'
        "  exit 1; }; done\n"
        'for a in "$@"; do [ "$a" = "comment" ] && exit %d; done\n'
        # `--jq length` identifies the count call and nothing else.
        'for a in "$@"; do [ "$a" = "length" ] && {\n'
        "  if [ %d -ne 0 ]; then echo 'stub: gh count failed' >&2; exit %d; fi\n"
        "  echo %d; exit 0; }; done\n"
        "if [ %d -ne 0 ]; then echo 'stub: gh list failed' >&2; exit %d; fi\n"
        "echo '[%s]'\n"
        % (comment_rc, count_rc, count_rc, len(_OPEN_PRS), list_rc, list_rc, payload),
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _env_with_stub(directory: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{directory}{os.pathsep}{env['PATH']}"
    env["REPO"] = "owner/repo"
    env["PR_NUMBER"] = "105"
    env["GH_TOKEN"] = "stub-token-not-a-real-credential"
    return env


def test_the_script_is_where_the_workflow_calls_it() -> None:
    """A missing script would make every assertion below vacuous."""
    assert _SCRIPT.is_file(), f"{_SCRIPT} is missing"
    assert _WORKFLOW.is_file(), f"{_WORKFLOW} is missing"


def test_open_list_excludes_the_current_pr(tmp_path: Path) -> None:
    """The whole point of the `$skip` binding that #14718 broke."""
    _write_gh_stub(tmp_path)
    result = subprocess.run(
        ["bash", str(_SCRIPT), "owner/repo", "105"],
        capture_output=True,
        text=True,
        env=_env_with_stub(tmp_path),
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "- #105 " not in result.stdout, "the current PR must not list itself"
    assert "- #104 pr number 104" in result.stdout
    assert result.stdout.count("- #") == len(_OPEN_PRS) - 1


def test_a_non_numeric_pr_number_is_rejected(tmp_path: Path) -> None:
    """`--argjson` needs a number; a string would silently match nothing."""
    _write_gh_stub(tmp_path)
    result = subprocess.run(
        ["bash", str(_SCRIPT), "owner/repo", "not-a-number"],
        capture_output=True,
        text=True,
        env=_env_with_stub(tmp_path),
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode != 0
    assert "must be numeric" in result.stderr


def test_the_script_reports_a_gh_failure_rather_than_hiding_it(tmp_path: Path) -> None:
    """The script is honest; making it non-fatal is the caller's job."""
    _write_gh_stub(tmp_path, list_rc=1)
    result = subprocess.run(
        ["bash", str(_SCRIPT), "owner/repo", "105"],
        capture_output=True,
        text=True,
        env=_env_with_stub(tmp_path),
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode != 0, "a gh failure must not be swallowed here"


def _gate_run_block() -> str:
    """The `run:` script the workflow actually executes."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-pr-limit"]["steps"]
    blocks = [step["run"] for step in steps if "run" in step]
    assert len(blocks) == 1, f"expected one run block, found {len(blocks)}"
    return blocks[0]


@pytest.mark.parametrize(
    ("label", "kwargs", "reaches_runaway"),
    [
        ("everything works", {}, True),
        ("posting the notice fails", {"comment_rc": 1}, True),
        ("listing the PRs fails", {"list_rc": 1}, True),
        ("counting the PRs fails", {"count_rc": 1}, False),
    ],
)
def test_the_gate_never_fails_the_check(
    tmp_path: Path, label: str, kwargs: dict[str, int], reaches_runaway: bool
) -> None:
    """Warn-only, enforced by running it — this is the #14718 regression.

    `reaches_runaway` is asserted, not assumed. Without it a case can fail its
    way onto the quiet path and pass for the wrong reason: when a single switch
    failed both `gh pr list` calls, the count died first, the gate skipped the
    runaway branch entirely, and the case nominally covering the open-list
    fallback exercised none of it. Deleting that fallback left the suite green.
    """
    _write_gh_stub(tmp_path, **kwargs)
    script = tmp_path / "gate.sh"
    script.write_text(_gate_run_block(), encoding="utf-8")
    result = subprocess.run(
        # Actions runs a `run:` block as `bash --noprofile --norc -eo pipefail`.
        # Plain `bash` would let a failed command slide and under-reproduce the
        # very failure this test exists for.
        ["bash", "-eo", "pipefail", str(script)],
        capture_output=True,
        text=True,
        env=_env_with_stub(tmp_path),
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"the runaway gate exited {result.returncode} when {label}. It is "
        f"documented warn-only and must never fail a check.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    reached = "Runaway threshold reached" in result.stdout
    assert reached is reaches_runaway, (
        f"when {label} the gate {'reached' if reached else 'did not reach'} the "
        f"runaway branch, expected the opposite. A case that silently takes the "
        f"quiet path proves nothing about the branch it is meant to cover.\n"
        f"stdout:\n{result.stdout}"
    )


def test_the_stub_stays_above_the_workflow_threshold() -> None:
    """Tie the stub's size to the gate's own threshold, not to a guess.

    The parametrised cases above already assert which branch each one took, so
    a stub that silently stopped tripping the runaway branch would be caught —
    but caught as three confusing failures that all look like the gate broke.

    The real hazard is drift in one direction: raise ``RUNAWAY_THRESHOLD`` in
    the workflow and the stub's PR count quietly stops exceeding it. Reading
    the threshold out of the workflow and comparing it here turns that into one
    failure that names the actual cause.
    """
    match = re.search(r"RUNAWAY_THRESHOLD=(\d+)", _gate_run_block())
    assert match, (
        "could not find RUNAWAY_THRESHOLD in the gate's run block — if it was "
        "renamed, repoint this test rather than dropping the check"
    )
    threshold = int(match.group(1))

    assert len(_OPEN_PRS) > threshold, (
        f"the stub builds {len(_OPEN_PRS)} open PRs but the gate's threshold is "
        f"{threshold}. The runaway branch can no longer be reached, so every "
        f"case that expects it would fail for a reason that looks like the gate "
        f"is broken. Raise the stub above the threshold."
    )


def test_every_step_outside_the_run_block_tolerates_failure() -> None:
    """Steps around the `run:` block must not be able to redden the check.

    The tests above execute the `run:` block and prove it swallows its own
    failures. They cannot reach the other steps in the job, and a job fails if
    *any* step fails — so a checkout blip would reproduce the exact "warn-only
    job goes red" failure this gate was fixed for, from a step no execution
    test touches. Structure is the only place left to assert it.
    """
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["check-pr-limit"]

    unguarded = [
        step.get("name") or step.get("uses")
        for step in job["steps"]
        if "run" not in step and step.get("continue-on-error") is not True
    ]
    assert not unguarded, (
        f"these steps can fail the warn-only gate: {unguarded}. Give each "
        f"`continue-on-error: true`, or move its work into the run block where "
        f"the tests above can prove it degrades instead of failing."
    )


def test_the_job_declares_the_scopes_its_steps_need() -> None:
    """Naming any permission sets every unnamed scope to `none`."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["check-pr-limit"]
    permissions = job.get("permissions", {})

    if any("uses" in step and "checkout" in step["uses"] for step in job["steps"]):
        assert permissions.get("contents") == "read", (
            "the job checks out the repository but does not declare "
            "`contents: read`; declaring any permission drops every unlisted "
            "scope to `none`"
        )
    assert permissions.get("pull-requests") == "write", "the gate posts a comment"
