# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No workflow subscribes to a pull-request event (#20825).

A pull request without a ``land-next`` slot creates ZERO workflow runs: the PR coordinator starts CI with
``workflow_dispatch``. So no workflow may subscribe to ``pull_request`` / ``pull_request_target`` /
``pull_request_review*``, and no ``push`` trigger may be wider than the protected branches (a push to a PR
branch would start a run on every push). The allowlist is EMPTY on purpose: the owner's rule has no exception,
and every case once thought to need one has an event-free replacement.
"""

from __future__ import annotations

import pytest
import yaml
from repo_tests._pr_dispatch import WORKFLOWS, load, trigger_violations, triggers, workflow_files

#: file -> reason. Empty: an entry needs an owner decision recorded on #20825.
ALLOWLIST: dict[str, str] = {}


def test_the_allowlist_is_empty() -> None:
    assert ALLOWLIST == {}, "the owner rule has no exception; a workflow here needs a recorded owner decision"


def test_every_workflow_file_is_read_and_has_triggers() -> None:
    files = workflow_files()
    assert len(files) == len(list(WORKFLOWS.glob("*.yml"))) and len(files) > 60, f"only {len(files)} workflow files read"
    assert all(triggers(load(path)) for path in files), [p.name for p in files if not triggers(load(p))]


def test_no_workflow_can_be_started_by_a_pull_request() -> None:
    found = {p.name: trigger_violations(load(p)) for p in workflow_files() if p.name not in ALLOWLIST}
    assert {name: why for name, why in found.items() if why} == {}


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("on:\n  pull_request:\n    types: [opened]\n", "pull_request"),
        ("on: [push, pull_request]\n", "pull_request"),
        ("on: pull_request\n", "pull_request"),
        ("on:\n  pull_request_target:\n", "pull_request_target"),
        ("on:\n  pull_request_review:\n", "pull_request_review"),
        ("on:\n  push:\n    branches-ignore: [main]\n", "without `branches:`"),
        ("on:\n  push:\n", "without `branches:`"),
        ("on:\n  push:\n    branches: ['issue-*']\n", "non-protected"),
        ("on:\n  push:\n    branches: ['**']\n", "non-protected"),
    ],
)
def test_control_each_way_to_subscribe_is_caught(text: str, needle: str) -> None:
    doc = yaml.safe_load(text)
    assert any(needle in why for why in trigger_violations(doc)), (text, trigger_violations(doc))


@pytest.mark.parametrize(
    "text",
    [
        "on:\n  push:\n    branches: [main, release]\n  workflow_dispatch:\n  schedule:\n    - cron: '1 * * * *'\n",
        "on:\n  push:\n    tags: ['v*']\n",
        "on:\n  merge_group:\n  workflow_call:\n",
    ],
)
def test_control_the_allowed_shapes_are_not_flagged(text: str) -> None:
    assert trigger_violations(yaml.safe_load(text)) == []
