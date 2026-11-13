# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependabot pull request must not start the full suite on its own (#21490).

After a dependency-manifest change landed, dependabot rebased ~15 pull requests and opened 5
more within minutes; each started every expensive workflow, 60+ runs were cancelled by hand and
the queue head's guard run sat queued 10-20 minutes for a runner.

The rule: every `pull_request` workflow is either on `CHEAP` (named, with its job count, so a
cheap workflow that grows a job is looked at again) or each of its expensive jobs is held --
its `if:` names the dependabot author / `changes` outputs `ready` or `held`, or it `needs` a
job that is. "Expensive" is a property of the job (a reusable-workflow call, a timeout of
`_EXPENSIVE_MINUTES` or more, or an end-to-end / smoke / matrix / docker name), not a list.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"

#: Floor on the pull_request workflows examined (35 today); a glob or parse that stops
#: matching must not turn the guard into a pass over nothing.
_MIN_WORKFLOWS = 25
_EXPENSIVE_MINUTES = 20
_EXPENSIVE_NAME = re.compile(r"e2e|end-to-end|smoke|matrix|docker", re.IGNORECASE)
#: How the held scenario (a pull request by dependabot, not a `train-*` head, no `ci:full` label) reads each
#: atom of an `if:`. Anything not listed is UNKNOWN, so a job is
#: held only when its whole condition is definitely False with every unknown term left unknown (three-valued
#: logic, so `!unknown` is unknown too). That rejects `a || hold` and a hold sitting in a branch that does not
#: gate the job. `== 'dependabot[bot]'` is True here: such a job
#: runs for dependabot.
_ATOMS_FALSE = (
    re.compile(r"github\.event\.pull_request\.user\.login\s*!=\s*'dependabot\[bot\]'"),
    re.compile(r"startsWith\(github\.event\.pull_request\.head\.ref,\s*'train-'\)"),
    re.compile(r"contains\(github\.event\.pull_request\.labels\.\*\.name,\s*'ci:full'\)"),
    re.compile(r"github\.event_name\s*!=\s*'pull_request'"),
)
_CHANGES_ATOMS = {
    "held": re.compile(r"needs\.changes\.outputs\.held\s*!=\s*'true'"),
    "ready": re.compile(r"needs\.changes\.outputs\.ready\s*==\s*'true'"),
}
#: A dependent that runs whatever its dependency did is not held by inheriting.
_ALWAYS_RUNS = re.compile(r"always\(\)|cancelled\(\)|failure\(\)")

#: Workflows with no expensive job, by name -> job count. A new job makes the count differ and
#: forces a look at whether the workflow is still cheap.
CHEAP: dict[str, int] = {
    "actionlint.yml": 1,
    "ansible-file-references.yml": 1,
    "ansible-free-form-args.yml": 1,
    "ansible-role-facts-test.yml": 1,
    "ci-dispatch-watchdog.yml": 1,
    "constraint-drift.yml": 1,
    "docs-liquid-tags.yml": 1,
    "duplication-guard.yml": 2,
    "frontend-codegen-drift.yml": 1,
    "frontend-typecheck-regression.yml": 1,
    "issue-landing-notes.yml": 2,
    "no-commit-trailers.yml": 1,
    "phase_validation.yml": 2,
    "pr-blocking-findings.yml": 1,
    "pr-issue-validation.yml": 2,
    "pr-merge-conflict-gate.yml": 1,
    "pr-queue-gate.yml": 1,
    "pr-structure.yml": 1,
    "pr-template-check.yml": 2,
    "ssot-coverage.yml": 1,
    "stylelint-tokens.yml": 1,
    "train-content-gate.yml": 1,
    "trajectory-eval.yml": 1,  # non-blocking and cheap; held anyway
    "wiki.yml": 1,
}

#: (workflow, job) -> why an expensive-looking job is not held.
EXEMPT_JOBS: dict[tuple[str, str], str] = {
    ("ci.yml", "run-auto-fix-types"): "runs only when run-generated-types FAILED; that job is skipped when held",
    (
        "ci.yml",
        "run-precommit",
    ): "the config check carries the SPDX and symlink checks and runs on every PR, drafts included (#17957)",
}


def _triggers(doc: dict) -> dict:
    """The `on:` block; PyYAML reads the bare key `on` as the boolean True."""
    return doc.get(True) or doc.get("on") or {}


def pull_request_workflows(directory=WORKFLOW_DIR) -> dict[str, dict]:
    found = {}
    for path in sorted(p for p in directory.iterdir() if p.suffix == ".yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "pull_request" in _triggers(doc):
            found[path.name] = doc
    return found


def _is_expensive(job_id: str, job: dict) -> bool:
    timeout = job.get("timeout-minutes")
    return bool(
        "uses" in job
        or (isinstance(timeout, int) and timeout >= _EXPENSIVE_MINUTES)
        or _EXPENSIVE_NAME.search(job_id)
        or _EXPENSIVE_NAME.search(str(job.get("name", "")))
    )


#: The ci.yml gate jobs that run on purpose when held and report "held" (verdict.sh step 2b).
REPORTING_GATES = frozenset(
    {
        "python-suite",
        "code-quality",
        "startup-import-smoke",
        "unit-tests",
        "smoke-test",
        "api-wiring",
        "migration-matrix",
        "verify-generated-types",
    }
)


def _tokens(expr: str) -> list[str]:
    """`&&`, `||`, `!`, grouping parentheses and atoms; a call such as `startsWith(a, 'b')` is one atom."""
    out, i, buf = [], 0, ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            out.append(buf.strip())
        buf = ""

    while i < len(expr):
        c = expr[i]
        if c == "'":
            j = expr.index("'", i + 1)
            buf += expr[i : j + 1]
            i = j + 1
        elif expr.startswith(("&&", "||"), i):
            flush()
            out.append(expr[i : i + 2])
            i += 2
        elif c == "(" and re.search(r"[\w.]$", buf.rstrip()) and buf.strip():
            depth, j = 0, i
            while True:
                depth += {"(": 1, ")": -1}.get(expr[j], 0) if expr[j] != "'" else 0
                if expr[j] == "'":
                    j = expr.index("'", j + 1)
                j += 1
                if depth == 0:
                    break
            buf += expr[i:j]
            i = j
        elif c in "()" or (c == "!" and not expr.startswith("!=", i)):
            flush()
            out.append(c)
            i += 1
        else:
            buf += c
            i += 1
    flush()
    return out


def _atom_value(atom: str, defined: frozenset) -> bool | None:
    atom = " ".join(atom.split())
    if any(p.fullmatch(atom) for p in _ATOMS_FALSE):
        return False
    if any(name in defined and p.fullmatch(atom) for name, p in _CHANGES_ATOMS.items()):
        return False
    return True if atom == "true" else None


def condition_value(condition: str, defined: frozenset = frozenset()) -> bool | None:
    """The `if:` under the held scenario: False = skipped for it, True = runs, None = cannot tell."""
    expr = condition.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2]
    toks, pos = _tokens(expr), [0]

    def peek() -> str:
        return toks[pos[0]] if pos[0] < len(toks) else ""

    def take() -> str:
        pos[0] += 1
        return toks[pos[0] - 1]

    def p_or() -> bool | None:
        values = [p_and()]
        while peek() == "||":
            take()
            values.append(p_and())
        return True if True in values else None if None in values else False

    def p_and() -> bool | None:
        values = [p_not()]
        while peek() == "&&":
            take()
            values.append(p_not())
        return False if False in values else None if None in values else True

    def p_not() -> bool | None:
        if peek() == "!":
            take()
            inner = p_not()
            return None if inner is None else not inner
        if peek() == "(":
            take()
            value = p_or()
            take()  # ")"
            return value
        return _atom_value(take(), defined)

    return p_or() if toks else True


def _changes_outputs(jobs: dict) -> frozenset:
    return frozenset((jobs.get("changes") or {}).get("outputs") or {})


def classify(jobs: dict) -> dict[str, str]:
    """job -> "direct" (its own condition skips it for a held run) or "inherited" (needs a held job and is skippable)."""
    defined = _changes_outputs(jobs)
    kind = {
        j: "direct" for j, spec in jobs.items() if "if" in spec and condition_value(str(spec["if"]), defined) is False
    }
    while True:
        more = {
            j: "inherited"
            for j, spec in jobs.items()
            if j not in kind and set(_needs(spec)) & set(kind) and not _ALWAYS_RUNS.search(str(spec.get("if", "")))
        }
        if not more:
            return kind
        kind.update(more)


def _held_jobs(jobs: dict) -> set[str]:
    return set(classify(jobs))


def _needs(spec: dict) -> list:
    needs = spec.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def violations(workflows: dict[str, dict], cheap=CHEAP, exempt=EXEMPT_JOBS) -> list[str]:
    problems = []
    for name, doc in workflows.items():
        jobs = doc.get("jobs") or {}
        expensive = [
            j
            for j, spec in jobs.items()
            if _is_expensive(j, spec) and (name, j) not in exempt and not (name == "ci.yml" and j in REPORTING_GATES)
        ]
        if name in cheap:
            if len(jobs) != cheap[name]:
                problems.append(
                    f"{name}: allow-listed with {cheap[name]} job(s) but has {len(jobs)}; re-check it is still cheap"
                )
            if expensive:
                problems.append(f"{name}: allow-listed as cheap but has expensive job(s) {expensive}")
            continue
        if not expensive:
            problems.append(f"{name}: no expensive job -- add it to CHEAP with its job count")
        held = _held_jobs(jobs)
        problems.extend(
            f"{name}: expensive job {j!r} is not held for dependabot pull requests (#21490)"
            for j in expensive
            if j not in held
        )
    return problems


def test_the_scan_examines_the_pull_request_workflows():
    assert len(pull_request_workflows()) >= _MIN_WORKFLOWS


def test_every_allow_listed_workflow_still_exists_and_triggers_on_pull_request():
    found = pull_request_workflows()
    assert not sorted(set(CHEAP) - set(found)), "stale CHEAP entries"
    for wf, job in EXEMPT_JOBS:
        assert job in found[wf]["jobs"], f"stale exemption {wf}:{job}"


def test_every_pull_request_workflow_holds_its_expensive_jobs_for_dependabot():
    problems = violations(pull_request_workflows())
    assert not problems, "\n".join(problems)


def test_ci_defines_held_and_every_gate_passes_it_to_the_verdict():
    jobs = pull_request_workflows()["ci.yml"]["jobs"]
    assert "held" in jobs["changes"]["outputs"]
    gates = [
        step["with"]
        for spec in jobs.values()
        for step in spec.get("steps", [])
        if str(step.get("uses", "")).endswith("gate-verdict")
        and str(step["with"].get("draft-gated", "true")) != "false"
    ]
    assert len(gates) >= 8
    assert all("held" in w for w in gates), "a draft-gated verdict gate does not pass `held`"


# --- controls: the detector must flag what it is meant to flag -------------------------------
_UNGATED = {
    "x.yml": {
        "jobs": {
            "run-big": {"uses": "./.github/workflows/_gate-x.yml"},
            "slow": {"timeout-minutes": 45, "if": "${{ true }}"},
        }
    }
}
_GATED = {
    "x.yml": {
        "jobs": {
            "changes": {"outputs": {"held": "x"}},
            "run-big": {"uses": "./a.yml", "if": "${{ needs.changes.outputs.held != 'true' }}"},
            "slow": {"timeout-minutes": 45, "if": "${{ github.event.pull_request.user.login != 'dependabot[bot]' }}"},
            "after": {"uses": "./b.yml", "needs": ["slow"]},
        }
    }
}


def test_control_an_ungated_expensive_job_is_flagged():
    problems = violations(_UNGATED, cheap={})
    assert len(problems) == 2, problems


def test_control_held_jobs_and_their_dependants_pass():
    assert violations(_GATED, cheap={}) == []


def test_control_a_cheap_workflow_that_grew_a_job_is_flagged():
    wf = {"c.yml": {"jobs": {"a": {}, "b": {}}}}
    assert violations(wf, cheap={"c.yml": 1})
    assert violations(wf, cheap={"c.yml": 2}) == []


def test_a_held_gate_fails_and_says_held_never_passes():
    from repo_tests._gate_verdict_driver import run_verdict

    code, out = run_verdict(GATE_HELD="true", GATE_APPLIES="false", GATE_WORK_OK="false")
    assert code == 1 and "held" in out
    # not held, same inputs: "not affected" passes -- the contrast the held branch must not share
    assert run_verdict(GATE_APPLIES="false", GATE_WORK_OK="false")[0] == 0
    # a held flag on a push event is inert
    assert run_verdict(GATE_HELD="true", GATE_EVENT="push")[0] == 0


def test_control_the_positive_dependabot_test_is_not_a_hold():
    wf = {
        "x.yml": {
            "jobs": {
                "big": {"timeout-minutes": 45, "if": "${{ github.event.pull_request.user.login == 'dependabot[bot]' }}"}
            }
        }
    }
    assert violations(wf, cheap={})


def test_control_changes_outputs_count_only_where_changes_defines_them():
    big = {"timeout-minutes": 45, "if": "${{ needs.changes.outputs.ready == 'true' }}", "needs": ["changes"]}
    assert violations({"x.yml": {"jobs": {"changes": {"outputs": {}}, "big": big}}}, cheap={})
    assert violations({"x.yml": {"jobs": {"changes": {"outputs": {"ready": "x"}}, "big": big}}}, cheap={}) == []


@pytest.mark.parametrize("condition", ["always()", "${{ !cancelled() }}", "${{ failure() }}"])
def test_control_an_always_running_dependent_does_not_inherit_the_hold(condition):
    jobs = {"held": {"if": "${{ github.event.pull_request.user.login != 'dependabot[bot]' }}"}}
    jobs["after"] = {"uses": "./a.yml", "needs": ["held"], "if": condition}
    assert violations({"x.yml": {"jobs": jobs}}, cheap={}) == [
        "x.yml: expensive job 'after' is not held for dependabot pull requests (#21490)"
    ]
    exempted = violations({"x.yml": {"jobs": jobs}}, cheap={}, exempt={("x.yml", "after"): "reports"})
    assert not any("not held" in problem for problem in exempted)


def test_the_reporting_gates_are_real_ci_jobs_that_always_run():
    jobs = pull_request_workflows()["ci.yml"]["jobs"]
    assert all(g in jobs and jobs[g].get("if") == "always()" for g in REPORTING_GATES)


_HOLD = "github.event.pull_request.user.login != 'dependabot[bot]'"
_TRAIN = "startsWith(github.event.pull_request.head.ref, 'train-')"


@pytest.mark.parametrize(
    "condition, held",
    [
        (f"${{{{ {_HOLD} }}}}", True),
        (f"${{{{ true && {_HOLD} }}}}", True),
        (f"${{{{ {_HOLD} || {_TRAIN} }}}}", True),
        (f"${{{{ github.event_name != 'pull_request' || (a.b == false && ({_HOLD} || {_TRAIN})) }}}}", True),
        (f"${{{{ !({_HOLD}) }}}}", False),
        (f"${{{{ x.y == 'z' || {_HOLD} }}}}", False),
        (f"${{{{ always() || {_HOLD} }}}}", False),
        (f"${{{{ (x.y == 'z' || {_HOLD}) && w.v == 'q' }}}}", False),
        ("${{ github.event.pull_request.user.login == 'dependabot[bot]' }}", False),
        ("${{ x.y == 'z' }}", False),
        ("${{ !cancelled() }}", False),
    ],
)
def test_control_only_a_conjunct_hold_is_effective(condition, held):
    assert (condition_value(condition) is False) is held


def test_control_a_changes_output_is_a_hold_only_where_changes_defines_that_output():
    cond = "${{ needs.changes.outputs.held != 'true' }}"
    assert condition_value(cond, frozenset({"held"})) is False
    assert condition_value(cond, frozenset({"ready"})) is not False, "reads `held`, but changes defines only `ready`"
    assert condition_value("${{ needs.changes.outputs.ready == 'true' }}", frozenset({"ready"})) is False
