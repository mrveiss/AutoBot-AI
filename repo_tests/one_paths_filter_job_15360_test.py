# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One change-detection job per pull request (#15360, #18208).

#15360 moved sixteen byte-similar `changes` jobs into one reusable workflow. #18208 went the
rest of the way: ci.yml has ONE `changes` job, with one `dorny/paths-filter` step per filter
file in `.github/filters/`, and every gate reads its answer. A second dorny step anywhere
else -- or a second `changes` job, or a call to a reusable `changes` workflow -- is the fork
coming back: the pin, the merge-group `base` handling (#14054, #18191) and the checkout would
again be edited in some places and not others, and a pull request would again pay for several
runners to compute the same diff.

The detector reads the parsed workflow, so a comment or a string that merely names the action
is not a step.
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
_DORNY = "dorny/paths-filter"
_REMOVED_REUSABLE = "_changes.yml"

#: Workflow file name -> why it runs dorny. Shrink-only, and one entry by design (#18208): the
#: single `changes` job of ci.yml. Add an entry only with a reason ci.yml's job cannot serve.
_ALLOWED: dict[str, str] = {
    "ci.yml": "the ONE `changes` job: one dorny step per .github/filters/ file, outputs named `run_<gate>`",
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


def _calls_removed_reusable(parsed: object) -> bool:
    jobs = parsed.get("jobs") if isinstance(parsed, dict) else None
    return any(
        isinstance(j, dict) and str(j.get("uses", "")).endswith(f"/{_REMOVED_REUSABLE}") for j in (jobs or {}).values()
    )


def offenders(texts: dict[str, str], allowed: dict[str, str] = _ALLOWED) -> list[str]:
    """Workflow names with a dorny step that is not on the allow-list."""
    return sorted(name for name, text in texts.items() if name not in allowed and _dorny_steps(yaml.safe_load(text)))


@functools.lru_cache(maxsize=1)
def _texts() -> dict[str, str]:
    root = repo_root()
    return {Path(rel).name: (root / rel).read_text(encoding="utf-8") for rel in REACH.examined(root)}


_INLINE = (
    "name: x\non: push\njobs:\n  changes:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - uses: dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d\n"
    "        id: filter\n        with:\n          filters: .github/filters/python-paths.yml\n"
)
_COMMENT_ONLY = "name: x\non: push\n# dorny/paths-filter is mentioned here\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n"


def test_an_inline_dorny_step_trips_the_detector() -> None:
    assert offenders({"zz-new-gate.yml": _INLINE}) == ["zz-new-gate.yml"]


def test_a_workflow_that_only_names_the_action_in_a_comment_passes() -> None:
    assert offenders({"zz-new-gate.yml": _COMMENT_ONLY}) == []


def test_an_allow_listed_workflow_is_exempt_and_nothing_else_is() -> None:
    assert offenders({"ci.yml": _INLINE}) == []
    assert offenders({"ci.yml": _INLINE, "zz.yml": _INLINE}) == ["zz.yml"]


def test_the_scan_is_not_vacuous() -> None:
    texts = _texts()
    assert len(texts) >= 50, f"parsed only {len(texts)} workflows"
    assert _dorny_steps(yaml.safe_load(texts["ci.yml"])) >= 7


def test_ci_reads_every_filter_file_exactly_once_in_the_one_changes_job() -> None:
    """Seven steps, one per file, all inside `changes`, with distinct ids and the merge-group base."""
    doc = yaml.safe_load(_texts()["ci.yml"])
    holders = [
        j for j, spec in doc["jobs"].items() if any(_DORNY in str(s.get("uses", "")) for s in spec.get("steps") or [])
    ]
    assert holders == ["changes"], f"dorny runs in {holders}; it must run only in `changes`"
    steps = [s for s in doc["jobs"]["changes"]["steps"] if _DORNY in str(s.get("uses", ""))]
    files = sorted(s["with"]["filters"] for s in steps)
    on_disk = sorted(
        f".github/filters/{p.name}"
        for p in [p for p in (repo_root() / ".github" / "filters").iterdir() if p.suffix == ".yml"]
    )
    assert files == on_disk, f"filter files read {files} != filter files on disk {on_disk}"
    ids = [s["id"] for s in steps]
    assert len(ids) == len(set(ids)), "two dorny steps share an id: their outputs would collide"
    for s in steps:
        assert (
            s["with"]["base"] == "${{ github.event.merge_group.base_sha || '' }}"
        ), f"step {s['id']} lacks the merge_group base (#14054, #18191)"


def test_no_workflow_calls_the_removed_reusable_changes_workflow() -> None:
    assert not (repo_root() / _WORKFLOWS / _REMOVED_REUSABLE).exists()
    callers = [n for n, t in _texts().items() if _calls_removed_reusable(yaml.safe_load(t))]
    assert callers == [], f"{callers} call the deleted {_REMOVED_REUSABLE}"


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_every_allow_listed_workflow_still_has_the_step_it_is_excused_for(name: str) -> None:
    """A stale entry would excuse a future copy in that file, silently."""
    assert _dorny_steps(yaml.safe_load(_texts()[name])) >= 1, f"{name} no longer runs dorny; drop its entry"


def test_no_workflow_runs_dorny_outside_ci() -> None:
    bad = offenders(_texts())
    assert not bad, (
        f"#18208: {bad} run dorny/paths-filter themselves. Add a filter file under .github/filters/ and a step "
        "to ci.yml's `changes` job instead, or add an _ALLOWED entry that says why that job cannot serve."
    )
