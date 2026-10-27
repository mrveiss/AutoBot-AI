# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow and job names a person sees say "Company OS", never "LLC" (#19546).

Owner rule: **Company OS** is the feature's name in everything a person sees;
``llc`` stays the internal code name for packages, routes, symbols and the
``LLC_*`` env vars. The contract gate shipped with an ``llc-`` file name,
``name: LLC Contract Gate`` and jobs ``llc-wiring-audit`` / ``llc-e2e``, so the
internal name was what every pull request's checks list and the Actions tab
showed. #19546 renamed them; this guard keeps it that way for every workflow.

What a person sees, and therefore what is checked:

* the workflow file name (the Actions tab lists it when ``name:`` is absent);
* the workflow ``name:``;
* each job's display name -- its ``name:`` if set, else its job id, which is
  exactly the fallback GitHub uses for the check name.

Paths, ``run:`` scripts and path filters are NOT checked: ``autobot-backend/llc/**``
and ``/api/llc`` are internal names and stay.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

_REPO_ROOT = repo_root()

#: "LLC" as a word: not preceded or followed by a letter, so ``llc-e2e`` and
#: ``LLC Contract Gate`` match while ``callcenter`` does not.
_LLC_WORD = re.compile(r"(?i)(?<![a-z])llc(?![a-z])")


def _workflow_files(root: Path = _REPO_ROOT) -> list[Path]:
    """Every ``*.yml`` workflow under *root*; an empty list on an empty tree, never a raise.

    ``*.yml`` only, which is every workflow in the tree today. A ``*.yaml`` read is
    not covered by the python suite's path filter, and adding one to the uncovered-glob
    record would grow a record that only shrinks (#15900).
    """
    return sorted((root / ".github" / "workflows").glob("*.yml"))


def visible_names(file_name: str, doc: object) -> list[tuple[str, str]]:
    """``(where, name)`` for every name of this workflow a person sees in the GitHub UI."""
    names = [("file", file_name)]
    if not isinstance(doc, dict):
        return names
    if doc.get("name") is not None:
        names.append(("workflow name", str(doc["name"])))
    jobs = doc.get("jobs")
    for job_id, job in (jobs if isinstance(jobs, dict) else {}).items():
        shown = job.get("name") if isinstance(job, dict) and job.get("name") is not None else job_id
        names.append((f"job {job_id}", str(shown)))
    return names


def llc_names(file_name: str, doc: object) -> list[str]:
    """The visible names of one workflow that contain "LLC" as a word."""
    return [f"{file_name}: {where} {name!r}" for where, name in visible_names(file_name, doc) if _LLC_WORD.search(name)]


#: Re-measured with a throwaway count of `_workflow_files()` against this tree, not
#: carried across (#15928); pinned mid-window as `_reach` requires (#17356). `growth=10`
#: absorbs an ordinary new workflow or two before a deliberate re-pin; `skips=0`
#: because an unparseable workflow fails the test below rather than being skipped.
REACH = declare(
    "workflow-visible-name-sweep",
    discover=_workflow_files,
    floor=65,
    growth=10,
    skips=0,
    what="workflow files",
    roots=(".github/workflows",),
)


def _scan() -> tuple[list[str], list[str]]:
    """``(offending names, unparseable files)`` across every workflow, completion-bounded."""
    offenders: list[str] = []
    unreadable: list[str] = []
    parsed = 0
    for path in REACH.examined(_REPO_ROOT):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            unreadable.append(f"{path.name}: {exc}")
            continue
        parsed += 1
        offenders.extend(llc_names(path.name, doc))
    REACH.completed(parsed)
    return offenders, unreadable


def test_no_workflow_or_job_name_a_person_sees_says_llc() -> None:
    """The rule: user-visible workflow and job names use the feature name (#19546)."""
    offenders, unreadable = _scan()
    assert not unreadable, f"could not parse {len(unreadable)} workflow(s), so their names went unchecked: {unreadable}"
    assert not offenders, "\n".join(
        [
            "a workflow or job name shown in the PR checks or the Actions tab says 'LLC'. "
            "User-visible names say 'Company OS'; `llc` is the internal code name only (#19546):",
            *(f"  {o}" for o in offenders),
            "  -> rename it, or give the job a `name:` that says Company OS",
        ]
    )


@pytest.mark.parametrize(
    ("doc", "file_name", "expected"),
    [
        ({"name": "LLC gate", "jobs": {}}, "gate.yml", ["gate.yml: workflow name 'LLC gate'"]),
        ({"name": "Company OS gate", "jobs": {}}, "gate.yml", []),
        (
            {"name": "gate", "jobs": {"llc-x": {"runs-on": "ubuntu-latest"}}},
            "gate.yml",
            ["gate.yml: job llc-x 'llc-x'"],
        ),
        ({"name": "gate", "jobs": {"llc-x": {"name": "Company OS x"}}}, "gate.yml", []),
        ({"name": "Call center", "jobs": {"callcenter": {}}}, "gate.yml", []),
        ({"jobs": {}}, "llc-gate.yml", ["llc-gate.yml: file 'llc-gate.yml'"]),
    ],
    ids=["llc-workflow-fails", "company-os-passes", "llc-job-id-fails", "named-job-passes", "word-boundary", "file"],
)
def test_the_rule_tells_llc_from_company_os(doc: dict, file_name: str, expected: list[str]) -> None:
    """Contrast: the matcher fires on the fixtures that say LLC and on nothing else."""
    assert llc_names(file_name, doc) == expected


def test_the_sweep_fails_on_a_fixture_tree(tmp_path: Path) -> None:
    """End to end over a real directory: a fixture workflow named "LLC gate" is caught."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text("name: LLC gate\njobs:\n  llc-x:\n    runs-on: x\n", encoding="utf-8")
    (workflows / "good.yml").write_text("name: Company OS gate\njobs:\n  ok:\n    runs-on: x\n", encoding="utf-8")
    found = [o for p in _workflow_files(tmp_path) for o in llc_names(p.name, yaml.safe_load(p.read_text("utf-8")))]
    assert found == ["bad.yml: workflow name 'LLC gate'", "bad.yml: job llc-x 'llc-x'"]
