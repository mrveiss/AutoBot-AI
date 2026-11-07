# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A job that judges a draft-gated job must be draft-gated too (#17957, #17975).

#17957 gated the expensive jobs on `draft == false` so a draft PR stops burning
the runner queue. `python-suite` is not a matrix job, so nothing gated it by
inheritance -- and it re-asserts its shards' verdict:

    - name: Fail if any shard failed
      if: ${{ needs.python-shard.result != 'success' }}

For a matrix, `result` is the aggregate across all twelve shards, and twelve
skipped shards aggregate to `skipped`, which satisfies `!= 'success'`. So every
draft PR reported a red `python-suite` for shards that were deliberately not
run. The job's own comment shows the authors had already foreseen skipped
shards and guarded the *path-filter* cause; the draft gate added a second cause
to a condition written for one.

The invariant is narrow on purpose. It is not "every dependent of a gated job
must be gated" -- plenty of jobs legitimately run alongside a skipped one. It
is: **if you re-assert a dependency's `result`, you inherit the conditions
under which that dependency does not run.**
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

WORKFLOWS = repo_root() / ".github" / "workflows"

#: The gate as it is actually written. Matched on the parsed condition, never on
#: file text -- a comment quoting the expression (this file is full of them)
#: must not count as a gate (#17941).
_DRAFT_GATE = re.compile(r"github\.event\.pull_request\.draft\s*==\s*false")

#: `needs.<job>.result` compared against anything. The comparison direction does
#: not matter: `!= 'success'` fails on a skip, `== 'failure'` does not, but both
#: mean this job reads a verdict it can only interpret if the dependency ran.
_READS_RESULT = re.compile(r"needs\.([A-Za-z0-9_-]+)\.result")


def _is_gated(condition: object) -> bool:
    return bool(_DRAFT_GATE.search(str(condition or "")))


#: A condition that names `skipped` has considered the case. `deployment-check`
#: reads `python-suite.result` and accepts `success || skipped`, so a skipped
#: dependency is a state it handles rather than a verdict it misreads. Flagging
#: it would be a false positive, and a guard with false positives gets muted --
#: which costs more than the one it would have caught.
_TOLERATES_SKIP = re.compile(r"'skipped'|\"skipped\"")


def _intolerant_result_reads(job: dict) -> set[str]:
    """Jobs whose `result` this job reads in a condition that does NOT allow `skipped`.

    Scoped per condition, not per job: a job may read one dependency tolerantly
    and another strictly, and only the strict read is a defect. Checking the
    job as a whole would let one tolerant condition excuse an intolerant one.
    """
    sources = [job.get("if", "")]
    sources += [step.get("if", "") for step in job.get("steps", []) or [] if isinstance(step, dict)]
    found: set[str] = set()
    for source in sources:
        text = str(source or "")
        if _TOLERATES_SKIP.search(text):
            continue
        found.update(_READS_RESULT.findall(text))
    return found


def _workflows() -> list[Path]:
    found = sorted(p for p in WORKFLOWS.glob("*.yml"))
    # Non-vacuity: an empty sweep satisfies the assertion below by looking at
    # nothing. MEASUREMENT_DISCIPLINE.md -- "nothing found" and "did not look"
    # must not read alike.
    assert len(found) > 40, f"only {len(found)} workflows found -- the glob or the path is wrong"
    return found


def _offenders(workflow: dict) -> list[str]:
    """(judge, dependency) pairs where the judge is ungated and the dep is gated."""
    jobs = workflow.get("jobs") or {}
    bad = []
    for name, job in jobs.items():
        if not isinstance(job, dict) or _is_gated(job.get("if")):
            continue
        for dep in _intolerant_result_reads(job):
            target = jobs.get(dep)
            if isinstance(target, dict) and _is_gated(target.get("if")):
                bad.append(f"{name} reads {dep}.result")
    return bad


def test_a_job_that_judges_a_draft_gated_job_is_itself_draft_gated() -> None:
    """The invariant. `python-suite` against `python-shard` is the instance."""
    offenders: list[str] = []
    for path in _workflows():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # a malformed workflow is another guard's problem
            continue
        if isinstance(loaded, dict):
            offenders += [f"{path.name}: {entry}" for entry in _offenders(loaded)]

    assert not offenders, (
        "a job reads the `result` of a draft-gated job but is not draft-gated itself:\n  "
        + "\n  ".join(offenders)
        + "\n\nOn a draft the dependency is skipped, and a verdict step that treats "
        "anything other than 'success' as a failure reports red for work that was "
        "deliberately not run. Mirror the dependency's draft condition (#17957)."
    )


_GATE = "github.event_name != 'pull_request' || github.event.pull_request.draft == false"

#: The shape the defect took: judge ungated, dependency gated.
_UNGATED_JUDGE = {
    "jobs": {
        "shard": {"if": f"${{{{ ({_GATE}) }}}}", "steps": []},
        "suite": {"if": "${{ !cancelled() }}", "steps": [{"if": "${{ needs.shard.result != 'success' }}"}]},
    }
}
#: The same pair, fixed.
_GATED_JUDGE = {
    "jobs": {
        "shard": {"if": f"${{{{ ({_GATE}) }}}}", "steps": []},
        "suite": {
            "if": f"${{{{ !cancelled() && ({_GATE}) }}}}",
            "steps": [{"if": "${{ needs.shard.result != 'success' }}"}],
        },
    }
}
#: Neither gated -- not this guard's business, and flagging it would make the
#: guard fire on most of the tree.
_NEITHER_GATED = {
    "jobs": {
        "shard": {"if": "${{ true }}", "steps": []},
        "suite": {"if": "${{ !cancelled() }}", "steps": [{"if": "${{ needs.shard.result != 'success' }}"}]},
    }
}
#: Gated dependency, but the judge never reads its result -- it merely runs
#: after it. Gating that would be the over-broad rule this guard refuses.
_NO_RESULT_READ = {
    "jobs": {
        "shard": {"if": f"${{{{ ({_GATE}) }}}}", "steps": []},
        "suite": {"if": "${{ !cancelled() }}", "needs": ["shard"], "steps": [{"run": "echo hi"}]},
    }
}
#: The gate named only in a comment-like string value. The detector reads the
#: parsed condition, so prose must not satisfy it (#17941).
_PROSE_ONLY_GATE = {
    "jobs": {
        "shard": {"if": f"${{{{ ({_GATE}) }}}}", "steps": []},
        "suite": {
            "if": "${{ !cancelled() }}",
            "name": f"skipped when {_GATE}",
            "steps": [{"if": "${{ needs.shard.result != 'success' }}"}],
        },
    }
}


#: Reads a gated dependency's result but explicitly allows `skipped`. This is
#: `deployment-check`, and it is correct -- the real tree's control.
_TOLERATES_SKIPPED = {
    "jobs": {
        "shard": {"if": f"${{{{ ({_GATE}) }}}}", "steps": []},
        "suite": {
            "if": "${{ needs.shard.result == 'success' || needs.shard.result == 'skipped' }}",
            "steps": [],
        },
    }
}


@pytest.mark.parametrize(
    "label,workflow,expected",
    [
        ("an ungated judge of a gated dependency", _UNGATED_JUDGE, 1),
        ("the same pair with the judge gated", _GATED_JUDGE, 0),
        ("neither gated", _NEITHER_GATED, 0),
        ("a gated dependency whose result is never read", _NO_RESULT_READ, 0),
        ("the gate present only as prose in a name", _PROSE_ONLY_GATE, 1),
        ("a judge that explicitly allows a skipped dependency", _TOLERATES_SKIPPED, 0),
    ],
)
def test_the_detector_separates_the_shapes(label: str, workflow: dict, expected: int) -> None:
    """The contrast set. Without it, `return []` passes the sweep above.

    The prose case is the one worth keeping: this very file spells the gate
    expression repeatedly in comments and fixtures, so a text scan over the
    tree would find it everywhere and report clean.
    """
    found = _offenders(workflow)
    assert len(found) == expected, f"with {label}, the detector reported {found}, expected {expected} offender(s)"
