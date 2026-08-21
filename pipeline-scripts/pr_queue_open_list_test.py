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


def _write_gh_stub(directory: Path, *, list_rc: int = 0, comment_rc: int = 0) -> None:
    """Put a fake `gh` on PATH that mimics the two calls the gate makes."""
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
        "if [ %d -ne 0 ]; then echo 'stub: gh failed' >&2; exit %d; fi\n"
        'for a in "$@"; do [ "$a" = "length" ] && { echo %d; exit 0; }; done\n'
        "echo '[%s]'\n" % (comment_rc, list_rc, list_rc, len(_OPEN_PRS), payload),
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
    ("label", "kwargs"),
    [
        ("everything works", {}),
        ("posting the notice fails", {"comment_rc": 1}),
        ("listing the PRs fails", {"list_rc": 1}),
    ],
)
def test_the_gate_never_fails_the_check(
    tmp_path: Path, label: str, kwargs: dict[str, int]
) -> None:
    """Warn-only, enforced by running it — this is the #14718 regression.

    Before the fix the third case exited non-zero, turning a detector into a
    blocker on every PR opened above the threshold.
    """
    _write_gh_stub(tmp_path, **kwargs)
    script = tmp_path / "gate.sh"
    script.write_text(_gate_run_block(), encoding="utf-8")
    result = subprocess.run(
        # GitHub Actions runs a `run:` block as `bash -e {0}`. Invoking plain
        # `bash` here would let a failed command slide and under-reproduce the
        # very failure this test exists for.
        ["bash", "-e", str(script)],
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


def test_the_threshold_branch_is_actually_reached(tmp_path: Path) -> None:
    """Guard the guard: 30 stubbed PRs must trip the runaway branch.

    If the stub ever fell below the threshold the tests above would pass by
    running the quiet path and would prove nothing about the failure mode.
    """
    _write_gh_stub(tmp_path)
    script = tmp_path / "gate.sh"
    script.write_text(_gate_run_block(), encoding="utf-8")
    result = subprocess.run(
        # GitHub Actions runs a `run:` block as `bash -e {0}`. Invoking plain
        # `bash` here would let a failed command slide and under-reproduce the
        # very failure this test exists for.
        ["bash", "-e", str(script)],
        capture_output=True,
        text=True,
        env=_env_with_stub(tmp_path),
        cwd=_REPO_ROOT,
        check=False,
    )
    assert "Runaway threshold reached" in result.stdout, (
        "the stub no longer trips the threshold, so the warn-only tests are "
        f"exercising the quiet path and prove nothing.\nstdout:\n{result.stdout}"
    )
