# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Branch-reporting sweeps must test landing, not ancestry (#15036).

This repository squash-merges. A squash merge writes a commit on the base that
is not a descendant of the branch's commits, so
``git merge-base --is-ancestor <branch> <base>`` and ``git branch --merged`` are
false for every branch the repository has ever merged. Any sweep that uses
either as its landed/unlanded test reports a false positive for all of them.

That is not hypothetical: #11703 named five "stale" branches and all five had
landed; #13603 claimed three branches held ~1760 unlanded insertions and 16 of
18 files were byte-identical to base; #4324 did the same in April. Each closed
with no action because there was none to take, and a detector with a ~100%
false-positive rate trains its readers to ignore the report that is finally
right.

The replacement lives in ``scripts/lib/branch-guards.sh`` as
``branch_landing_evidence``: a merged PR whose head ref is the branch, or a
commit on base carrying the branch's ``(#issue)``, or nothing added at all.
Everything else is reported as unproven WITH its per-file numbers attached.

WHY THIS STRIPS COMMENTS FIRST. Both workflows now carry header prose naming the
forbidden commands in order to explain why they are forbidden. A guard reading
raw text would match that prose and fail on the very lines documenting the
correct behaviour. Only executable shell is examined.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO_ROOT / ".github/workflows"
_GUARD_LIB = _REPO_ROOT / "scripts/lib/branch-guards.sh"

#: The sweeps that classify branches as stale or merged and report the result.
#: A new one belongs here; otherwise it can reintroduce the ancestry test
#: unobserved.
_REPORTING_SWEEPS = ("stale-branches-warning.yml", "branch-health-report.yml")

#: Ancestry masquerading as a landed/unlanded test.
_ANCESTRY = (
    re.compile(r"--is-ancestor\b"),
    re.compile(r"\bgit\s+branch\b[^\n|]*\s--merged\b"),
    re.compile(r"\bgit\s+branch\b[^\n|]*\s--no-merged\b"),
)

#: Ancestry is forbidden as a landed/unlanded *test*. It is still legitimate as
#: a deletion NARROWER, where a false negative merely spares a branch: that is
#: the direction ``branch-cleanup.yml`` uses it in, deliberately, since #10035.
#: The safety of that use rests entirely on which direction the error falls, so
#: the exemption is named with its reason rather than inferred.
_ANCESTRY_ALLOWED = {
    "branch-cleanup.yml": (
        "narrows the DELETION candidate set; a squash-merged branch it misses is "
        "simply not deleted, which is the safe direction (#10035)"
    ),
}

#: Every workflow file must be scanned; these are the floors that make an empty
#: sweep fail loudly instead of reporting clean. Chosen well below the current
#: counts so ordinary additions never trip them.
_MIN_WORKFLOWS_SCANNED = 20
_MIN_SHELL_BODIES = 2


def _shell_bodies(path: Path) -> list[str]:
    """Every ``run:`` script in a workflow, with shell comments removed."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        return []
    bodies: list[str] = []
    for job in (spec.get("jobs") or {}).values():
        for step in job.get("steps", []) if isinstance(job, dict) else []:
            run = step.get("run") if isinstance(step, dict) else None
            if not isinstance(run, str):
                continue
            bodies.append(
                "\n".join(
                    line for line in run.splitlines() if not line.lstrip().startswith("#")
                )
            )
    return bodies


def _ancestry_hits(path: Path) -> list[str]:
    """Every ancestry test in this workflow's executable shell."""
    hits: list[str] = []
    for body in _shell_bodies(path):
        for line in body.splitlines():
            for pattern in _ANCESTRY:
                match = pattern.search(line)
                if match is not None:
                    hits.append(f"{path.name}: {line.strip()!r} (matched {match.group(0)!r})")
    return hits


def test_reporting_sweeps_exist() -> None:
    """The reach check: every assertion below is vacuous if a sweep moved."""
    missing = [name for name in _REPORTING_SWEEPS if not (_WORKFLOWS / name).is_file()]
    assert not missing, (
        f"reporting sweeps missing from {_WORKFLOWS.relative_to(_REPO_ROOT)}: {missing}. "
        "If one was renamed, update _REPORTING_SWEEPS -- do not delete this guard."
    )


def test_no_workflow_uses_ancestry_as_a_landed_test() -> None:
    """Swept repository-wide, not just over the two known sweeps (#15036).

    The defect is a habit, not a file. A new workflow reaching for
    ``git branch --merged`` would reintroduce it somewhere this guard would
    never look if the sweep were narrowed to the current offenders.
    """
    scanned = 0
    hits: list[str] = []
    for path in sorted(_WORKFLOWS.glob("*.y*ml")):
        scanned += 1
        if path.name in _ANCESTRY_ALLOWED:
            continue
        hits.extend(_ancestry_hits(path))

    assert scanned >= _MIN_WORKFLOWS_SCANNED, (
        f"only {scanned} workflow file(s) scanned, expected at least "
        f"{_MIN_WORKFLOWS_SCANNED} -- the sweep lost reach and is asserting nothing"
    )
    assert not hits, (
        "workflows testing ancestry instead of landing -- this repository "
        "squash-merges, so these are false for every branch it has ever merged "
        "(#15036):\n" + "\n".join(hits)
    )


def test_reporting_sweeps_use_the_shared_landing_evidence() -> None:
    """Each sweep must call ``branch_landing_evidence``, not roll its own test."""
    offenders: list[str] = []
    for name in _REPORTING_SWEEPS:
        joined = "\n".join(_shell_bodies(_WORKFLOWS / name))
        if "scripts/lib/branch-guards.sh" not in joined:
            offenders.append(f"{name}: does not source scripts/lib/branch-guards.sh")
        if "branch_landing_evidence" not in joined:
            offenders.append(f"{name}: never calls branch_landing_evidence")
    assert not offenders, (
        "reporting sweeps not using the shared landing check (#15036):\n"
        + "\n".join(offenders)
    )


def test_reporting_sweeps_have_a_failing_vacuity_floor() -> None:
    """A broken enumeration must fail the job, not publish "0 problems found".

    Both sweeps report a count. Zero is what a healthy repository reports AND
    what an enumeration that scanned nothing reports, and the issue body cannot
    tell them apart -- `stale-branches-warning` goes further and *closes* its
    tracking issue on zero. A ``::warning::`` annotation does not stop any of
    that; only a non-zero exit does, which is why the floor is asserted to be a
    call to ``branch_sweep_assert_reach`` under ``set -e``.
    """
    offenders: list[str] = []
    for name in _REPORTING_SWEEPS:
        bodies = _shell_bodies(_WORKFLOWS / name)
        joined = "\n".join(bodies)
        if "branch_sweep_assert_reach" not in joined:
            offenders.append(f"{name}: no call to branch_sweep_assert_reach")
        if not any("set -euo pipefail" in body or "set -e" in body for body in bodies):
            offenders.append(f"{name}: no `set -e`, so a failing floor would not abort")
    assert not offenders, (
        "reporting sweeps whose vacuity floor cannot fail the job:\n" + "\n".join(offenders)
    )


def test_the_floor_helper_actually_fails() -> None:
    """``branch_sweep_assert_reach`` must return non-zero below the floor.

    Asserted here as well as in the bash suite because the workflows' whole
    protection is this one exit code, and a refactor that made the helper always
    succeed would leave both `set -e` guards above passing while protecting
    nothing.
    """
    text = _GUARD_LIB.read_text(encoding="utf-8")
    assert "branch_sweep_assert_reach()" in text, "the floor helper is gone"
    assert "BRANCH_SWEEP_MIN_ENUMERATED" in text, "the floor constant is gone"
    body = text.split("branch_sweep_assert_reach()", 1)[1].split("\n}", 1)[0]
    assert "return 1" in body, (
        "branch_sweep_assert_reach no longer returns non-zero; under `set -e` "
        "the sweeps would carry on over an enumeration that scanned nothing"
    )


def test_the_guard_actually_reads_shell() -> None:
    """A parse that yields nothing would make every assertion above vacuous."""
    for name in _REPORTING_SWEEPS:
        bodies = _shell_bodies(_WORKFLOWS / name)
        assert len(bodies) >= _MIN_SHELL_BODIES, (
            f"{name}: only {len(bodies)} run: script(s) parsed, expected at least "
            f"{_MIN_SHELL_BODIES} -- the YAML parse broke and this guard inspects nothing"
        )
        joined = "\n".join(bodies)
        assert "refs/remotes/origin/" in joined, (
            f"{name}: no longer enumerates refs/remotes/origin; either it was rewritten "
            "(update this guard deliberately) or the parse broke"
        )
        assert "git branch -r" not in joined, (
            f"{name}: enumerates with `git branch -r`, which spans EVERY configured "
            "remote. Stripping only the `origin/` prefix then leaves another remote's "
            "branch as `<remote>/<branch>`, which the sweep re-prefixes into the "
            "unresolvable `origin/<remote>/<branch>` -- and classifies from the "
            "resulting git failures instead of skipping it."
        )


def test_landing_evidence_helpers_are_defined() -> None:
    """The workflows source this library; a rename would break them at runtime."""
    text = _GUARD_LIB.read_text(encoding="utf-8")
    required = (
        "branch_landing_evidence()",
        "branch_content_presence()",
        "branch_is_archival()",
        "branch_tree_matches_base()",
        "branch_paths_covered_for_issue()",
        "branch_sweep_assert_reach()",
        "merged_pr_for_branch()",
        "base_commit_for_issue()",
    )
    absent = [name for name in required if name not in text]
    assert not absent, (
        f"{_GUARD_LIB.relative_to(_REPO_ROOT)} no longer defines {absent}; the "
        "reporting sweeps source it and would fail at runtime (#15036)"
    )


def test_archival_prefixes_cover_the_known_archives() -> None:
    """``rescued/*`` (#14078) and ``release/changelog-*`` (#15167) hold the only
    copy of work that must never be reported as stranded or swept."""
    text = _GUARD_LIB.read_text(encoding="utf-8")
    for prefix in ("rescued/", "release/changelog-"):
        assert prefix in text, (
            f"{prefix!r} dropped from BRANCH_ARCHIVAL_PREFIXES -- those branches "
            "hold the only copy of rescued (#14078) or released-changelog (#15167) "
            "content and must not be reported as stranded work"
        )


def test_the_ancestry_exemption_still_explains_itself() -> None:
    """An exempt workflow must keep the comment that justifies its exemption.

    The exemption is safe only while the ancestry call narrows a deletion set.
    If that comment is gone, the call has probably been repurposed, and the
    allowlist entry is no longer describing what the file does.
    """
    for name in _ANCESTRY_ALLOWED:
        path = _WORKFLOWS / name
        assert path.is_file(), (
            f"{name} is exempt from the ancestry sweep but no longer exists; "
            "remove its _ANCESTRY_ALLOWED entry"
        )
        text = path.read_text(encoding="utf-8")
        assert "ancestor-based" in text, (
            f"{name} lost the comment explaining why it uses ancestry. The "
            "exemption assumes it narrows a DELETION set (a miss simply spares a "
            "branch). Re-establish that, or drop the exemption (#15036, #10035)."
        )
        assert _ancestry_hits(path), (
            f"{name} no longer uses ancestry at all -- drop its _ANCESTRY_ALLOWED "
            "entry so the repository-wide sweep covers it again"
        )
