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
G5  ci.yml's pull_request trigger carries no paths/branches filter and has the five
    types (labeled starts the suite when the coordinator adds land-next, #20825)
G6  the required list is non-vacuous: the scan resolves every one of the eleven
G7  control fixtures: a gate missing `if: always()`, a gate gated on a filter output
    and a duplicated context name must each FAIL the checker
"""

import copy
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._gate_if import runs_when_needs_skipped, runs_without_land_next
from tools.lint._comment_syntax import code_text

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
#: Runs before the verdict: a cancelled upstream ends the run `cancelled`, not failed or skipped (#17764).
CANCEL_ACTION = "./.github/actions/cancel-run-on-cancelled-upstream"
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
        if not _gate_if_ok(spec):
            problems.append(
                f"G2 {context!r}: `if:` is {spec.get('if')!r}, must be exactly `always() && !({NOOP})` -- "
                "a gate skipped by a filter re-publishes `skipped`; a no-op label event must publish nothing"
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
    problems += _cancel_step_violations(context, spec, work)
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
    if "'land-next'" not in str(with_.get("admitted", "")):
        problems.append(f"G3 {context!r}: `admitted` does not read the land-next label (fail closed, #20825)")
    if "noop" in with_:
        problems.append(f"G3 {context!r}: a `noop` input is back: no event may pass a gate without a verdict (#20825)")
    is_gated = str(with_.get("draft-gated", "true")).lower() != "false"
    if is_gated != draft_gated:
        problems.append(f"G3 {context!r}: draft-gated is {is_gated}, expected {draft_gated}")
    return problems


def _cancel_step_violations(context: str, spec: dict, work: tuple) -> list:
    """G5: the cancel step runs before the verdict and reads every upstream the verdict reads (#17764)."""
    uses = [s.get("uses") for s in spec.get("steps") or []]
    if uses.count(CANCEL_ACTION) != 1:
        return [f"G5 {context!r}: expected exactly one `{CANCEL_ACTION}` step, found {uses.count(CANCEL_ACTION)}"]
    if uses.index(CANCEL_ACTION) > uses.index(GATE_ACTION):
        return [f"G5 {context!r}: the cancel step runs after the verdict, so a parked run reads as failed"]
    results = str((spec["steps"][uses.index(CANCEL_ACTION)].get("with") or {}).get("results", ""))
    missing = [u for u in ("changes", *work) if f"needs.{u}.result" not in results]
    problems = [f"G5 {context!r}: the cancel step does not read needs.{u}.result" for u in missing]
    if (spec.get("permissions") or {}).get("actions") != "write":
        problems.append(f"G5 {context!r}: the job lacks `permissions: actions: write`, so the cancel cannot run")
    return problems


def _norm(expr) -> str:
    """An `if:` with comments stripped, the `${{ }}` wrapper removed and whitespace collapsed."""
    text = code_text(str(expr or ""), name="workflow.yml")
    return " ".join(text.replace("${{", " ").replace("}}", " ").split())


def _gate_if_ok(spec: dict) -> bool:
    """A gate is `always()` except on a no-op label event, where it is skipped so the earlier verdict stands."""
    return _norm(spec.get("if")) == f"always() && !({NOOP})"


def _verdict_step(job: dict) -> dict:
    return next(s for s in job["steps"] if s.get("uses") == GATE_ACTION)


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
    assert {"opened", "synchronize", "reopened", "ready_for_review", "labeled"} <= set(pull_request.get("types", []))


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
    step = _verdict_step(docs["ci.yml"]["jobs"]["smoke-test"])
    step["with"]["changes-result"] = "success"
    problems = _gate_violations(docs)
    assert any(p.startswith("G3 'smoke-test'") and "fail closed" in p for p in problems), problems


def test_control_a_gate_that_ignores_its_work_fails_the_checker():
    docs = _fixture()
    _verdict_step(docs["ci.yml"]["jobs"]["api-wiring"])["with"]["work-ok"] = "true"
    problems = _gate_violations(docs)
    assert any(p.startswith("G3 'api-wiring'") and "run-api-wiring" in p for p in problems), problems


def test_the_work_callers_hold_back_draft_pull_requests():
    """A required gate's work does not run until the PR carries land-next; the gate says why (D4, #20825).

    `ready` requires the label, so this holds for run-precommit too (it no longer runs on drafts).
    """
    jobs = _load(CI)["jobs"]
    for context, (_, work, draft_gated) in GATES.items():
        for w in work:
            if w == "python-shard":
                cond = str(jobs["python-shard"].get("if", ""))
            else:
                cond = str(jobs[w].get("if", ""))
            assert "outputs.ready == 'true'" in cond, f"{w} (for {context}) is not held back until land-next"


def test_the_gate_names_are_the_exact_branch_protection_strings():
    """A rename silently un-requires a context. Compare against the literal job `name:`."""
    jobs = _load(CI)["jobs"]
    names = {_job_name(j, s) for j, s in jobs.items()}
    assert set(GATES) <= names


def test_control_a_gate_whose_cancel_step_misses_its_work_fails_the_checker():
    """G5 contrast: dropping the work job from the cancel step's `results` is caught (#17764)."""
    docs = _fixture()
    steps = docs["ci.yml"]["jobs"]["migration-matrix"]["steps"]
    cancel = next(s for s in steps if s.get("uses") == CANCEL_ACTION)
    cancel["with"]["results"] = "${{ needs.changes.result }}"
    problems = _gate_violations(docs)
    assert any(p.startswith("G5 'migration-matrix'") and "run-migration-gate" in p for p in problems), problems


def test_control_a_cancel_step_after_the_verdict_fails_the_checker():
    docs = _fixture()
    steps = docs["ci.yml"]["jobs"]["code-quality"]["steps"]
    i = next(n for n, s in enumerate(steps) if s.get("uses") == CANCEL_ACTION)
    steps.append(steps.pop(i))
    problems = _gate_violations(docs)
    assert any(p.startswith("G5 'code-quality'") and "after the verdict" in p for p in problems), problems


# --- Only land-next pull requests run (#20825) ---------------------------------------------------
# Owner rule 2026-11-28: the PRs labelled `land-next` are the only ones that run. The coordinator labels
# exactly the admitted ones and parks the rest. For `pull_request` events NO job does real work without
# the label; push, merge_group, schedule and dispatch are unaffected. A required context never reports
# success for an un-admitted PR: ci.yml's gates read `admitted` (verdict.sh fails closed), and the two
# governance workflows fail their first step.

# THE one form: expressions cannot import, so every workflow spells it this way; anything else is rejected.
LAND_NEXT = "contains(github.event.pull_request.labels.*.name, 'land-next')"
# THE no-op event: an unrelated label. Every required-context job is skipped on it, so it publishes NOTHING new
# and the earlier real verdict stands. There is no "no-op success": a pass here would green an un-admitted PR.
NOOP = "github.event_name == 'pull_request' && github.event.action == 'labeled' && github.event.label.name != 'land-next'"
# A `labeled` run for another label skips, so an unrelated label starts no work.
LABEL_IS_LAND_NEXT = "github.event.label.name == 'land-next'"

# Workflows with no land-next condition, each justified. Only a workflow whose work cannot be a PR's.
LAND_NEXT_EXEMPT_WORKFLOWS = {
    "issue-landing-notes.yml": "fires only on `closed` (post-merge issue notes); it never runs for an open PR",
}
CLOSED_ONLY_WORKFLOWS = frozenset(LAND_NEXT_EXEMPT_WORKFLOWS)
# Exempt by job, each justified.
LAND_NEXT_EXEMPT_JOBS = {
    ("phase_validation.yml", "integration-validation"): "not a pull_request job: it runs on push and dispatch only",
}


def _pr_trigger(doc: dict):
    """The `pull_request` trigger as a dict (None when absent), for the three YAML shapes."""
    on = _on(doc)
    if on == "pull_request" or (isinstance(on, list) and "pull_request" in on):
        return {}
    if isinstance(on, dict) and "pull_request" in on:
        return on["pull_request"] or {}
    return None


def _pr_workflows(workflows: dict) -> dict:
    return {n: d for n, d in workflows.items() if _pr_trigger(d) is not None}


def _cond(spec: dict) -> str:
    return code_text(str(spec.get("if", "")), name="workflow.yml")


def _holds_back(spec: dict) -> bool:
    """A real land-next condition: the label test AND the unrelated-label skip, or ci.yml's `ready` output."""
    cond = _cond(spec)
    if "outputs.ready == 'true'" in cond:
        return True
    held = f"{LAND_NEXT} &&" in cond and LABEL_IS_LAND_NEXT in cond and f"!{LAND_NEXT}" not in cond
    return held and not runs_without_land_next(cond)


def _fails_closed(spec: dict) -> bool:
    """A required-context job: skips only an unrelated label, and its first step fails an un-admitted PR."""
    steps = spec.get("steps") or []
    first = steps[0] if steps else {}
    return (
        _norm(spec.get("if")) == f"!({NOOP})"
        and f"!{LAND_NEXT}" in code_text(str(first.get("if", "")), name="workflow.yml")
        and "exit 1" in str(first.get("run", ""))
    )


def _held_back(jobs: dict, name: str, job_id: str, seen: frozenset = frozenset()) -> bool:
    """Held by land-next, exempt, a ci.yml gate, or every job it needs is held back (transitively)."""
    spec = jobs.get(job_id)
    if spec is None or job_id in seen:
        return False
    if (name, job_id) in LAND_NEXT_EXEMPT_JOBS or _holds_back(spec):
        return True
    if name == "ci.yml" and job_id in {g[0] for g in GATES.values()}:
        return _gate_if_ok(spec)  # `always()` bar the no-op event; it fails closed through `admitted` (G3)
    needed = _needs(spec)
    held = all(_held_back(jobs, name, n, seen | {job_id}) for n in needed)
    return bool(needed) and held and not runs_when_needs_skipped(_cond(spec))


def _park_violations(workflows: dict) -> list:
    problems = []
    for name, doc in _pr_workflows(workflows).items():
        if name in LAND_NEXT_EXEMPT_WORKFLOWS:
            continue
        types = _pr_trigger(doc).get("types") or []
        for needed in ("labeled", "ready_for_review"):
            if needed not in types:
                problems.append(f"{name}: pull_request.types lacks {needed} ({types!r})")
        if "-noop-" not in str(doc.get("concurrency", "")) and doc.get("concurrency"):
            problems.append(f"{name}: the concurrency group does not isolate an unrelated-label run")
        governance = name in set(GOVERNANCE.values())
        for job_id, spec in doc["jobs"].items():
            if governance:
                if not _fails_closed(spec):
                    problems.append(f"{name} '{job_id}' is a required context that does not fail closed when not admitted")
            elif not _held_back(doc["jobs"], name, job_id):
                problems.append(f"{name} '{job_id}' is not held back by the land-next condition")
    ready = str((((workflows.get("ci.yml") or {}).get("jobs") or {}).get("changes") or {}).get("outputs", {}).get("ready", ""))
    if LAND_NEXT not in ready:
        problems.append("ci.yml: changes.outputs.ready does not require the land-next label")
    return problems


def test_every_pull_request_workflow_refires_on_label_and_runs_only_for_land_next():
    assert _park_violations(_all_workflows()) == []


def test_every_exemption_names_a_workflow_that_exists_and_a_reason():
    names = {p.name for p in WORKFLOW_DIR.glob("*.yml")}
    assert set(LAND_NEXT_EXEMPT_WORKFLOWS) <= names and all(LAND_NEXT_EXEMPT_WORKFLOWS.values())
    assert all(j in _load(WORKFLOW_DIR / w)["jobs"] and r for (w, j), r in LAND_NEXT_EXEMPT_JOBS.items())


def test_the_required_gates_fail_closed_on_an_unadmitted_pull_request():
    """Each ci.yml gate hands the verdict script `admitted` (the label), is skipped on the no-op event, and
    verdict.sh has no noop path and fails an un-admitted pull_request before anything else."""
    assert _unadmitted_violations(_all_workflows(), _verdict_text()) == []


def _verdict_text() -> str:
    return (REPO_ROOT / ".github" / "actions" / "gate-verdict" / "verdict.sh").read_text(encoding="utf-8")


def _unadmitted_violations(workflows: dict, script: str) -> list:
    """Every way a gate could exit 0 on an un-admitted pull_request (#20825). Empty means none."""
    problems = []
    jobs = (workflows.get("ci.yml") or {}).get("jobs") or {}
    for context, (job_id, _, _) in GATES.items():
        spec = jobs[job_id]
        with_ = (_verdict_step(spec).get("with")) or {}
        if str(with_.get("admitted", "")).replace(" ", "") != ("${{" + LAND_NEXT + "}}").replace(" ", ""):
            problems.append(f"{context}: `admitted` is not the land-next label test")
        if not _gate_if_ok(spec):
            problems.append(f"{context}: the gate `if` does not skip the no-op label event")
        if "noop" in with_:
            problems.append(f"{context}: passes a noop input")
    code = code_text(script, name="verdict.sh")
    if "NOOP" in code.upper():
        problems.append("verdict.sh has a noop path")
    marker = 'GATE_ADMITTED}" != "true"'
    head = code.split(marker)[0] if marker in code else code
    if marker not in code or "exit 0" in head:
        problems.append("verdict.sh can exit 0 before the not-admitted check")
    return problems


def test_control_a_gate_that_can_exit_zero_unadmitted_fails_the_checker():
    docs = _fixture()
    noop = 'if [ "${GATE_NOOP}" = "true" ]; then\n  exit 0\nfi\n'
    assert any("noop path" in p for p in _unadmitted_violations(docs, noop + _verdict_text()))
    assert any("before the not-admitted" in p for p in _unadmitted_violations(docs, "exit 0\n" + _verdict_text()))
    docs["ci.yml"]["jobs"]["python-suite"]["if"] = "always()"
    assert any("python-suite: the gate `if`" in p for p in _unadmitted_violations(docs, _verdict_text()))
    _verdict_step(docs["ci.yml"]["jobs"]["code-quality"])["with"]["noop"] = "true"
    assert any("code-quality: passes a noop" in p for p in _unadmitted_violations(docs, _verdict_text()))


def test_control_a_workflow_without_labeled_fails_the_park_checker():
    docs = _fixture()
    docs["marker-tests.yml"][True]["pull_request"]["types"] = ["opened", "synchronize", "ready_for_review"]
    assert any(p.startswith("marker-tests.yml: pull_request.types lacks labeled") for p in _park_violations(docs))
    docs = _fixture()
    docs["marker-tests.yml"][True]["pull_request"]["types"] = ["opened", "synchronize", "labeled"]
    assert any("lacks ready_for_review" in p for p in _park_violations(docs))


def test_control_a_job_missing_the_land_next_condition_fails_the_park_checker():
    for cond in (
        "${{ github.event_name != 'pull_request' }}",
        "${{ github.event.pull_request.draft == false }}",
        f"${{{{ !{LAND_NEXT} }}}}",
        "${{ true }}\n# " + LAND_NEXT + " && " + LABEL_IS_LAND_NEXT,
    ):
        docs = _fixture()
        docs["marker-tests.yml"]["jobs"]["marker-tests"]["if"] = cond
        assert any("marker-tests.yml 'marker-tests' is not held back" in p for p in _park_violations(docs)), cond
    docs = _fixture()
    docs["ci.yml"]["jobs"]["run-security"].update({"if": "${{ needs.changes.outputs.held != 'true' }}", "needs": []})
    assert any("'run-security'" in p for p in _park_violations(docs))
    docs = _fixture()
    docs["ci.yml"]["jobs"]["changes"]["outputs"]["ready"] = "${{ github.event.pull_request.draft == false }}"
    assert any("ready does not require" in p for p in _park_violations(docs))


def test_control_a_required_context_that_can_pass_unadmitted_fails_the_park_checker():
    docs = _fixture()
    del docs["no-commit-trailers.yml"]["jobs"]["check-trailers"]["steps"][0]["run"]
    assert any("no-commit-trailers.yml 'check-trailers'" in p for p in _park_violations(docs))
    docs = _fixture()
    docs["pr-blocking-findings.yml"]["jobs"]["blocking-findings"]["if"] = f"${{{{ {LAND_NEXT} }}}}"
    assert any("pr-blocking-findings.yml" in p for p in _park_violations(docs))


def test_control_a_gate_that_ignores_admission_fails_the_checker():
    docs = _fixture()
    del _verdict_step(docs["ci.yml"]["jobs"]["python-suite"])["with"]["admitted"]
    assert any(p.startswith("G3 'python-suite'") and "admitted" in p for p in _gate_violations(docs))


def test_control_a_job_needing_an_ungated_job_fails_the_park_checker():
    docs = _fixture()
    jobs = docs["marker-tests.yml"]["jobs"]
    jobs["follower"] = {"needs": "marker-tests", "runs-on": "ubuntu-latest"}
    jobs["marker-tests"]["if"] = "${{ github.event_name == 'pull_request' }}"
    assert any("marker-tests.yml 'follower' is not held back" in p for p in _park_violations(docs))


def test_the_park_checker_reads_every_pull_request_trigger_shape():
    for shape in ("pull_request", ["pull_request"], {"pull_request": None}):
        docs = _fixture()
        docs["marker-tests.yml"][True] = shape
        assert "marker-tests.yml" in _pr_workflows(docs)
        assert any(p.startswith("marker-tests.yml: pull_request.types") for p in _park_violations(docs))
