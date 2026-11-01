# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Expensive CI jobs wait for the short check, and required gates still report (#20552)."""

import yaml
from repo_tests._paths import repo_root

_WORKFLOWS = repo_root() / ".github" / "workflows"
_FAST_LIST = repo_root() / "tools" / "git-hooks" / "fast_guard_tests.txt"
#: Called with the verdict of short-check's successors, or cheap by design.
_NOT_STAGED = {"changes", "short-check", "run-precommit", "run-auto-fix-types"}


def _doc(name: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _doc("ci.yml")["jobs"]


def _needs(job: dict) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else needs


def _steps_using(job: dict, action: str) -> list[dict]:
    return [s for s in job.get("steps", []) if action in s.get("uses", "")]


def _gates() -> dict:
    return {
        name: job
        for name, job in _jobs().items()
        if _steps_using(job, "gate-verdict") and name != "verify-precommit-config"
    }


def test_every_job_that_starts_from_detection_waits_for_the_short_check() -> None:
    direct = {n: j for n, j in _jobs().items() if "changes" in _needs(j) and n not in _NOT_STAGED}
    work = {n: j for n, j in direct.items() if not _steps_using(j, "gate-verdict") and n != "notify"}
    assert len(work) >= 14, sorted(work)
    # python-shard waits through provision-packages, which a failed need skips.
    missing = sorted(n for n, j in work.items() if not {"short-check", "provision-packages"} & set(_needs(j)))
    assert not missing, missing


def test_a_failed_short_check_reaches_each_gate_as_evidence_not_a_skip() -> None:
    gates = _gates()
    assert len(gates) == 8, sorted(gates)
    for name, job in gates.items():
        assert job["if"] == "always()", name
        assert "short-check" in _needs(job), name
        verdict = _steps_using(job, "gate-verdict")[0]["with"]
        assert "needs.short-check.result" in verdict["work-detail"], name


def test_a_cancelled_short_check_ends_each_gate_cancelled() -> None:
    for name, job in _gates().items():
        results = _steps_using(job, "cancel-run-on-cancelled-upstream")[0]["with"]["results"]
        assert "needs.short-check.result" in results, name


def test_the_short_check_itself_always_starts() -> None:
    job = _jobs()["short-check"]
    assert "if" not in job and _needs(job) == ["changes"]


def test_the_listed_guards_exist() -> None:
    listed = [line.split("#")[0].strip() for line in _FAST_LIST.read_text(encoding="utf-8").splitlines()]
    assert all((repo_root() / path).is_file() for path in listed if path)


def test_auto_fix_runs_only_after_verify_failed() -> None:
    assert list(_doc("auto-fix-generated-types.yml")[True]) == ["workflow_call"]
    condition = _jobs()["run-auto-fix-types"]["if"]
    assert "needs.run-generated-types.result == 'failure'" in condition


def test_triage_structure_ignores_labels_that_cannot_change_its_verdict() -> None:
    condition = _doc("issue-triage.yml")["jobs"]["structure"]["if"]
    assert "startsWith(github.event.label.name, 'phase:')" in condition
    assert "github.event.label.name == 'needs-structure'" in condition
