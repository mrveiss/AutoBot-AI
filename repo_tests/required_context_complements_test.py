# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for the required status contexts (#14353, #15606, #17391, #18208).

A required context is matched by check-run NAME. A job whose `if:` is false is
SKIPPED, and a skipped required job is the defect this file keeps out: it reads as
"never ran" and as "nothing to verify" at once. Until #18208 each context was
published by two same-named jobs in two workflows -- a real job and a "shim" -- and
a guard had to prove that exactly one of them could conclude. It covered one of the
five pairs (#17391) and could not cover the ordering of their check runs (#14922).

#18208 removed the pairs. Each gated required context is now published by ONE
top-level `if: always()` job in ci.yml (a "gate"), which reads the single `changes`
job and the work behind it through `.github/actions/gate-verdict`. The invariant this
file enforces (AC 4 of #18208): no required context's job can be skipped without its
always-reporting complement, because the only job that publishes the name IS the
always-reporting one, and every job that CAN be skipped has a different name.

G1  every required context is published by exactly one job in the whole tree
G2  each gated context's job is a top-level job of ci.yml, `if: always()`, and needs
    `changes` and the work it stands for
G3  the gate reads `needs.changes.result` (fail closed) and the work's result
G4  no work job or reusable-body job takes the name of a required context
G5  ci.yml's pull_request trigger carries no paths/branches filter and has the four
    types; the contexts that carry no draft clause still carry none
G6  the required list is non-vacuous: the scan resolves every one of the eleven
G7  control fixtures: a gate missing `if: always()`, a gate gated on a filter output
    and a duplicated context name must each FAIL the checker
"""

import copy
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

REPO_ROOT = repo_root()
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOW_DIR / "ci.yml"

# The eleven contexts branch protection requires on main. Branch protection lives in
# the GitHub API and cannot be read offline, so the list is declared here rather than
# derived. This hardcoded copy is a SECOND copy of the protection list and is kept
# only until the owner completes D7 of #18208 (move the required checks into the
# ruleset so the guard can compare against `GET /rules/branches/main`); at that point
# this constant is replaced by a read of the live rule. Until then, a change to the
# protected set must change this list in the same PR.
REQUIRED_CONTEXTS = frozenset(
    {
        "smoke-test",
        "code-quality",
        "startup-import-smoke",
        "Unit & Integration Tests",
        "No open blocks-merge issues reference this PR",
        "No commit trailers",
        "verify-generated-types",
        "migration-matrix",
        "verify-precommit-config",
        "api-wiring",
        "python-suite",
    }
)

# context -> (the gate's job id in ci.yml, the work jobs it must `need`, draft-gated).
# Rows are the whole of the gated set; the two governance checks are separate workflows.
GATES = {
    "python-suite": ("python-suite", ("python-shard",), True),
    "code-quality": ("code-quality", ("run-code-quality",), True),
    "startup-import-smoke": ("startup-import-smoke", ("run-startup-import-smoke",), True),
    "Unit & Integration Tests": ("unit-tests", ("run-frontend-test",), True),
    "smoke-test": ("smoke-test", ("run-docker-smoke",), True),
    "api-wiring": ("api-wiring", ("run-api-wiring",), True),
    "migration-matrix": ("migration-matrix", ("run-migration-gate",), True),
    "verify-generated-types": ("verify-generated-types", ("run-generated-types",), True),
    # #17957: the one context that runs on drafts (SPDX and symlink checks cover every PR).
    "verify-precommit-config": ("verify-precommit-config", ("run-precommit",), False),
}

# Separate workflows, kept apart on purpose (D1 of #18208).
GOVERNANCE = {
    "No commit trailers": "no-commit-trailers.yml",
    "No open blocks-merge issues reference this PR": "pr-blocking-findings.yml",
}

GATE_ACTION = "./.github/actions/gate-verdict"
SHIMS = (
    "python-required-context.yml",
    "backend-required-context.yml",
    "code-quality-required-context.yml",
    "frontend-required-context.yml",
    "docker-smoke-required-context.yml",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _on(doc: dict) -> dict:
    """The `on:` block. YAML 1.1 turns the bare key into True, so `doc["on"]` misses it."""
    return doc.get(True) or doc.get("on") or {}


def _all_workflows() -> dict:
    return {p.name: _load(p) for p in sorted(WORKFLOW_DIR.glob("*.yml"))}


def _job_name(job_id: str, spec: dict) -> str:
    return (spec or {}).get("name", job_id)


def _publishers(workflows: dict) -> dict:
    """context -> [(workflow file, job id)] for every job whose name is a required context."""
    found: dict = {}
    for fname, doc in workflows.items():
        for job_id, spec in (doc.get("jobs") or {}).items():
            name = _job_name(job_id, spec)
            if name in REQUIRED_CONTEXTS:
                found.setdefault(name, []).append((fname, job_id))
    return found


def _needs(spec: dict) -> set:
    needs = spec.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


def _gate_violations(workflows: dict) -> list:
    """Every way the tree breaks G1-G4, as readable strings. Empty means clean."""
    problems: list = []
    published = _publishers(workflows)

    # G1: exactly one publisher per required context, across ALL workflows.
    for context in sorted(REQUIRED_CONTEXTS):
        where = published.get(context, [])
        if len(where) != 1:
            problems.append(f"G1 {context!r} is published by {len(where)} jobs {where}, expected exactly 1")

    ci_jobs = (workflows.get("ci.yml") or {}).get("jobs") or {}
    for context, (job_id, work, draft_gated) in GATES.items():
        spec = ci_jobs.get(job_id)
        if spec is None:
            problems.append(f"G2 {context!r}: no top-level job {job_id!r} in ci.yml")
            continue
        if _job_name(job_id, spec) != context:
            problems.append(f"G2 {context!r}: job {job_id!r} is named {_job_name(job_id, spec)!r}")
        if str(spec.get("if", "")).strip() != "always()":
            problems.append(
                f"G2 {context!r}: `if:` is {spec.get('if')!r}, must be exactly `always()` -- "
                "a gate that can be skipped re-publishes `skipped` on the context"
            )
        missing = ({"changes"} | set(work)) - _needs(spec)
        if missing:
            problems.append(f"G2 {context!r}: `needs` lacks {sorted(missing)}")
        problems.extend(_verdict_step_violations(context, spec, work, draft_gated))

    # G4: nothing that can be skipped takes a required name.
    for fname, doc in workflows.items():
        callee = fname.startswith("_gate-")
        for job_id, spec in (doc.get("jobs") or {}).items():
            name = _job_name(job_id, spec)
            is_work = callee or (fname == "ci.yml" and job_id.startswith("run-"))
            if is_work and any(ctx in {name, job_id} for ctx in REQUIRED_CONTEXTS):
                problems.append(
                    f"G4 {fname}:{job_id} is named {name!r}, a required context; a job in a called "
                    "workflow reports as '<caller> / <job>' and a work job may be skipped"
                )
    return problems


def _verdict_step_violations(context: str, spec: dict, work: tuple, draft_gated: bool) -> list:
    problems: list = []
    steps = [s for s in spec.get("steps") or [] if s.get("uses") == GATE_ACTION]
    if len(steps) != 1:
        return [f"G3 {context!r}: expected exactly one `{GATE_ACTION}` step, found {len(steps)}"]
    with_ = steps[0].get("with") or {}
    if with_.get("context") != context:
        problems.append(f"G3 {context!r}: verdict `context` is {with_.get('context')!r}")
    if "needs.changes.result" not in str(with_.get("changes-result", "")):
        problems.append(f"G3 {context!r}: verdict does not read needs.changes.result (fail closed)")
    for w in work:
        if f"needs.{w}." not in str(with_.get("work-ok", "")):
            problems.append(f"G3 {context!r}: `work-ok` does not read the result of {w!r}")
    if "pull_request.draft" not in str(with_.get("draft", "")):
        problems.append(f"G3 {context!r}: `draft` is not wired to the pull request")
    is_gated = str(with_.get("draft-gated", "true")).lower() != "false"
    if is_gated != draft_gated:
        problems.append(f"G3 {context!r}: draft-gated is {is_gated}, expected {draft_gated}")
    return problems


# ── G1-G4 on the real tree ───────────────────────────────────────────────────


def test_the_scan_binds_to_the_workflows_it_guards():
    """A glob that matched nothing would make everything below assert nothing (G6)."""
    workflows = _all_workflows()
    assert "ci.yml" in workflows and len(workflows) > 20
    published = _publishers(workflows)
    assert (
        set(published) == REQUIRED_CONTEXTS
    ), f"the scan resolved {sorted(published)}; missing {sorted(REQUIRED_CONTEXTS - set(published))}"
    assert len(REQUIRED_CONTEXTS) == 11


def test_every_required_context_has_one_always_reporting_publisher():
    assert _gate_violations(_all_workflows()) == []


def test_the_governance_checks_are_separate_ungated_workflows():
    """D1: kept out of ci.yml, and neither carries a draft clause (they run on drafts)."""
    workflows = _all_workflows()
    for context, fname in GOVERNANCE.items():
        assert workflows[fname]["jobs"], fname
        assert [j for j, s in workflows[fname]["jobs"].items() if _job_name(j, s) == context], (context, fname)
        for spec in workflows[fname]["jobs"].values():
            assert "draft" not in str(spec.get("if", "")), f"{fname} gained a draft clause"


def test_the_shims_are_gone():
    for name in SHIMS:
        assert not (WORKFLOW_DIR / name).exists(), f"{name} is back: a same-named second publisher (#17391, #14922)"


# ── G5: the trigger ──────────────────────────────────────────────────────────


def test_ci_triggers_on_stacked_pull_requests_and_on_merge_group():
    """ci.yml publishes nine required contexts, so both triggers are its own.

    `branches:` would drop STACKED pull requests (base is another feature branch): zero
    runs, every context absent (#14747, measured on #14641). `paths:` would deadlock a PR
    that misses the filter (#13388). `ready_for_review` is the only event marking a PR ready
    fires, and the gates fail on a draft until it does.
    """
    on = _on(_load(CI))
    assert "merge_group" in on, "no merge_group trigger: no context can report inside a queue (#14054)"
    pull_request = on.get("pull_request") or {}
    assert isinstance(pull_request, dict)
    for key in ("paths", "paths-ignore", "branches", "branches-ignore"):
        assert key not in pull_request, f"ci.yml filters pull_request.{key}: a context can fail to report"
    assert {"opened", "synchronize", "reopened", "ready_for_review"} <= set(pull_request.get("types", []))


@pytest.mark.parametrize("fname", sorted(set(GOVERNANCE.values())))
def test_the_separate_required_workflows_have_no_pull_request_paths(fname):
    on = _on(_load(WORKFLOW_DIR / fname))
    assert "paths" not in (on.get("pull_request") or {}), f"{fname} would deadlock a PR that misses its filter"


# ── G7: control fixtures -- the checker must catch what it claims ────────────


def _fixture() -> dict:
    return copy.deepcopy(_all_workflows())


def test_control_a_gate_missing_always_fails_the_checker():
    """The deliberate break: `if: always()` removed from one gate."""
    docs = _fixture()
    del docs["ci.yml"]["jobs"]["python-suite"]["if"]
    problems = _gate_violations(docs)
    assert any(p.startswith("G2 'python-suite'") and "always()" in p for p in problems), problems


def test_control_a_gate_that_can_be_skipped_by_a_filter_output_fails_the_checker():
    docs = _fixture()
    docs["ci.yml"]["jobs"]["code-quality"]["if"] = "${{ needs.changes.outputs.run_code_quality == 'true' }}"
    problems = _gate_violations(docs)
    assert any(p.startswith("G2 'code-quality'") for p in problems), problems


def test_control_a_second_publisher_of_a_context_fails_the_checker():
    """The shim shape #17391 and #14922 measured: two same-named jobs."""
    docs = _fixture()
    docs["backend-required-context.yml"] = {
        "jobs": {"startup-import-smoke": {"name": "startup-import-smoke", "if": "needs.changes.outputs.x != 'true'"}}
    }
    problems = _gate_violations(docs)
    assert any(p.startswith("G1 'startup-import-smoke'") for p in problems), problems


def test_control_a_work_job_named_like_a_required_context_fails_the_checker():
    docs = _fixture()
    docs["_gate-code-quality.yml"]["jobs"]["audit"]["name"] = "code-quality"
    problems = _gate_violations(docs)
    assert any(p.startswith("G4 _gate-code-quality.yml:audit") for p in problems), problems


def test_control_a_gate_that_ignores_detection_failure_fails_the_checker():
    docs = _fixture()
    step = docs["ci.yml"]["jobs"]["smoke-test"]["steps"][1]
    step["with"]["changes-result"] = "success"
    problems = _gate_violations(docs)
    assert any(p.startswith("G3 'smoke-test'") and "fail closed" in p for p in problems), problems


def test_control_a_gate_that_ignores_its_work_fails_the_checker():
    docs = _fixture()
    docs["ci.yml"]["jobs"]["api-wiring"]["steps"][1]["with"]["work-ok"] = "true"
    problems = _gate_violations(docs)
    assert any(p.startswith("G3 'api-wiring'") and "run-api-wiring" in p for p in problems), problems


def test_the_work_callers_hold_back_draft_pull_requests():
    """A required gate's work does not run on a draft; the gate says why (D4).

    The exception is `run-precommit`, which carries no `ready` condition.
    """
    jobs = _load(CI)["jobs"]
    for context, (_, work, draft_gated) in GATES.items():
        for w in work:
            if w == "python-shard":
                cond = str(jobs["python-shard"].get("if", ""))
            else:
                cond = str(jobs[w].get("if", ""))
            if draft_gated:
                assert "outputs.ready == 'true'" in cond, f"{w} (for {context}) is not held back on a draft"
            else:
                assert "ready" not in cond, f"{w} (for {context}) must run on drafts"


def test_the_gate_names_are_the_exact_branch_protection_strings():
    """A rename silently un-requires a context. Compare against the literal job `name:`."""
    jobs = _load(CI)["jobs"]
    names = {_job_name(j, s) for j, s in jobs.items()}
    assert set(GATES) <= names
