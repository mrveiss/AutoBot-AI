# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pull request on a `[skip ci]` head can get its required checks by dispatch (#21577).

The branch sync leaves a head whose message ends `[skip ci]`; GitHub starts no push / pull_request run for
it. A `workflow_dispatch` on the branch is not skipped by the marker and its check runs attach to the branch
head, which is where branch protection reads the eleven required contexts. This file pins the entry point:

* D1  every workflow that publishes a required context has the `workflow_dispatch` entry (the list of
      contexts and their publishers is the one in `required_context_complements_test`, not a second copy)
* D2  the job publishing each context is reachable from a dispatch: an `if: always()` gate behind `changes`,
      work jobs not conditioned on a pull_request / push / merge_group event
* D3  every `github.event.pull_request.*` / `github.head_ref` / `github.base_ref` use in those workflows and
      in the gate bodies behind them has a dispatch fallback, or is explained below (a dispatch has no payload)
* D3b every script reachable from those jobs that reads GITHUB_SHA / GITHUB_REF / the event JSON is listed with
      the reason it is right on a dispatch; the shared scope scripts take the checkout's HEAD, never GITHUB_SHA
* D4  the refusals: the resolver step runs before the hold, a held dispatch fails the job (every gate then
      fails closed), the hold stays the one definition, and the permissions and concurrency cannot cancel
* D5  every checkout of the tree takes the dispatched pull request's test merge commit (the shape the suite's
      `HEAD^1` / `HEAD^2` scoping needs), through the one `checkout_ref` input
* D6  the documented path: the sync workflow's comment and the developer doc name the three dispatches

What this cannot prove: no run is dispatched here. The premise (a dispatch ignores the marker; its check runs
attach to the head) is GitHub's, and is first shown by a dispatched run on a synced head after this lands.
"""

from __future__ import annotations

import copy
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests.required_context_complements_test import GATES, REQUIRED_CONTEXTS, _all_workflows, _on, _publishers

from tools.lint._comment_syntax import code_text

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

_ROOT = repo_root()
_WORKFLOWS = _ROOT / ".github" / "workflows"
_RESOLVER = "dispatch-resolver/pipeline-scripts/dispatched_pr.py"
#: The workflows that publish the eleven required contexts: the suite and the two governance checks.
PUBLISHERS = frozenset({"ci.yml", "no-commit-trailers.yml", "pr-blocking-findings.yml"})
_ALWAYS = ("always()", "${{ always() }}")
_EVENT_ONLY = re.compile(r"github\.event_name\s*==\s*'(pull_request|push|merge_group)'")


@pytest.fixture(scope="module")
def workflows() -> dict:
    return _all_workflows()


def _needs(spec: dict) -> set:
    needs = spec.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


def _publisher_files(flows: dict) -> set[str]:
    return {fname for places in _publishers(flows).values() for fname, _ in places}


def missing_dispatch(flows: dict) -> list[str]:
    """The workflows that publish a required context but cannot be dispatched."""
    return sorted(f for f in _publisher_files(flows) if "workflow_dispatch" not in _on(flows[f]))


def unreachable_from_dispatch(flows: dict) -> list[str]:
    """Publisher jobs a dispatch cannot reach: not `always()`, not behind `changes`, or gated on another event."""
    problems = []
    for context, places in _publishers(flows).items():
        for fname, job_id in places:
            spec = flows[fname]["jobs"][job_id]
            if str(spec.get("if", "always()")).strip() not in _ALWAYS:
                problems.append(f"{context}: {fname}:{job_id} is conditional")
            if fname == "ci.yml" and "changes" not in _needs(spec):
                problems.append(f"{context}: {job_id} does not need `changes`")
    for context, (_, works, _) in GATES.items():
        for work in works:
            if _EVENT_ONLY.search(str(flows["ci.yml"]["jobs"][work].get("if", ""))):
                problems.append(f"{context}: work job {work} runs only on another event")
    return problems


def test_d1_every_publisher_of_a_required_context_can_be_dispatched(workflows) -> None:
    assert set(_publishers(workflows)) == REQUIRED_CONTEXTS, "the eleven required contexts are not all published"
    assert _publisher_files(workflows) == PUBLISHERS, "a required context has a new publisher workflow: dispatch it"
    assert missing_dispatch(workflows) == []


def test_d1_control_a_publisher_without_the_entry_is_flagged(workflows) -> None:
    broken = copy.deepcopy(workflows)
    _on(broken["no-commit-trailers.yml"]).pop("workflow_dispatch")
    assert missing_dispatch(broken) == ["no-commit-trailers.yml"]


def test_d2_each_context_is_published_by_a_job_a_dispatch_reaches(workflows) -> None:
    assert unreachable_from_dispatch(workflows) == []
    ready = workflows["ci.yml"]["jobs"]["changes"]["outputs"]["ready"]
    assert "github.event_name != 'pull_request'" in ready, "a non-pull_request run must not wait on the draft clause"


def test_d2_control_a_conditional_gate_and_an_event_bound_work_job_are_flagged(workflows) -> None:
    broken = copy.deepcopy(workflows)
    broken["ci.yml"]["jobs"]["api-wiring"]["if"] = "${{ github.event_name == 'pull_request' }}"
    broken["ci.yml"]["jobs"]["run-api-wiring"]["if"] = "${{ github.event_name == 'pull_request' }}"
    problems = unreachable_from_dispatch(broken)
    assert any("api-wiring: ci.yml:api-wiring is conditional" in p for p in problems)
    assert any("work job run-api-wiring runs only on another event" in p for p in problems)


# ----- D3: no pull_request payload use without a dispatch fallback -----

_PR_USE = re.compile(r"github\.event\.pull_request[\w.*]*|github\.head_ref|github\.base_ref")
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_BARE_IF = re.compile(r"^\s*(?:- )?if:\s*(?!\$\{\{|[|>])(.+)$", re.MULTILINE)
#: A use is safe when THAT use is the left operand of a `||` whose next operand (past merge_group terms) is the
#: resolver's fact of the same step chain or the dispatched commit, when the resolver's fact comes first
#: (`steps.pr.outputs.x || toJSON(use)`), or when the expression runs only for a pull_request event
#: (`github.event_name != 'pull_request' || ...`). An unrelated `steps.pr.outputs` in the expression is not one.
_FOLLOWED_BY_FALLBACK = re.compile(
    r"\s*(?:[<>=!]=?\s*[\w']+)?\s*\|\|\s*(?:github\.event\.merge_group\.[\w.]+\s*\|\|\s*)*"
    r"(?:steps\.pr\.outputs\.\w+|github\.sha)\b"
)
_PRECEDED_BY_FACT = re.compile(r"steps\.pr\.outputs\.\w+\s*\|\|\s*(?:toJSON\(\s*)?$")
_PR_ONLY_GUARD = "github.event_name != 'pull_request'"
_CHECK_BASE = "github.event.pull_request.base.sha || github.event.merge_group.base_sha"
_BASE_REASON = (
    "base for git_scope_resolve_base, which reads the checked-out merge commit's parents FIRST: a dispatch checks out"
    " the test merge (checkout_ref), so the payload value is only a fallback it never needs"
)
#: (file, normalised expression) -> why a dispatch needs no fallback there.
EXPLAINED = {
    ("ci.yml", "github.event.pull_request.draft == true"): (
        "the gate verdict reads `draft` only for event == pull_request; a dispatch of a draft is refused by the"
        " resolver before any gate runs, and the job failure fails every gate closed"
    ),
    ("ci.yml", "startsWith(github.head_ref, 'train-')"): (
        "the reach-floor audit is for train branches; a dispatch of one is refused"
    ),
    ("_gate-code-quality.yml", _CHECK_BASE): _BASE_REASON,
    ("_gate-precommit.yml", _CHECK_BASE): _BASE_REASON,
}


def _normal(expression: str) -> str:
    return " ".join(expression.split())


def _has_fallback(expression: str, use: re.Match) -> bool:
    return bool(
        _FOLLOWED_BY_FALLBACK.match(expression[use.end() :]) or _PRECEDED_BY_FACT.search(expression[: use.start()])
    )


def pull_request_uses(texts: dict[str, str]) -> list[tuple[str, str]]:
    """(file, normalised expression) for each expression that reads the pull request and has no fallback."""
    found = []
    for fname, text in texts.items():
        expressions = [m.group(1) for m in _EXPRESSION.finditer(text)] + _BARE_IF.findall(text)
        for expression in map(_normal, expressions):
            if _PR_ONLY_GUARD in expression:
                continue
            if any(not _has_fallback(expression, use) for use in _PR_USE.finditer(expression)):
                found.append((fname, expression))
    return found


def _gate_files(flows: dict) -> set[str]:
    jobs = flows["ci.yml"]["jobs"]
    uses = {jobs[work].get("uses", "") for _, works, _ in GATES.values() for work in works}
    return {u.rsplit("/", 1)[1] for u in uses if "/_gate-" in u}


def _scope_texts(flows: dict) -> dict[str, str]:
    return {name: code_text(_WORKFLOWS / name) for name in sorted(PUBLISHERS | _gate_files(flows))}


def test_d3_every_pull_request_use_has_a_dispatch_fallback_or_an_explanation(workflows) -> None:
    texts = _scope_texts(workflows)
    assert len(texts) >= 11, f"the scan reaches {sorted(texts)}: the three publishers and the eight gate bodies"
    unexplained = [use for use in pull_request_uses(texts) if use not in EXPLAINED]
    assert unexplained == [], f"a dispatch has no pull_request payload; these read it with no fallback: {unexplained}"


def test_d3_every_explanation_still_matches_a_use(workflows) -> None:
    found = set(pull_request_uses(_scope_texts(workflows)))
    stale = sorted(set(EXPLAINED) - found)
    assert stale == [], f"explained uses that no longer exist (a stale explanation hides the next): {stale}"


def test_d3_the_detector_flags_a_bare_use_and_accepts_a_fallback() -> None:
    bare = "env:\n  A: ${{ github.event.pull_request.base.sha }}\n"
    assert pull_request_uses({"x.yml": bare}) == [("x.yml", "github.event.pull_request.base.sha")]
    assert pull_request_uses({"x.yml": "A: ${{ github.event.pull_request.number || steps.pr.outputs.number }}"}) == []
    lookalike = "A: ${{ github.event.pull_request.number && steps.pr.outputs.number }}"
    flagged = [("x.yml", "github.event.pull_request.number && steps.pr.outputs.number")]
    assert pull_request_uses({"x.yml": lookalike}) == flagged
    other = "A: ${{ github.event.pull_request.number || github.run_id }} ${{ steps.pr.outputs.n }}"
    assert len(pull_request_uses({"x.yml": other})) == 1, "an unrelated fallback elsewhere is not this use's fallback"
    two = "A: ${{ github.event.pull_request.number || steps.pr.outputs.n }}, ${{ github.event.pull_request.title }}"
    assert pull_request_uses({"x.yml": two}) == [("x.yml", "github.event.pull_request.title")]
    guarded = "if: ${{ github.event_name != 'pull_request' || github.event.pull_request.draft }}"
    assert pull_request_uses({"x.yml": guarded}) == []
    assert pull_request_uses({"x.yml": "if: startsWith(github.head_ref, 'x')\n"}) == [
        ("x.yml", "startsWith(github.head_ref, 'x')")
    ]


# ----- D3b: scripts that read the commit under test from the environment -----

_SCRIPT_REF = re.compile(r"(?:(?<![\w./-])|(?<=\./))((?:pipeline-scripts|scripts|tools)/[A-Za-z0-9_./-]+\.(?:sh|py))")
_ENV_READ = re.compile(r"GITHUB_(?:SHA|REF|HEAD_REF|BASE_REF|EVENT_PATH|EVENT_NAME)\b")
#: script -> why its read of the run's event environment is right on a dispatch, whose GITHUB_SHA is the BRANCH HEAD
#: (a sync merge) and whose GITHUB_REF is the branch, while the checkout is the test merge. A script that reads the
#: commit under test must not appear here: it takes HEAD (the checkout) or an explicit value from its caller.
ENV_READERS = {
    "scripts/lib/git-scope.sh": (
        "GITHUB_BASE_REF is the 3rd fallback of git_scope_resolve_base, after the merge commit's parents; empty on a"
        " dispatch, and the test merge's parents resolve first"
    ),
    "pipeline-scripts/check_codeql_alert_ceiling.sh": (
        "matches CodeQL's analysis of THIS run (ci.yml's run-codeql uploads against GITHUB_REF at GITHUB_SHA, the"
        " branch ref and head on a dispatch); fails closed when none matches. First proved by a dispatched run"
    ),
}


def reachable_scripts(texts: dict[str, str], read) -> dict[str, str]:
    """Every script named (transitively) in the run steps of *texts*, mapped to its comment-free text."""
    found: dict[str, str] = {}
    queue = [ref for text in texts.values() for ref in _SCRIPT_REF.findall(text)]
    while queue:
        rel = queue.pop()
        body = None if rel in found else read(rel)
        if body is not None:
            found[rel] = body
            queue += _SCRIPT_REF.findall(body)
    return found


def unlisted_env_readers(scripts: dict[str, str], listed=ENV_READERS) -> list[str]:
    return sorted(rel for rel, body in scripts.items() if _ENV_READ.search(body) and rel not in listed)


def _read_script(rel: str) -> str | None:
    path = _ROOT / rel
    return code_text(path) if path.is_file() else None


def test_d3b_no_reachable_script_reads_the_commit_under_test_from_the_environment_unlisted(workflows) -> None:
    scripts = reachable_scripts(_scope_texts(workflows), _read_script)
    assert len(scripts) >= 40, f"the walk reached only {len(scripts)} scripts"
    assert "scripts/lib/git-scope.sh" in scripts and "pipeline-scripts/check-pre-commit-hook-pr.sh" in scripts
    assert unlisted_env_readers(scripts) == []


def test_d3b_every_listed_reader_is_still_reached_and_still_reads(workflows) -> None:
    scripts = reachable_scripts(_scope_texts(workflows), _read_script)
    stale = sorted(rel for rel in ENV_READERS if rel not in scripts or not _ENV_READ.search(scripts[rel]))
    assert stale == [], f"listed readers that no longer read the environment or are no longer reached: {stale}"


def test_d3b_the_shared_scope_scripts_default_to_the_checkout_never_to_github_sha(workflows) -> None:
    shared = (
        "scripts/lib/git-scope.sh",
        "pipeline-scripts/check-pre-commit-hook-pr.sh",
        "pipeline-scripts/check_baseline_no_growth.sh",
    )
    for rel in shared:
        body = _read_script(rel)
        assert "GITHUB_SHA" not in body, f"{rel} takes the commit under test from GITHUB_SHA (the branch head here)"
        assert ":-HEAD}" in body, rel


def test_d3b_control_a_script_defaulting_to_github_sha_is_flagged_and_a_walk_follows_sources() -> None:
    files = {
        "scripts/a.sh": "source scripts/lib/b.sh\nrun pipeline-scripts/c.py\n",
        "scripts/lib/b.sh": 'HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"\n',
        "pipeline-scripts/c.py": "import os\nos.environ['GITHUB_EVENT_PATH']\n",
    }
    scripts = reachable_scripts({"w.yml": "run: bash ./scripts/a.sh"}, files.get)
    assert sorted(scripts) == sorted(files)
    assert unlisted_env_readers(scripts) == ["pipeline-scripts/c.py", "scripts/lib/b.sh"]
    assert unlisted_env_readers(scripts, listed={"scripts/lib/b.sh": "x", "pipeline-scripts/c.py": "y"}) == []


# ----- D4: the refusals -----


def _changes_steps(workflows: dict) -> list[dict]:
    return workflows["ci.yml"]["jobs"]["changes"]["steps"]


def _step(steps: list[dict], **match: str) -> dict:
    return next(s for s in steps if all(s.get(k) == v for k, v in match.items()))


def test_d4_the_resolver_runs_before_the_hold_and_a_held_dispatch_fails_the_job(workflows) -> None:
    steps = _changes_steps(workflows)
    resolve, hold = _step(steps, id="pr"), _step(steps, id="hold")
    refuse = _step(steps, name="Refuse a held dispatch")
    assert resolve["if"] == "github.event_name == 'workflow_dispatch'"
    assert resolve["run"].strip() == f"python3 {_RESOLVER}"
    assert steps.index(resolve) < steps.index(hold) < steps.index(refuse)
    assert refuse["if"] == "github.event_name == 'workflow_dispatch' && steps.hold.outputs.held == 'true'"
    assert refuse["run"].rstrip().endswith("exit 1")
    trees = [s for s in steps if s.get("uses", "").startswith("actions/checkout") and "ref" in s.get("with", {})]
    assert steps.index(refuse) < steps.index(trees[0]), "the tree is checked out only after a held dispatch is refused"


def test_d4_the_hold_stays_the_one_definition_and_judges_a_dispatch_as_its_pull_request(workflows) -> None:
    env = _step(_changes_steps(workflows), id="hold")["env"]
    assert "'workflow_dispatch' && 'pull_request'" in env["EVENT"]
    for key in ("AUTHOR", "HEAD_REF", "HEAD_REPO", "BASE_REF", "LABELS"):
        assert "steps.pr.outputs." in env[key], f"{key} has no dispatch fallback"
    assert "dependabot" not in _step(_changes_steps(workflows), id="pr")["run"], "a second definition of the hold"


def test_d4_the_changes_job_may_read_the_pull_request_and_exports_the_merge_ref(workflows) -> None:
    changes = workflows["ci.yml"]["jobs"]["changes"]
    assert changes["permissions"] == {"contents": "read", "packages": "read", "pull-requests": "read"}
    assert changes["outputs"]["checkout_ref"] == "${{ steps.pr.outputs.checkout_ref }}"
    assert workflows["ci.yml"]["permissions"].get("pull-requests") is None, "keep the wider read on the one job"


def test_d4_all_three_publishers_run_the_one_resolver_with_values_taken_only_through_env(workflows) -> None:
    for fname in sorted(PUBLISHERS):
        jobs = workflows[fname]["jobs"]
        steps = [s for spec in jobs.values() for s in spec.get("steps", []) if s.get("id") == "pr"]
        assert len(steps) == 1, fname
        step = steps[0]
        assert step["run"].strip() == f"python3 {_RESOLVER}" and "${{" not in step["run"], fname
        assert step["if"] == "github.event_name == 'workflow_dispatch'"
        assert set(step["env"]) == {"GITHUB_TOKEN", "REPO", "REF_NAME", "REF_TYPE", "SHA", "DEFAULT_BRANCH"}, fname


def test_d4_the_resolver_is_fetched_with_the_shared_client_it_imports(workflows) -> None:
    wanted = {f"pipeline-scripts/{name}.py" for name in ("dispatched_pr", "github_api", "header_safe_secret")}
    for fname in sorted(PUBLISHERS):
        fetches = [
            s
            for spec in workflows[fname]["jobs"].values()
            for s in spec.get("steps", [])
            if s.get("name") == "Fetch the dispatch resolver"
        ]
        assert len(fetches) == 1, fname
        assert set(fetches[0]["with"]["sparse-checkout"].split()) == wanted, fname


def test_d4_a_dispatch_never_cancels_and_never_joins_a_pull_request_group(workflows) -> None:
    ci = workflows["ci.yml"]
    group = ci["concurrency"]["group"]
    assert "github.event_name == 'workflow_dispatch' && github.sha" in group, group
    assert ci["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    shard_group = ci["jobs"]["python-shard"]["concurrency"]["group"]
    assert "github.event_name == 'workflow_dispatch'" in shard_group, "the shards queue like a pull request's"
    for fname in ("no-commit-trailers.yml", "pr-blocking-findings.yml"):
        assert workflows[fname]["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


# ----- D5: every checkout of the tree takes the test merge commit -----


def checkouts_without_ref(jobs: dict, fragment: str) -> list[str]:
    """`job: step` for each full checkout that does not pass `ref` containing *fragment*."""
    bad = []
    for job_id, spec in jobs.items():
        for step in spec.get("steps", []):
            if not str(step.get("uses", "")).startswith("actions/checkout"):
                continue
            with_ = step.get("with") or {}
            if "sparse-checkout" not in with_ and fragment not in str(with_.get("ref", "")):
                bad.append(f"{job_id}: {step.get('name', step['uses'])}")
    return bad


def test_d5_ci_jobs_that_read_the_tree_check_out_the_test_merge(workflows) -> None:
    jobs = workflows["ci.yml"]["jobs"]
    scoped = {k: jobs[k] for k in ("changes", "short-check", "provision-packages", "python-shard", "frontend-tests")}
    assert checkouts_without_ref(scoped, "checkout_ref") == []
    assert "deployment-check" not in scoped, "deployment-check runs on push only and keeps its own checkout"


def test_d5_every_gate_body_takes_the_input_and_checks_out_with_it(workflows) -> None:
    gates = sorted(_gate_files(workflows))
    assert len(gates) == 8, gates
    for fname in gates:
        doc = workflows[fname]
        declared = _on(doc)["workflow_call"]["inputs"]["checkout_ref"]
        assert declared["default"] == "" and declared["type"] == "string" and not declared["required"], fname
        assert checkouts_without_ref(doc["jobs"], "inputs.checkout_ref") == [], fname


def test_d5_every_required_work_job_passes_the_merge_commit_down(workflows) -> None:
    jobs = workflows["ci.yml"]["jobs"]
    called = [w for _, works, _ in GATES.values() for w in works if "uses" in jobs[w]]
    assert len(called) == 8, called
    for work in called:
        assert jobs[work]["with"]["checkout_ref"] == "${{ needs.changes.outputs.checkout_ref }}", work


def test_d5_control_a_checkout_without_the_ref_is_flagged() -> None:
    sparse = {"uses": "actions/checkout@v7", "with": {"sparse-checkout": "x"}}
    jobs = {"a": {"steps": [{"uses": "actions/checkout@v7"}]}, "b": {"steps": [sparse]}}
    assert checkouts_without_ref(jobs, "checkout_ref") == ["a: actions/checkout@v7"]


# ----- D6: the documented path -----


def test_d6_the_sync_comment_documents_the_dispatch_and_no_longer_claims_every_pr_uses_a_train() -> None:
    text = (_WORKFLOWS / "sync-branches-with-main.yml").read_text(encoding="utf-8")
    assert "Every PR lands through a train" not in text
    for command in ("ci.yml", "no-commit-trailers.yml", "pr-blocking-findings.yml"):
        assert f"gh workflow run {command} --ref <branch>" in text
    assert "pipeline-scripts/dispatched_pr.py" in text


def test_d6_the_developer_doc_names_the_dispatch() -> None:
    text = (_ROOT / "docs" / "developer" / "CLAUDE_GIT.md").read_text(encoding="utf-8")
    assert "gh workflow run ci.yml --ref <branch>" in text and "#21577" in text
