# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every workflow job that runs repo Python sets up the ``.python-version`` floor (#20903).

``autobot_shared/__init__`` calls ``require_supported_python()`` at import, so any job
that runs a repo script (``pipeline-scripts/``, ``scripts/``, ``tools/``,
``repo_tests/``) or pytest on the runner's default ``python3`` crashes with
``UnsupportedPythonError`` the moment it imports ``autobot_shared``. The floor is only
true everywhere if each such job installs the interpreter first.

A job passes when a step BEFORE the first such run step is either
``actions/setup-python`` with ``python-version-file`` or one of the repo's composite
actions that set the interpreter from ``.python-version``.
"""

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"
# The runner-default interpreter invoked on a repo script, directly or via a relative path
# (``python3 ../../tools/lint/x.py``). An explicit interpreter path (a venv's python, the
# setup-python output) is not the runner default and is not matched.
_REPO_SCRIPT = re.compile(
    r"(?<![\w./-])python3?\s+(?:-[\w-]+\s+)*(?:\.\./)*" r"(?:pipeline-scripts|scripts|tools|repo_tests)/[\w./-]+\.py\b"
)
_PYTEST = re.compile(r"(?<![\w-])pytest(?![\w-])")
_FLOOR_COMPOSITES = ("setup-python-ci", "setup-python-suite")


def _runs_repo_python(run: str) -> bool:
    return bool(_REPO_SCRIPT.search(run) or _PYTEST.search(run))


def _sets_floor(step: dict) -> bool:
    uses = step.get("uses") or ""
    with_ = step.get("with") or {}
    if uses.startswith("actions/setup-python@"):
        return "python-version-file" in with_
    return any(uses.endswith(c) for c in _FLOOR_COMPOSITES) and "python-version" not in with_


def jobs_missing_floor(workflow: dict) -> list:
    """Job ids that run repo Python before (or without) a floor-setting step."""
    bad = []
    for job_id, job in (workflow.get("jobs") or {}).items():
        ready = False
        for step in job.get("steps") or []:
            ready = ready or _sets_floor(step)
            if not ready and _runs_repo_python(step.get("run") or ""):
                bad.append(job_id)
                break
    return bad


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_every_job_running_repo_python_sets_up_the_floor():
    offenders = {}
    workflows = sorted(WORKFLOW_DIR.glob("*.yml"))
    assert workflows, "no workflows found - the glob measured nothing"
    for path in workflows:
        bad = jobs_missing_floor(_load(path))
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        "jobs run repo Python without a prior actions/setup-python using "
        "python-version-file: .python-version (the autobot_shared import floor, #20903): "
        f"{offenders}"
    )


_PLANTED = """
jobs:
  bare:
    steps:
      - uses: actions/checkout@v7
      - run: python3 pipeline-scripts/pr_structure.py
  late:
    steps:
      - run: pytest repo_tests
      - uses: actions/setup-python@v7
        with: {python-version-file: .python-version}
  pinned_version:
    steps:
      - uses: actions/setup-python@v7
        with: {python-version: "3.11"}
      - run: python3 scripts/x.py
  ok:
    steps:
      - uses: actions/setup-python@v7
        with: {python-version-file: .python-version}
      - run: python3 pipeline-scripts/pr_structure.py
  composite_ok:
    steps:
      - uses: ./.github/actions/setup-python-ci
      - run: pytest
  stdlib_only:
    steps:
      - run: python3 -c "print(1)"
"""


def test_control_planted_workflow_is_caught():
    planted = yaml.safe_load(_PLANTED)
    assert jobs_missing_floor(planted) == ["bare", "late", "pinned_version"]
