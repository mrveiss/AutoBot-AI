# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One `dorny/paths-filter` job (#15360).

Sixteen workflows each carried their own checkout + `dorny/paths-filter` + outputs `changes`
job. It now lives once, in `.github/workflows/_changes.yml`, and a workflow calls it with
`uses:` and hands over its filter source. A seventeenth inline copy is the fork coming back:
the pin, the `base` handling for merge groups (#14054) and the checkout would again be
edited in some places and not others.

Three workflows legitimately keep a dorny step of their own, each for a reason the reusable
job cannot express; they are in `_ALLOWED` with the reason. The detector reads the parsed
workflow, so a comment or a string that merely names the action is not a step.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_WORKFLOWS = ".github/workflows"
_REUSABLE = "_changes.yml"
_DORNY = "dorny/paths-filter"

#: Workflow file name -> why it keeps its own dorny step. Shrink-only: add an entry only with
#: a reason the reusable job cannot express, and drop it when the step goes.
_ALLOWED: dict[str, str] = {
    "ci.yml": (
        "its `changes` job runs two filter steps, one per source (`python` from a shared file, "
        "`frontend` inline); the reusable job takes exactly one `filters` source"
    ),
    "codeql.yml": (
        "its `changes` output is the JSON list of matched filters (`steps.filter.outputs.changes`) "
        "fed to fromJSON, and the job carries its own `pull-requests: read` permission"
    ),
    "enforce-precommit.yml": (
        "a STEP inside the required `verify-precommit-config` job (#15299), not a job of its own; "
        "moving it into a called job would change which steps the required context runs"
    ),
}


def _workflow_population(root: Path) -> list[str]:
    """Every tracked workflow file: the scan's whole input."""
    try:
        tracked = tracked_paths(root, _WORKFLOWS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith((".yml", ".yaml"))]


REACH = declare(
    "paths-filter-workflow-sweep",
    discover=_workflow_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=63,
    what="tracked workflow files",
    roots=(_WORKFLOWS,),
    growth=10,
)


def _dorny_steps(parsed: object) -> int:
    """How many steps of a parsed workflow run dorny/paths-filter."""
    jobs = parsed.get("jobs") if isinstance(parsed, dict) else None
    count = 0
    for job in (jobs or {}).values():
        steps = job.get("steps") if isinstance(job, dict) else None
        count += sum(1 for s in steps or [] if isinstance(s, dict) and _DORNY in str(s.get("uses", "")))
    return count


def _calls_reusable(parsed: object) -> bool:
    jobs = parsed.get("jobs") if isinstance(parsed, dict) else None
    return any(isinstance(j, dict) and str(j.get("uses", "")).endswith(f"/{_REUSABLE}") for j in (jobs or {}).values())


def offenders(texts: dict[str, str], allowed: dict[str, str] = _ALLOWED) -> list[str]:
    """Workflow names with a dorny step that is neither `_changes.yml` nor allow-listed."""
    return sorted(
        name
        for name, text in texts.items()
        if name != _REUSABLE and name not in allowed and _dorny_steps(yaml.safe_load(text))
    )


@functools.lru_cache(maxsize=1)
def _texts() -> dict[str, str]:
    root = repo_root()
    return {Path(rel).name: (root / rel).read_text(encoding="utf-8") for rel in REACH.examined(root)}


_INLINE = (
    "name: x\non: push\njobs:\n  changes:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - uses: dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d\n"
    "        id: filter\n        with:\n          filters: .github/filters/python-paths.yml\n"
)
_CALL = (
    "name: x\non: push\njobs:\n  changes:\n    uses: ./.github/workflows/_changes.yml\n"
    "    with:\n      filters: .github/filters/python-paths.yml\n"
)
_COMMENT_ONLY = "name: x\non: push\n# dorny/paths-filter is mentioned here\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n"


def test_an_inline_dorny_step_trips_the_detector() -> None:
    assert offenders({"zz-new-gate.yml": _INLINE}) == ["zz-new-gate.yml"]


def test_a_job_calling_the_reusable_workflow_passes() -> None:
    assert offenders({"zz-new-gate.yml": _CALL}) == []


def test_a_workflow_that_only_names_the_action_in_a_comment_passes() -> None:
    assert offenders({"zz-new-gate.yml": _COMMENT_ONLY}) == []


def test_an_allow_listed_workflow_is_exempt_and_nothing_else_is() -> None:
    assert offenders({"ci.yml": _INLINE}) == []
    assert offenders({"ci.yml": _INLINE, "zz.yml": _INLINE}) == ["zz.yml"]


def test_the_reusable_workflow_itself_is_where_the_step_lives() -> None:
    assert offenders({_REUSABLE: _INLINE}) == []


def test_the_scan_is_not_vacuous() -> None:
    texts = _texts()
    assert _REUSABLE in texts and _dorny_steps(yaml.safe_load(texts[_REUSABLE])) == 1
    callers = [n for n, t in texts.items() if _calls_reusable(yaml.safe_load(t))]
    assert len(callers) >= 16, f"only {len(callers)} workflows call {_REUSABLE}"
    assert len(texts) >= 50, f"parsed only {len(texts)} workflows"


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_every_allow_listed_workflow_still_has_the_step_it_is_excused_for(name: str) -> None:
    """A stale entry would excuse a future copy in that file, silently."""
    assert _dorny_steps(yaml.safe_load(_texts()[name])) >= 1, f"{name} no longer runs dorny; drop its entry"


def test_no_workflow_runs_dorny_outside_the_reusable_job() -> None:
    bad = offenders(_texts())
    assert not bad, (
        f"#15360: {bad} run dorny/paths-filter themselves. Call ./.github/workflows/{_REUSABLE} with "
        "`filters:` instead, or add an _ALLOWED entry that says why the reusable job cannot serve."
    )
