# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The daily failure sweep covers every scheduled workflow, and nothing is listed by hand (#21592).

`pipeline-scripts/scheduled_failure_report.py` derives its list at run time: every workflow whose
`on` map carries a `schedule` with a cron. A list kept in sync by hand is how a new scheduled
workflow goes unwatched, so the list does not exist; what can still go wrong is the DERIVATION --
the `on` key parsing as the boolean `True`, a `.yaml` extension, a trigger written in a form the
parser reads differently -- missing a workflow that does have a schedule.

The rule: the script's own discovery function, run over the real `.github/workflows`, returns
exactly the files an independent scan finds. The scan reads text, not YAML, and is the repo's one text
reader of a workflow's schedule, `release_sync_main.declares_schedule` (comment-stripped `on:` block
with a `schedule:` key and a `cron:` value). Two instruments with different failure modes agreeing is
the evidence; one disagreeing names the file. The population is declared with the reach mechanism as a
fraction of that independent count (1.0: every file the text scan finds), so a derivation that reaches
fewer files, or a scan that finds none, is refused rather than passed.

Controls: planted workflows in every trigger form (bare and quoted `on`, `.yaml`, string and list
`on`, an empty and a commented-out `schedule`) must come out the same from both instruments, and
the comparison itself must name a file one side misses.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests._release_sync_fakes import load_script

_SCRIPT = "pipeline-scripts/scheduled_failure_report.py"
_WORKFLOWS = ".github/workflows"
_REPORT_WORKFLOW = "scheduled-failure-report.yml"
_MODULE_NAME = "_scheduled_failure_report_guard_21592"


@functools.lru_cache(maxsize=1)
def _script() -> ModuleType:
    """The sweep script, loaded by path (its directory name has a hyphen)."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, repo_root() / _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module  # its dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def _text_reader() -> Callable[[str], bool]:
    """The repo's one text reader of a workflow's schedule (release_sync_main), loaded the way its own tests do."""
    return load_script().declares_schedule


def derived_names(directory: Path) -> set[str]:
    """The workflow files the script's own discovery calls scheduled."""
    if not directory.is_dir():
        return set()
    return {wf.file for wf in _script().scheduled_workflows(directory)}


def scanned_names(directory: Path) -> set[str]:
    """The same question asked of the text: no YAML parse, no glob, no code shared with the script."""
    if not directory.is_dir():
        return set()
    files = [path for path in directory.iterdir() if path.suffix in {".yml", ".yaml"}]
    return {path.name for path in files if _text_reader()(path.read_text(encoding="utf-8"))}


def uncovered(derived: set[str], scanned: set[str]) -> list[str]:
    """Every file the two instruments disagree on, each with the side that saw it."""
    missed = [f"{name}: has a schedule in its text, the derivation missed it" for name in scanned - derived]
    invented = [f"{name}: derived as scheduled, its text has no schedule with a cron" for name in derived - scanned]
    return sorted(missed + invented)


def _scheduled_files(root: Path) -> list[Path]:
    directory = root / _WORKFLOWS
    return [directory / name for name in sorted(derived_names(directory))]


REACH = declare(
    "scheduled-workflows-derived-for-failure-report-21592",
    discover=_scheduled_files,
    min_fraction=1.0,
    reference=lambda root: len(scanned_names(root / _WORKFLOWS)),
    what="scheduled workflow files the failure sweep derives",
    roots=(_WORKFLOWS,),
)

_PLANTED = {
    "bare-on.yml": "name: A\non:\n  schedule:\n    - cron: '0 1 * * *'\n",
    "quoted-on.yml": "'on':\n  schedule:\n    - cron: '0 1 * * *'\n",
    "other-ext.yaml": "on:\n  push:\n  schedule:\n    # nightly\n\n    - cron: '5 4 * * 1'\n",
    "string-form.yml": "on: schedule\njobs: {}\n",
    "list-form.yml": "on: [push, schedule]\njobs: {}\n",
    "empty-schedule.yml": "on:\n  schedule: []\n",
    "commented-cron.yml": "on:\n  push:\n  # schedule:\n  #   - cron: '0 1 * * *'\n",
    "no-schedule.yml": "on: push\njobs: {}\n",
}
_PLANTED_SCHEDULED = {"bare-on.yml", "quoted-on.yml", "other-ext.yaml"}


def test_the_derivation_covers_every_scheduled_workflow_in_the_repository() -> None:
    directory = repo_root() / _WORKFLOWS
    scanned = scanned_names(directory)
    assert scanned, "the text scan found no scheduled workflow: the instrument is blind, not the tree empty"
    assert {path.name for path in REACH.examined(repo_root())} == derived_names(directory)
    assert uncovered(derived_names(directory), scanned) == []


def test_both_instruments_agree_on_every_planted_trigger_form(tmp_path: Path) -> None:
    for name, text in _PLANTED.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert derived_names(tmp_path) == _PLANTED_SCHEDULED
    assert scanned_names(tmp_path) == _PLANTED_SCHEDULED


def test_a_derivation_that_misses_a_scheduled_file_is_named() -> None:
    assert uncovered({"a.yml"}, {"a.yml", "b.yml"}) == ["b.yml: has a schedule in its text, the derivation missed it"]


def test_a_derivation_that_invents_a_scheduled_file_is_named() -> None:
    assert uncovered({"a.yml", "b.yml"}, {"a.yml"}) == [
        "b.yml: derived as scheduled, its text has no schedule with a cron"
    ]


def test_an_empty_or_missing_directory_derives_and_scans_nothing(tmp_path: Path) -> None:
    for directory in (tmp_path, tmp_path / "absent"):
        assert derived_names(directory) == set() and scanned_names(directory) == set()


def _report_workflow() -> dict:
    return yaml.safe_load((repo_root() / _WORKFLOWS / _REPORT_WORKFLOW).read_text(encoding="utf-8"))


def test_the_report_workflow_is_scheduled_dispatchable_with_a_dry_run_and_least_privilege() -> None:
    doc = _report_workflow()
    triggers = doc[True] if True in doc else doc["on"]
    assert triggers["schedule"] and "workflow_dispatch" in triggers
    assert triggers["workflow_dispatch"]["inputs"]["dry_run"]["type"] == "boolean"
    assert doc["permissions"] == {"actions": "read", "contents": "read", "issues": "write"}


def test_the_report_workflow_runs_the_script_it_is_guarded_for() -> None:
    steps = [step for job in _report_workflow()["jobs"].values() for step in job["steps"]]
    assert any(_SCRIPT in (step.get("run") or "") for step in steps)
