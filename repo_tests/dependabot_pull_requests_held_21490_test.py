# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependabot or release promotion pull request must not start the full suite on its own (#21490, #21519).

After a dependency-manifest change landed, dependabot rebased ~15 pull requests and opened 5
more within minutes; each started every expensive workflow, 60+ runs were cancelled by hand and
the queue head's guard run sat queued 10-20 minutes for a runner.

The rule: every `pull_request` workflow is either on `CHEAP` (named, with its job count, so a
cheap workflow that grows a job is looked at again) or each of its expensive jobs is held --
its `if:` names the dependabot author / `changes` outputs `ready` or `held`, or it `needs` a
job that is. In `ci.yml` "expensive" is a property of the job (a reusable-workflow call, a timeout of
`_EXPENSIVE_MINUTES` or more, or an end-to-end / smoke / matrix / docker name), because its change
detection and reporting jobs run on purpose. In every other workflow EVERY job is in scope: a job
that is neither held nor named in `EXEMPT_JOBS` is a violation, so a job the heuristic does not
recognise (no timeout, no matching name) cannot run for a held pull request (#21519).

#21519: the same rule holds the release promotion pull request (head = this repository's default
branch, base = `release`) unless it carries `ci:full`. A job must be held in BOTH scenarios in
`SCENARIOS`; three running scenarios (labelled, fork branch of the same name, ordinary feature branch)
pin that the promotion clause holds nothing else. Every inline copy of the clause is the same text.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"

#: Floor on the pull_request workflows examined (35 today); a glob or parse that stops
#: matching must not turn the guard into a pass over nothing.
_MIN_WORKFLOWS = 25
_EXPENSIVE_MINUTES = 20
_EXPENSIVE_NAME = re.compile(r"e2e|end-to-end|smoke|matrix|docker", re.IGNORECASE)
#: Each atom of an `if:` the scenarios speak about. Anything not listed in a scenario is UNKNOWN, so a job is
#: held only when its whole condition is definitely False with every unknown term left unknown (three-valued
#: logic, so `!unknown` is unknown too). That rejects `a || hold` and a hold sitting in a branch that does not
#: gate the job. `== 'dependabot[bot]'` is not an atom: such a job runs for dependabot.
_ATOMS = {
    "not_dependabot": re.compile(r"github\.event\.pull_request\.user\.login\s*!=\s*'dependabot\[bot\]'"),
    "train": re.compile(r"startsWith\(github\.event\.pull_request\.head\.ref,\s*'train-'\)"),
    "label": re.compile(r"contains\(github\.event\.pull_request\.labels\.\*\.name,\s*'ci:full'\)"),
    "not_pr": re.compile(r"github\.event_name\s*!=\s*'pull_request'"),
    "head_not_default": re.compile(
        r"github\.event\.pull_request\.head\.ref\s*!=\s*github\.event\.repository\.default_branch"
    ),
    "fork_head": re.compile(r"github\.event\.pull_request\.head\.repo\.full_name\s*!=\s*github\.repository"),
    "base_not_release": re.compile(r"github\.event\.pull_request\.base\.ref\s*!=\s*'release'"),
}
_PROMOTION = {"not_dependabot": True, "train": False, "label": False, "not_pr": False}
_PROMOTION.update(head_not_default=False, fork_head=False, base_not_release=False)
#: scenario -> value of each atom. `held` scenarios must skip every expensive job; `running` ones must not skip any.
SCENARIOS: dict[str, dict[str, bool]] = {
    "dependabot": {"not_dependabot": False, "train": False, "label": False, "not_pr": False},
    "promotion": dict(_PROMOTION),
    "promotion_labelled": {**_PROMOTION, "label": True},
    "fork_branch_named_like_default": {**_PROMOTION, "fork_head": True},
    "feature_branch": {**_PROMOTION, "head_not_default": True},
}
HELD_SCENARIOS = ("dependabot", "promotion")
RUNNING_SCENARIOS = tuple(sorted(set(SCENARIOS) - set(HELD_SCENARIOS)))
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
    (
        "test-durations.yml",
        "land",
    ): "needs a successful store-durations (held) and never runs on a pull_request, so it is skipped when held",
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


def _atom_value(atom: str, defined: frozenset, scenario: str) -> bool | None:
    atom = " ".join(atom.split())
    for name, pattern in _ATOMS.items():
        if pattern.fullmatch(atom):
            return SCENARIOS[scenario].get(name)
    if scenario in HELD_SCENARIOS and any(n in defined and p.fullmatch(atom) for n, p in _CHANGES_ATOMS.items()):
        return False
    return True if atom == "true" else None


def condition_value(condition: str, defined: frozenset = frozenset(), scenario: str = "dependabot") -> bool | None:
    """The `if:` under a scenario: False = skipped for it, True = runs, None = cannot tell."""
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
        return _atom_value(take(), defined, scenario)

    return p_or() if toks else True


def _changes_outputs(jobs: dict) -> frozenset:
    return frozenset((jobs.get("changes") or {}).get("outputs") or {})


def classify(jobs: dict, scenario: str = "dependabot") -> dict[str, str]:
    """job -> "direct" (its own `if:` skips it in a held run) or "inherited" (needs a held job and is skippable)."""
    defined = _changes_outputs(jobs)
    kind = {
        j: "direct"
        for j, spec in jobs.items()
        if "if" in spec and condition_value(str(spec["if"]), defined, scenario) is False
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
    """Jobs skipped in EVERY held scenario."""
    return set.intersection(*(set(classify(jobs, scenario)) for scenario in HELD_SCENARIOS))


def _needs(spec: dict) -> list:
    needs = spec.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _in_scope(name: str, job_id: str, spec: dict) -> bool:
    """ci.yml: the expensive-looking jobs; every other workflow: every job."""
    if name != "ci.yml":
        return True
    return _is_expensive(job_id, spec) and job_id not in REPORTING_GATES


def violations(workflows: dict[str, dict], cheap=CHEAP, exempt=EXEMPT_JOBS) -> list[str]:
    problems = []
    for name, doc in workflows.items():
        jobs = doc.get("jobs") or {}
        expensive = [
            j
            for j, spec in jobs.items()
            if _in_scope(name, j, spec) and (name, j) not in exempt
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
            f"{name}: job {j!r} is not held for dependabot or promotion pull requests (#21490, #21519)"
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


def test_every_pull_request_workflow_holds_its_expensive_jobs_for_dependabot_and_the_promotion():
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


#: The one promotion clause every inline `if:` carries (whitespace-normalised); it is False exactly for a
#: same-repository head on the default branch into `release` without `ci:full` (#21519).
PROMOTION_CLAUSE = (
    "(github.event.pull_request.head.ref != github.event.repository.default_branch"
    " || github.event.pull_request.head.repo.full_name != github.repository"
    " || github.event.pull_request.base.ref != 'release'"
    " || contains(github.event.pull_request.labels.*.name, 'ci:full'))"
)
#: A condition that holds both kinds, for the fixtures below.
_BOTH = f"github.event.pull_request.user.login != 'dependabot[bot]' && {PROMOTION_CLAUSE}"

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
    "ci.yml": {
        "jobs": {
            "changes": {"outputs": {"held": "x"}},
            "run-big": {"uses": "./a.yml", "if": "${{ needs.changes.outputs.held != 'true' }}"},
            "slow": {"timeout-minutes": 45, "if": "${{ " + _BOTH + " }}"},
            "after": {"uses": "./b.yml", "needs": ["slow"]},
        }
    }
}


def test_control_an_ungated_expensive_job_is_flagged():
    problems = violations(_UNGATED, cheap={})
    assert len(problems) == 2, problems


def test_control_held_jobs_and_their_dependants_pass():
    assert violations(_GATED, cheap={}) == []


def test_control_one_held_job_does_not_excuse_an_unheld_sibling_in_a_workflow():
    """The wiring audit ran for the promotion because its sibling job was held (#21519)."""
    held = {"timeout-minutes": 45, "if": "${{ " + _BOTH + " }}"}
    plain = {"runs-on": "ubuntu-latest", "if": "${{ github.event.pull_request.draft == false }}"}
    problems = violations({"x.yml": {"jobs": {"big": held, "audit": plain}}}, cheap={})
    assert len(problems) == 1 and "'audit'" in problems[0], problems
    assert violations({"x.yml": {"jobs": {"big": held, "audit": held}}}, cheap={}) == []
    assert violations({"x.yml": {"jobs": {"big": held, "audit": plain}}}, cheap={}, exempt={("x.yml", "audit"): "r"}) == []


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
    jobs = {"held": {"if": "${{ " + _BOTH + " }}"}}
    jobs["after"] = {"uses": "./a.yml", "needs": ["held"], "if": condition}
    assert violations({"x.yml": {"jobs": jobs}}, cheap={}) == [
        "x.yml: expensive job 'after' is not held for dependabot or promotion pull requests (#21490, #21519)"
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


# --- #21519: the release promotion pull request is held by the same rule ------------------------
_MIN_HELD_COPIES = 10  # 12 inline copies today across 11 workflows; a glob that stops matching must not pass


def _inline_hold_conditions() -> dict[tuple[str, str], str]:
    """(workflow, job) -> normalised `if:` for every job outside ci.yml that holds itself in the dependabot scenario."""
    found = {}
    for name, doc in pull_request_workflows().items():
        if name == "ci.yml":
            continue
        jobs = doc.get("jobs") or {}
        direct = [job for job, kind in classify(jobs).items() if kind == "direct"]
        found.update({(name, job): " ".join(str(jobs[job]["if"]).split()) for job in direct})
    return found


def test_every_inline_hold_carries_the_one_promotion_clause():
    copies = _inline_hold_conditions()
    assert len(copies) >= _MIN_HELD_COPIES
    assert [k for k, text in copies.items() if PROMOTION_CLAUSE not in text] == []


@pytest.mark.parametrize("scenario", HELD_SCENARIOS)
def test_every_real_workflow_job_that_holds_itself_does_so_in_each_held_scenario(scenario):
    for name, doc in pull_request_workflows().items():
        jobs = doc.get("jobs") or {}
        direct_somewhere = {j for s in HELD_SCENARIOS for j, k in classify(jobs, s).items() if k == "direct"}
        assert direct_somewhere <= set(classify(jobs, scenario)), f"{name}: held in one scenario only"


@pytest.mark.parametrize("scenario", RUNNING_SCENARIOS)
def test_the_promotion_clause_holds_nothing_else(scenario):
    """Labelled promotion, a fork branch named like the default branch, an ordinary branch: all still run."""
    for (name, job), text in _inline_hold_conditions().items():
        assert condition_value(text, scenario=scenario) is not False, f"{name}:{job} is held for {scenario}"


def test_control_the_promotion_clause_alone_is_what_separates_the_scenarios():
    cond = "${{ " + PROMOTION_CLAUSE + " }}"
    assert condition_value(cond, scenario="promotion") is False
    assert [condition_value(cond, scenario=s) for s in RUNNING_SCENARIOS] == [True] * len(RUNNING_SCENARIOS)


def test_control_a_job_holding_only_dependabot_is_flagged_for_the_promotion():
    only_dependabot = {"x.yml": {"jobs": {"big": {"timeout-minutes": 45, "if": "${{ " + _HOLD_DEP + " }}"}}}}
    assert violations(only_dependabot, cheap={})


_HOLD_DEP = "github.event.pull_request.user.login != 'dependabot[bot]'"
_HOLD_BASE = {
    "EVENT": "pull_request",
    "AUTHOR": "maintainer",
    "HEAD_REF": "issue-1-work",
    "HEAD_REPO": "owner/repo",
    "BASE_REF": "main",
    "DEFAULT_BRANCH": "main",
    "REPO": "owner/repo",
    "LABELS": "[]",
}
_PROMOTION_ENV = {"HEAD_REF": "main", "BASE_REF": "release"}


def _hold_step() -> dict:
    steps = pull_request_workflows()["ci.yml"]["jobs"]["changes"]["steps"]
    return next(step for step in steps if step.get("id") == "hold")


def _run_hold(tmp_path, **override) -> str:
    """The `held` output of the hold step's own script, run with exactly the step's environment names."""
    assert set(_hold_step()["env"]) == set(_HOLD_BASE), "the step reads an input this driver does not provide"
    out, summary = tmp_path / "output", tmp_path / "summary"
    env = {**os.environ, **_HOLD_BASE, **override, "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary)}
    subprocess.run(["bash", "-c", _hold_step()["run"]], env=env, check=True, capture_output=True, text=True)
    return out.read_text(encoding="utf-8").strip()


@pytest.mark.skipif(shutil.which("jq") is None, reason="the hold step needs jq, as the hosted runner has")
@pytest.mark.parametrize(
    "override, held",
    [
        (_PROMOTION_ENV, "held=true"),
        ({**_PROMOTION_ENV, "LABELS": '["ci:full"]'}, "held=false"),
        ({**_PROMOTION_ENV, "HEAD_REPO": "fork/repo"}, "held=false"),
        ({**_PROMOTION_ENV, "BASE_REF": "main"}, "held=false"),
        ({"HEAD_REF": "issue-1-work", "BASE_REF": "release"}, "held=false"),
        ({**_PROMOTION_ENV, "EVENT": "push"}, "held=false"),
        ({**_PROMOTION_ENV, "LABELS": "not json"}, "held=false"),
        ({"AUTHOR": "dependabot[bot]"}, "held=true"),
        ({"AUTHOR": "dependabot[bot]", "HEAD_REF": "train-1"}, "held=false"),
    ],
)
def test_the_hold_step_holds_the_promotion_and_dependabot_and_nothing_else(tmp_path, override, held):
    assert _run_hold(tmp_path, **override) == held
