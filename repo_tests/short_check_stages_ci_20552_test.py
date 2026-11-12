# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Expensive CI jobs wait for the short check, and required gates still report (#20552)."""

import copy
import re

import yaml
from repo_tests._gate_verdict_driver import run_verdict
from repo_tests._github_expressions import evaluate, strip_expression_braces
from repo_tests._paths import repo_root

_WORKFLOWS = repo_root() / ".github" / "workflows"
_FAST_LIST = repo_root() / "tools" / "git-hooks" / "fast_guard_tests.txt"
#: Called with the verdict of short-check's successors, or cheap by design.
_NOT_STAGED = {"changes", "short-check", "run-precommit"}
_STATUS_FUNCTIONS = ("always()", "cancelled()", "failure()")
_CHANGES_OUTPUT = re.compile(r"needs\.changes\.outputs\.([\w-]+)")


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


def _staged(jobs: dict, name: str) -> bool:
    """True when `name` needs the short check, or needs only jobs that are themselves staged."""
    needs = set(_needs(jobs[name])) - {"changes"}
    return "short-check" in needs or (bool(needs) and all(_staged(jobs, n) for n in needs))


def test_every_job_that_starts_from_detection_waits_for_the_short_check() -> None:
    jobs = _jobs()
    direct = {n: j for n, j in jobs.items() if "changes" in _needs(j) and n not in _NOT_STAGED}
    work = {n: j for n, j in direct.items() if not _steps_using(j, "gate-verdict") and n != "notify"}
    assert len(work) >= 14, sorted(work)
    # python-shard waits through provision-packages: a failed need skips it, so it is staged by closure.
    missing = sorted(n for n in work if not _staged(jobs, n))
    assert not missing, missing


def test_the_staging_closure_rejects_a_job_that_bypasses_the_short_check() -> None:
    """Control: python-shard needing detection alone, or an unstaged job, is not staged."""
    jobs = _jobs()
    assert _staged(jobs, "python-shard") and not _staged(jobs, "short-check")
    bypass = {**jobs, "python-shard": {"needs": ["changes"]}}
    assert not _staged(bypass, "python-shard")
    skipping_the_stage = {**jobs, "provision-packages": {"needs": ["changes"]}}
    assert not _staged(skipping_the_stage, "python-shard")


def _gate_inputs(job: dict) -> dict:
    return _steps_using(job, "gate-verdict")[0]["with"]


def _skips_when_short_check_fails(jobs: dict, name: str) -> bool:
    """A job whose need failed is skipped unless its own `if` names a status function."""
    job = jobs[name]
    condition = str(job.get("if", ""))
    if any(fn in condition for fn in _STATUS_FUNCTIONS):
        return False
    return "short-check" in _needs(job) or any(
        _skips_when_short_check_fails(jobs, n) for n in _needs(job) if n != "changes"
    )


def _needs_context(job: dict, short_check: str, work: str, affected: bool) -> dict:
    """The `needs` context a gate sees: detection succeeded, `affected` paths, and the given results."""
    inputs = _gate_inputs(job)
    refs = _CHANGES_OUTPUT.findall(inputs["applies"] + inputs["work-ok"])
    flag = "true" if affected else "false"
    needs = {"changes": {"result": "success", "outputs": dict.fromkeys(refs, flag)}}
    needs["short-check"] = {"result": short_check}
    for name in set(_needs(job)) - {"changes", "short-check"}:
        ok = {"ok": "true", "slm_ok": "true"} if work == "success" else {}
        needs[name] = {"result": work, "outputs": ok}
    return {"needs": needs, "github": {"event_name": "pull_request", "event": {"pull_request": {"draft": False}}}}


def _render(expression: str, context: dict) -> str:
    value = evaluate(strip_expression_braces(expression), context)
    return str(value).lower() if isinstance(value, bool) else str(value)


def _verdict(job: dict, short_check: str, work: str, affected: bool = True) -> tuple[int, str]:
    """Run the real verdict.sh on the inputs the gate's own expressions produce for this state."""
    inputs, context = _gate_inputs(job), _needs_context(job, short_check, work, affected)
    return run_verdict(
        GATE_CONTEXT=inputs["context"],
        GATE_CHANGES_RESULT=_render(inputs["changes-result"], context),
        GATE_APPLIES=_render(inputs["applies"], context),
        GATE_WORK_OK=_render(inputs["work-ok"], context),
        GATE_WORK_DETAIL=f"short-check={short_check}",
        GATE_EVENT=_render(inputs["event"], context),
        GATE_DRAFT=_render(inputs["draft"], context),
    )


def test_the_work_behind_each_gate_is_skipped_when_the_short_check_fails() -> None:
    jobs = _jobs()
    for name, job in _gates().items():
        work = [n for n in _needs(job) if n not in ("changes", "short-check")]
        assert work and all(_skips_when_short_check_fails(jobs, n) for n in work), name
    always = {**jobs, "run-code-quality": {**jobs["run-code-quality"], "if": "${{ always() }}"}}
    assert not _skips_when_short_check_fails(always, "run-code-quality"), "control: a status function runs it anyway"


def test_a_failed_short_check_fails_every_gate_that_applies_never_skips_or_passes() -> None:
    """The first acceptance criterion of #20552, judged on the real gates and the real verdict script.

    Each gate's `applies` / `work-ok` / `changes-result` expressions are read from ci.yml and
    evaluated for the state a failed short check produces (the work job SKIPPED, outputs empty);
    the resulting values drive `verdict.sh` itself. Controls on the same gates: work successful
    passes ("verified"), work failed still fails, and a gate the change does not touch passes
    "not affected" whatever the short check did -- so the failure is not "everything fails".

    Cannot be proven without a real run: that GitHub skips a job whose need failed (asserted from
    the graph above, not observed), that the expressions are evaluated by GitHub as by the
    in-repo evaluator, and that a failing gate step makes the required context red.
    """
    gates = _gates()
    assert len(gates) == 8, sorted(gates)
    for name, job in gates.items():
        assert job["if"] == "always()" and "short-check" in _needs(job), name
        rc, out = _verdict(job, short_check="failure", work="skipped")
        assert rc == 1 and "did not pass" in out, (name, out)
        rc, out = _verdict(job, short_check="success", work="success")
        assert rc == 0 and "verified" in out, (name, out)
        assert _verdict(job, short_check="success", work="failure")[0] == 1, name
        rc, out = _verdict(job, short_check="failure", work="skipped", affected=False)
        assert rc == 0 and "not affected" in out, (name, out)


def test_control_a_gate_that_ignores_its_work_would_pass_a_failed_short_check() -> None:
    """The harness can see the defect: a gate whose `work-ok` is constant true passes the failed state."""
    job = copy.deepcopy(_gates()["code-quality"])
    _gate_inputs(job)["work-ok"] = "${{ true }}"
    assert _verdict(job, short_check="failure", work="skipped")[0] == 0


def test_the_evaluator_reads_the_operators_the_gates_use() -> None:
    """Control for `_render`: `!=`, hyphenated job ids and boolean literals, each with its contrast."""
    context = {"needs": {"a-b": {"outputs": {"ok": "true"}}}}
    assert evaluate("needs.a-b.outputs.ok != 'true'", context) is False
    assert evaluate("needs.a-b.outputs.missing != 'true'", context) is True
    assert evaluate("needs.a-b.outputs.ok == 'true' && true", context) is True
    assert evaluate("needs.a-b.outputs.missing == 'true' || false", context) is False


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
