# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for every required-context complement split (#14353, and the
`startup-import-smoke` deadlock this file was renamed for).

`python-suite` can only be a required status check if *exactly one* job publishes
it on every pull request: the real twelve-shard suite in ci.yml when Python paths
changed, and the shim in python-required-context.yml when they did not.

The dangerous direction is silent. If the shim believed nothing Python changed
while ci.yml believed otherwise, the pull request would take the shim's green for
a suite that never ran — a gate bypass, not a flake. These tests pin the two
properties that prevent it: the job names match, and both sides read the same
filter file rather than keeping copies that can drift.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SHIM = REPO_ROOT / ".github" / "workflows" / "python-required-context.yml"
FILTER = REPO_ROOT / ".github" / "filters" / "python-paths.yml"

REQUIRED_CONTEXT = "python-suite"


def _jobs(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def test_both_workflows_publish_the_same_context_name():
    """The required context is the job NAME; a rename on one side breaks the split."""
    assert _jobs(CI)[REQUIRED_CONTEXT]["name"] == REQUIRED_CONTEXT
    assert _jobs(SHIM)[REQUIRED_CONTEXT]["name"] == REQUIRED_CONTEXT


def test_the_two_conditions_are_exact_complements():
    """One and only one of them may run for any given pull request."""
    real = _jobs(CI)[REQUIRED_CONTEXT]["if"]
    shim = _jobs(SHIM)[REQUIRED_CONTEXT]["if"]

    assert "needs.changes.outputs.python == 'true'" in real
    assert shim.strip() == "needs.changes.outputs.python != 'true'"


def test_both_sides_read_the_shared_filter_file():
    """A second inline copy of the path set is how the two sides drift apart."""
    assert FILTER.is_file(), f"missing canonical filter: {FILTER}"

    for path in (CI, SHIM):
        text = path.read_text(encoding="utf-8")
        assert ".github/filters/python-paths.yml" in text, f"{path.name} does not read the shared filter"

    # ...and ci.yml resolves the set through that file rather than an inline copy.
    steps = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["changes"]["steps"]
    python_steps = [s for s in steps if s.get("id") == "filter-python"]
    assert len(python_steps) == 1, "ci.yml must resolve `python` through exactly one filter step"
    assert python_steps[0]["with"]["filters"] == ".github/filters/python-paths.yml"


def test_the_filter_covers_its_own_inputs():
    """Editing the filter or the shim must run the real suite, not the shim."""
    patterns = yaml.safe_load(FILTER.read_text(encoding="utf-8"))["python"]

    assert ".github/filters/python-paths.yml" in patterns
    assert ".github/workflows/python-required-context.yml" in patterns
    assert ".github/workflows/ci.yml" in patterns
    assert "**/*.py" in patterns


def test_the_shim_declares_no_concurrency_group():
    """A shared concurrency group is what made the frontend shim useless (#13405).

    Asserted against the parsed document, not the raw text: the file *explains*
    why it has no concurrency block, and a substring check fails on its own
    comment.
    """
    parsed = yaml.safe_load(SHIM.read_text(encoding="utf-8"))
    assert "concurrency" not in parsed
    assert "concurrency" not in parsed["jobs"][REQUIRED_CONTEXT]


def test_the_shim_runs_on_a_github_hosted_runner():
    """The shim must not depend on the singleton self-hosted pool."""
    assert _jobs(SHIM)[REQUIRED_CONTEXT]["runs-on"] == "ubuntu-latest"
    assert _jobs(SHIM)["changes"]["runs-on"] == "ubuntu-latest"


def test_the_shim_fails_closed_on_a_broken_detector():
    """If `changes` errors, the shim must skip rather than report green."""
    shim_job = _jobs(SHIM)[REQUIRED_CONTEXT]
    assert shim_job["needs"] == "changes", "without `needs`, a failed detector would not gate the shim"


# The ten contexts branch protection requires on Dev_new_gui today, plus
# `python-suite`, which #14353 exists to make the eleventh. Branch protection
# lives in the GitHub API and cannot be read offline, so this list is declared
# rather than derived — the test below is what keeps the workflows honest to it.
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
        REQUIRED_CONTEXT,
    }
)

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _triggers(doc: dict) -> dict:
    """Return the workflow's `on:` block.

    YAML 1.1 resolves the bare key ``on`` to the boolean ``True``, so
    ``doc["on"]`` raises and ``doc.get("on", {})`` silently returns nothing —
    which would make every assertion below vacuous while the test still passed.
    """
    return doc.get(True) or doc.get("on") or {}


def _published_context_names(doc: dict) -> set:
    jobs = doc.get("jobs") or {}
    return {(spec or {}).get("name", job_id) for job_id, spec in jobs.items()}


def _workflows_publishing_a_required_context():
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if _published_context_names(doc) & REQUIRED_CONTEXTS:
            yield path, doc


def test_the_scan_actually_finds_workflows():
    """A glob that matched nothing would make the guard below assert nothing."""
    found = list(_workflows_publishing_a_required_context())
    assert len(found) >= 3, (
        f"only {len(found)} workflow(s) matched a required context - the scan is "
        "no longer bound to the workflows it is meant to guard"
    )


@pytest.mark.parametrize(
    "path",
    [pytest.param(p, id=p.name) for p, _ in _workflows_publishing_a_required_context()],
)
def test_a_workflow_publishing_a_required_context_has_no_pull_request_paths(path):
    """A path-filtered required check deadlocks the pull request it gates.

    If the trigger does not match, the workflow never starts, so the context is
    never reported and the pull request waits on "Expected" forever. The
    complement shim cannot rescue it: the shim reads the *filter*, sees the path
    as Python, and skips - so neither side publishes.

    #13388 stated this rule for ci.yml and #14353 had to apply it; frontend-test.yml
    and code-quality.yml each removed their own filter for the same reason.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    pull_request = _triggers(doc).get("pull_request") or {}

    assert "paths" not in pull_request, (
        f"{path.name} publishes a required status context but filters "
        f"pull_request on paths {pull_request['paths']!r}. A pull request that "
        "misses this filter never starts the run, so the context never reports "
        "and the merge box blocks forever."
    )

# Each row is one required status context published by two mutually exclusive
# jobs: the real gate when its paths changed, and a shim reporting green when
# they did not. Adding a third pair is one row here.
#
#   (context, real workflow, real `if:` fragment, shim workflow, shim `if:`, filter)
_COMPLEMENT_PAIRS = (
    (
        "python-suite",
        "ci.yml",
        "needs.changes.outputs.python == 'true'",
        "python-required-context.yml",
        "needs.changes.outputs.python != 'true'",
        "python-paths.yml",
    ),
    (
        "startup-import-smoke",
        "startup-import-smoke.yml",
        "needs.changes.outputs.backend == 'true'",
        "backend-required-context.yml",
        "needs.changes.outputs.backend != 'true'",
        "backend-python-paths.yml",
    ),
    (
        "code-quality",
        "code-quality.yml",
        "needs.changes.outputs.backend == 'true'",
        "code-quality-required-context.yml",
        "needs.changes.outputs.backend != 'true'",
        "code-quality-paths.yml",
    ),
)

_PAIR_IDS = [p[0] for p in _COMPLEMENT_PAIRS]


@pytest.mark.parametrize("pair", _COMPLEMENT_PAIRS, ids=_PAIR_IDS)
def test_the_pair_publishes_one_context_under_two_complementary_conditions(pair):
    """The required context is the job NAME, and exactly one side may run."""
    context, real_wf, real_if, shim_wf, shim_if, _ = pair
    real = _jobs(WORKFLOW_DIR / real_wf)[context]
    shim = _jobs(WORKFLOW_DIR / shim_wf)[context]

    assert real.get("name", context) == context
    assert shim["name"] == context
    assert real_if in real["if"], f"{real_wf}:{context} no longer carries {real_if!r}"
    assert shim["if"].strip() == shim_if


@pytest.mark.parametrize("pair", _COMPLEMENT_PAIRS, ids=_PAIR_IDS)
def test_the_shim_cannot_be_cancelled_or_starved(pair):
    """No shared concurrency group (#13405), and never the self-hosted pool.

    Asserted against the parsed document, not the raw text: each file *explains*
    why it has no concurrency block, and a substring check fails on its own
    comment.
    """
    context, _, _, shim_wf, _, _ = pair
    parsed = yaml.safe_load((WORKFLOW_DIR / shim_wf).read_text(encoding="utf-8"))

    assert "concurrency" not in parsed
    assert "concurrency" not in parsed["jobs"][context]
    assert parsed["jobs"][context]["runs-on"] == "ubuntu-latest"
    assert parsed["jobs"]["changes"]["runs-on"] == "ubuntu-latest"


@pytest.mark.parametrize("pair", _COMPLEMENT_PAIRS, ids=_PAIR_IDS)
def test_the_shim_fails_closed_and_reads_the_shared_filter(pair):
    """A broken detector must block, and neither side may keep its own path copy."""
    context, real_wf, _, shim_wf, _, filter_name = pair
    shim_job = _jobs(WORKFLOW_DIR / shim_wf)[context]
    assert shim_job["needs"] == "changes", "without `needs`, a failed detector would not gate the shim"

    canonical = REPO_ROOT / ".github" / "filters" / filter_name
    assert canonical.is_file(), f"missing canonical filter: {canonical}"
    for wf in (real_wf, shim_wf):
        text = (WORKFLOW_DIR / wf).read_text(encoding="utf-8")
        assert f".github/filters/{filter_name}" in text, f"{wf} does not read the shared filter"


# ── the general catcher ──────────────────────────────────────────────────────
#
# The pairs above are pinned by name, but detection must NOT depend on that
# table: a context missing from it is exactly the case that needs catching. This
# resolves the property structurally instead — a required context is safe when
# some job publishing it is unconditional, or when two of them carry conditions
# that are exact complements.
#
# `startup-import-smoke` is why this exists. Its workflow correctly carries no
# `pull_request.paths` filter, so the older test above passed — but its single
# job was gated on `needs.changes.outputs.backend == 'true'` with no complement,
# and its own header claimed the job "self-skips (reporting success) when no
# backend paths are touched". A job whose `if:` is false is SKIPPED, and a
# skipped job publishes a check run whose conclusion is `skipped`, not `success`.
# A pull request touching only `scripts/` and `.dockerignore` therefore sat
# blocked on a required context nothing could turn green (#15606).
#
# The two failure directions are not symmetric. A missing complement BLOCKS,
# loudly and immediately. A complement whose condition is not an exact negation
# reports green for a gate that never ran, which is a silent bypass — so the
# string-level pinning in the parametrized tests matters more than this sweep.

# Shrink-only. A context here is a KNOWN deadlock with an issue against it, not a
# permitted shape: removing the gap must remove the entry, and a stale entry
# fails as loudly as a new unpaired context.
# Empty, and that is the point: #15608 was the last entry, closed by extracting
# code-quality's inline path set to .github/filters/code-quality-paths.yml and
# pairing it with .github/workflows/code-quality-required-context.yml. Every
# required context now has either an unconditional publisher or an exact
# complement, and the structural sweep below is what keeps it that way.
_KNOWN_UNPAIRED: dict[str, str] = {}


def _condition_is_always_true(expression: str) -> bool:
    """`always()` and a bare `true` run unconditionally, so they cannot deadlock."""
    return expression.strip().strip("${} ").lower() in {"always()", "true", "success() || failure()"}


def _negates(left: str, right: str) -> bool:
    """True when two `if:` expressions are exact complements of each other.

    Compared on the `outputs.<name> ==/!= 'true'` clause rather than the whole
    string: the real gate usually also admits `merge_group`, which the shim
    cannot see because `merge_group` is not one of its triggers.
    """
    clause = re.compile(r"needs\.changes\.outputs\.(\w+)\s*(==|!=)\s*'true'")
    left_clauses = {m.group(1): m.group(2) for m in clause.finditer(left)}
    right_clauses = {m.group(1): m.group(2) for m in clause.finditer(right)}
    shared = set(left_clauses) & set(right_clauses)
    return any(left_clauses[name] != right_clauses[name] for name in shared)


def _publishers_of_required_contexts():
    """Map each required context to every `if:` expression publishing it."""
    found = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, spec in (doc.get("jobs") or {}).items():
            spec = spec or {}
            context = spec.get("name", job_id)
            if context in REQUIRED_CONTEXTS:
                found.setdefault(context, []).append((path.name, str(spec.get("if") or "")))
    return found


def test_the_publisher_sweep_finds_every_required_context():
    """A sweep that resolved nothing would make the guard below assert nothing."""
    found = _publishers_of_required_contexts()
    missing = sorted(REQUIRED_CONTEXTS - set(found))
    assert not missing, f"no workflow publishes these required contexts at all: {missing}"


def test_every_required_context_can_report_success_on_any_pull_request():
    """A required context nothing can turn green deadlocks the pull request."""
    unpaired = []
    for context, publishers in sorted(_publishers_of_required_contexts().items()):
        conditions = [expr for _, expr in publishers]
        if any(not expr or _condition_is_always_true(expr) for expr in conditions):
            continue
        if any(_negates(a, b) for i, a in enumerate(conditions) for b in conditions[i + 1 :]):
            continue
        where = ", ".join(sorted({name for name, _ in publishers}))
        unpaired.append((context, where))

    unexpected = [f"{c} (in {w})" for c, w in unpaired if c not in _KNOWN_UNPAIRED]
    assert not unexpected, (
        "these required contexts are published only by conditional jobs with no "
        "complement. When the condition is false the job is SKIPPED, which is "
        "not SUCCESS, so the pull request blocks on a context nothing can "
        "produce (#15606):\n  " + "\n  ".join(unexpected)
    )

    fixed = sorted(set(_KNOWN_UNPAIRED) - {c for c, _ in unpaired})
    assert not fixed, (
        "these contexts now have a complement but are still listed in "
        "_KNOWN_UNPAIRED — remove them, a stale entry hides the next real one:\n  "
        + "\n  ".join(fixed)
    )
