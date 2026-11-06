# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A skipped `smoke-test` must never satisfy the required context (#17126, #18208).

Owner rule, 2026-09-19: nothing lands on `main` without passing the Docker smoke test.
`smoke-test` is a required status check.

**GitHub counts a SKIPPED check run as satisfying a required status check.** Until #18208
two jobs published that one context -- the real build and a path-filtered shim in a second
workflow, each with its own `changes` job -- and a `changes` job that failed or was cancelled
skipped both of them, so the requirement was met with no smoke test run at all. #17126 made
the shim refuse and the build run when detection failed; #17391 recorded that two detectors
could still disagree, leaving the context with two conclusions or none.

#18208 removes the second publisher. The context is now published by ONE job: the
`smoke-test` gate in ci.yml, `if: always()`, which fails closed when detection did not
succeed and when the build did not pass. This file keeps #17126's property -- "a skip is
never the only thing reported" -- as assertions about that one job, and runs the verdict
script over the detector-failure case the original test existed for.

**Stated boundary.** This reads the workflow YAML and runs the verdict script. It cannot
prove GitHub's own required-context resolution, and it does not try: the platform
behaviour is the premise, not the assertion. The merge tooling's `MUST_RUN` list
(`ci-gate`) independently refuses an all-skipped `smoke-test`, and that belt stays.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_WORKFLOWS = Path(".github/workflows")
_CONTEXT = "smoke-test"
_VERDICT = Path(".github/actions/gate-verdict/verdict.sh")


def _workflow_files(root: Path) -> list[Path]:
    directory = root / _WORKFLOWS
    return sorted(p for p in directory.iterdir() if p.suffix == ".yml") if directory.is_dir() else []


#: 69 workflow files at #18208; repinned by scripts/repin_reach_floors.py, so a moved or emptied tree fails.
REACH = declare(
    "docker-smoke-context-publishers",
    discover=_workflow_files,
    floor=68,  # mid-window: population 71, window (65, 71)
    growth=6,  # ~9%: a new workflow file must not turn an unrelated PR red
    what="workflow files",
    roots=(".github/workflows",),
)


def _ci() -> dict:
    return yaml.safe_load((repo_root() / _WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))


def _gate() -> dict:
    jobs = _ci()["jobs"]
    assert _CONTEXT in jobs, f"ci.yml has no `{_CONTEXT}` job; jobs are {sorted(jobs)}"
    return jobs[_CONTEXT]


def _verdict(**env: str) -> subprocess.CompletedProcess:
    base = {
        "PATH": "/usr/bin:/bin",
        "GATE_CONTEXT": _CONTEXT,
        "GATE_CHANGES_RESULT": "success",
        "GATE_APPLIES": "true",
        "GATE_WORK_OK": "true",
        "GATE_EVENT": "pull_request",
    }
    return subprocess.run(
        ["bash", str(repo_root() / _VERDICT)], env={**base, **env}, capture_output=True, text=True, check=False
    )


def test_exactly_one_job_in_the_whole_tree_publishes_the_context() -> None:
    """The shim is gone; a second same-named job is the shape #17391 measured as unsafe."""
    publishers = []
    files = REACH.examined(repo_root())
    for path in files:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, spec in (doc.get("jobs") or {}).items():
            if (spec or {}).get("name", job_id) == _CONTEXT:
                publishers.append(f"{path.name}:{job_id}")
    REACH.completed(files)
    assert publishers == [f"ci.yml:{_CONTEXT}"], publishers


def test_the_gate_cannot_be_skipped_and_depends_on_the_detector_and_the_build() -> None:
    """#17126 AC1: without `always()` the job is skipped when `changes` fails, and a skip satisfies."""
    gate = _gate()
    assert str(gate.get("if", "")).strip() == "always()"
    needs = gate.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert {"changes", "run-docker-smoke"} <= set(needs)


def test_the_gate_hands_the_detector_result_to_the_verdict() -> None:
    step = next(s for s in _gate()["steps"] if s.get("uses") == "./.github/actions/gate-verdict")
    assert "needs.changes.result" in step["with"]["changes-result"]
    assert "needs.run-docker-smoke.outputs.ok" in step["with"]["work-ok"]


def test_a_failed_detector_refuses_even_when_no_docker_path_could_have_changed() -> None:
    """The case the shim existed to refuse: it cannot know nothing changed, so it must not say so."""
    for result in ("failure", "cancelled", "skipped"):
        proc = _verdict(GATE_CHANGES_RESULT=result, GATE_APPLIES="false", GATE_WORK_OK="false")
        assert proc.returncode == 1, (result, proc.stdout)
        assert "path detection" in proc.stdout


def test_no_docker_path_changed_reports_not_affected_without_a_build() -> None:
    proc = _verdict(GATE_APPLIES="false", GATE_WORK_OK="false")
    assert proc.returncode == 0 and "not affected" in proc.stdout


def test_a_docker_path_change_needs_the_build_to_have_passed() -> None:
    assert _verdict(GATE_WORK_OK="true").returncode == 0
    for detail in ("run-docker-smoke=skipped", "run-docker-smoke=failure", "run-docker-smoke=cancelled"):
        proc = _verdict(GATE_WORK_OK="false", GATE_WORK_DETAIL=detail)
        assert proc.returncode == 1, (detail, proc.stdout)


def test_the_build_still_runs_off_pull_requests() -> None:
    """The old real job ran on merge_group, schedule, and a push to main regardless of the filter."""
    expr = " ".join(str(_ci()["jobs"]["changes"]["outputs"]["run_docker_smoke"]).split())
    assert "github.event_name == 'merge_group'" in expr
    assert "github.event_name == 'push' && github.ref_name == 'main'" in expr
    assert "steps.dk.outputs.docker == 'true'" in expr
    schedule = yaml.safe_load((repo_root() / _WORKFLOWS / "scheduled-docker-smoke.yml").read_text(encoding="utf-8"))
    assert schedule["jobs"]["docker-smoke"]["uses"].endswith("/_gate-docker-smoke.yml")
    assert "if" not in schedule["jobs"]["docker-smoke"], "a scheduled run has no diff: it must build unconditionally"
