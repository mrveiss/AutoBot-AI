# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The internal-key proposal step can never abort a node's update (#21343, #20750).

The step only PROPOSES a credential change for a person to approve (#17038). It failed fatally on
every update, and the fatal ended the main node's play: no restart of the backend, workers or AI
stack, and no user-frontend sync or build. `failed_when: false` absorbs only a module result, so the
unit is wrapped in block/rescue, and the rescue records a key-free line the update summary prints.

CI does not execute Ansible; these guards pin the SHAPE. Mutation check: drop the block's `rescue`,
or print `ansible_failed_result` whole, and a test below goes red.
"""

from __future__ import annotations

import json

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_CLAIM = _ANSIBLE / "_shared" / "tasks" / "realign_internal_api_key_claim.yml"
_UPDATER = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_PROPOSE = "Propose re-aligning"


def _dump(node) -> str:
    return json.dumps(node, default=str)


def _load(path) -> list:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, f"{path.name}: expected a non-empty list"
    return loaded


def _unit() -> dict:
    blocks = [t for t in _load(_CLAIM) if isinstance(t, dict) and "block" in t]
    assert len(blocks) == 1, "the proposal step must sit in ONE block/rescue unit"
    return blocks[0]


def _named(tasks: list, fragment: str) -> dict:
    found = [t for t in tasks if fragment in str(t.get("name", ""))]
    assert len(found) == 1, f"expected exactly one task naming {fragment!r}, found {len(found)}"
    return found[0]


def test_the_proposal_task_is_inside_a_block_with_a_rescue() -> None:
    unit = _unit()
    assert unit.get("rescue"), "a failure of the proposal step must be rescued, not fatal to the play"
    _named(unit["block"], _PROPOSE)
    top_level = [t for t in _load(_CLAIM) if isinstance(t, dict) and _PROPOSE in str(t.get("name", ""))]
    assert not top_level, "the proposal task must not sit outside the rescued block"


def test_nothing_in_the_rescue_can_fail_again() -> None:
    for task in _unit()["rescue"]:
        assert task.get("failed_when") is not True, f"rescue task {task['name']!r} must not fail"


def test_the_rescue_reports_status_and_field_names_not_the_whole_result() -> None:
    text = _dump(_unit()["rescue"])
    for shape in ("ansible_failed_result.status", "ansible_failed_result.keys()", "internal_api_key_realign_report"):
        assert shape in text, f"the rescue must report {shape}"
    whole = [t for t in _unit()["rescue"] if "{{ ansible_failed_result }}" in _dump(t)]
    assert not whole, "never print the whole failed result: it can carry request headers"


def test_the_rescue_withholds_error_text_that_holds_a_key() -> None:
    setter = _named(_unit()["rescue"], "could not be proposed")
    assert setter.get("no_log") is True, "the task that reads the keys must be no_log"
    assert "select('in', _msg)" in _dump(setter), "error text must be withheld when it contains a key"


def test_every_task_that_carries_a_key_is_no_log() -> None:
    carrying = [t for t in _unit()["block"] if "internal_api_key_by_file[" in _dump(t)]
    assert carrying, "expected tasks that send the backend's key"
    unhidden = [t["name"] for t in carrying if t.get("no_log") is not True]
    assert not unhidden, f"tasks sending a key without no_log: {unhidden}"


def test_the_update_summary_prints_the_realign_report() -> None:
    plays = [p for p in _load(_UPDATER) if isinstance(p, dict)]
    text = _dump([t for p in plays for t in p.get("tasks", []) if "Display update summary" in str(t.get("name"))])
    assert "internal_key_realign_lines" in text, "the summary must state where the credential re-alignment stands"


def _play2_tasks() -> list:
    play = next(p for p in _load(_UPDATER) if str(p.get("name", "")).startswith("Play 2 - "))
    return play["tasks"]


def test_service_restarts_are_inline_after_the_proposal_include_not_handlers() -> None:
    tasks = _play2_tasks()
    names = [str(t.get("name", "")) for t in tasks]
    include = next(i for i, n in enumerate(names) if "Propose or claim re-aligning the internal key" in n)
    restart = next(i for i, n in enumerate(names) if n == "[PLAY 2] Backend | Restart service")
    assert include < restart, "the restart must come after the proposal include"
    assert not [
        t for t in tasks if "notify" in t
    ], "Play 2 restarts are inline tasks; a notify would wait on a handler flush"
