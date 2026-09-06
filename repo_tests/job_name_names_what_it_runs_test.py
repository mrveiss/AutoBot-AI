# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A job that accuses one mechanism must run only that mechanism (#15887).

`pr-issue-validation.yml` declared one job named **"Check PR links to its
issue"** and hung a second, unrelated verification off it -- the same-scope
batching gate. A batching failure then reported under the linkage check's name,
and the log said both things eight lines apart::

    PR correctly links to issue 15879
    ...
    ##[error]Process completed with exit code 1.

A wrong name that *accuses a specific, verifiable mechanism* costs more than a
vague one. The reader checks that mechanism, finds it fine, and concludes the
gate is flaky -- so the false lead is confidently labelled and the real failure
is never looked for. Three sessions debugged this separately before the cause
was traced once. A job called `api-wiring` running four steps misleads nobody;
it names a scope, not a verdict.

Hence the population: names of the form "Check/Validate/Verify <something>".
Those assert a result about a named thing, so they must have exactly one thing
that can produce it.

## Why not the broader rule

"Any job whose name describes fewer steps than it runs" was measured before it
was rejected, rather than argued about: 55 jobs run 2+ `run:` steps, and
matching a job's name against its own steps' names flags 9 of them -- every one
a job with no explicit ``name:`` at all, where GitHub falls back to the job id.
`api-wiring`, `code-quality`, `release`. All false positives, because a scope
id is not a claim. Shipping that version would have taught readers to ignore
the guard, which is worse than not having it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"

#: A name that asserts a verdict about one named thing, rather than naming a scope.
_ACCUSES = re.compile(r"^(Check|Validate|Verify|Assert)\s+\S")

#: Below this the guard is not measuring the tree, it is measuring its own reach.
#: Three such jobs exist today; a floor of 2 fails loudly if a rename or a path
#: change empties the population, instead of reporting a clean tree it never read.
_MIN_ACCUSING_JOBS = 2


def _jobs():
    """Yield `(workflow, job_id, job_name, run_step_names)` for every parsed job."""
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # a malformed workflow is another guard's job
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
            continue
        for job_id, job in doc["jobs"].items():
            if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
                continue
            runs = [s.get("name") or "<unnamed>" for s in job["steps"] if isinstance(s, dict) and "run" in s]
            yield path.name, job_id, job.get("name"), runs


def _accusing_jobs():
    return [j for j in _jobs() if j[2] and _ACCUSES.match(str(j[2]))]


def test_the_guard_reaches_the_jobs_it_claims_to_check() -> None:
    """Positive assertion first: prove the population exists before judging it.

    Every could-not-fail test found in this repo has been a negative assertion
    that ran before the thing which would have falsified it. `_WORKFLOWS`
    pointing at nothing, or PyYAML failing on every file, would make the check
    below pass over an empty list and report the tree clean.
    """
    assert _WORKFLOWS.is_dir(), f"{_WORKFLOWS} is not a directory — the sweep read nothing"
    total = sum(1 for _ in _jobs())
    assert total > 50, f"only {total} jobs parsed; the workflow tree was not read"
    accusing = _accusing_jobs()
    assert len(accusing) >= _MIN_ACCUSING_JOBS, (
        f"only {len(accusing)} job(s) named 'Check/Validate/Verify <x>' were found "
        f"(floor {_MIN_ACCUSING_JOBS}) — the rule below would pass by reaching nothing"
    )


def test_a_job_that_accuses_one_mechanism_runs_only_one() -> None:
    """The rule. A verdict-shaped name must have exactly one thing that can produce it."""
    offenders = [(w, jid, name, runs) for w, jid, name, runs in _accusing_jobs() if len(runs) > 1]
    assert not offenders, "\n".join(
        [
            "a job whose name asserts one specific check runs several, so a failure in any of "
            "them is reported under the name of a check that may have passed (#15887):",
            *(
                f"  {w}::{jid}  {name!r} runs {len(runs)} steps: {', '.join(runs)}\n"
                f"      → split the extra step(s) into their own job, named for what they verify"
                for w, jid, name, runs in offenders
            ),
        ]
    )
