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

import ast
import json
import re

import pytest
from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache

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


def _report() -> str:
    return _named(_unit()["rescue"], "could not be proposed")["ansible.builtin.set_fact"][
        "internal_api_key_realign_report"
    ]


def test_nothing_in_the_rescue_can_fail_again() -> None:
    for task in _unit()["rescue"]:
        assert task.get("failed_when") is not True, f"rescue task {task['name']!r} must not fail"
    report = _report()
    for var in (
        "ansible_failed_result",
        "internal_api_key_by_file",
        "internal_api_key_canonical",
        "_r.msg",
        "_r.status",
    ):
        assert f"{var} | default(" in report or f"{var}|default(" in report, f"the rescue reads {var} without a default"
    assert "is mapping" in report, "the rescue must not assume the key map is a mapping"
    assert "map('string')" in report, "keys must be cast to str before the `in` test"


def test_the_rescue_neutralises_braces_in_the_embedded_error_text() -> None:
    report = _report()
    assert (
        "replace('{', '(')" in report and "replace('}', ')')" in report
    ), "a templating error quotes the failing expression; the line is templated again, so braces must go"


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


def _include_urls() -> list[str]:
    plays = [p for p in _load(_UPDATER) if isinstance(p, dict)]
    return [
        t["vars"]["internal_api_key_backend_url"]
        for p in plays
        for t in p.get("tasks", [])
        if "internal_api_key_backend_url" in (t.get("vars") or {})
    ]


def _registry_inventory_globals() -> set[str]:
    """Keys of `_ALL_VARS` in inventory_builder: the globals the updater's generated inventory carries."""
    source = (repo_root() / "autobot-slm-backend" / "services" / "inventory_builder.py").read_text(encoding="utf-8")
    for node in parse_cache.parse(source).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if target is not None and getattr(target, "id", "") == "_ALL_VARS":
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("_ALL_VARS not found in inventory_builder.py")


def test_the_internal_key_url_does_not_template_the_infrastructure_dict() -> None:
    """Looking up `infrastructure` templates the whole dict, so one bad entry kills any task using it."""
    urls = _include_urls()
    assert len(urls) == 2, "expected the claim and the verify include"
    assert not [u for u in urls if "infrastructure" in u], urls


def test_the_internal_key_url_only_uses_variables_the_updater_defines_before_it() -> None:
    """The registry-built inventory sets only `_ALL_VARS`; `backend_port` comes from the vars file loaded earlier."""
    tasks = _play2_tasks()
    names = [str(t.get("name", "")) for t in tasks]
    loaded = next(i for i, n in enumerate(names) if "Load shared backend env vars" in n)
    include = next(i for i, n in enumerate(names) if "Propose or claim re-aligning the internal key" in n)
    assert loaded < include, "backend-env.yml must be loaded before the proposal include"
    vars_file = tasks[loaded]["ansible.builtin.include_vars"]["file"]
    defined = set(yaml.safe_load((_ANSIBLE / "playbooks" / vars_file).read_text(encoding="utf-8")))
    defined |= _registry_inventory_globals()
    for url in _include_urls():
        unknown = set(re.findall(r"\{\{\s*(\w+)", url)) - defined
        assert not unknown, f"{url!r} uses {unknown}, which the updater's inventory does not define"


def test_the_backend_health_wait_uses_the_same_port_variable() -> None:
    wait = _named(_play2_tasks(), "Backend | Wait for API to be ready")
    assert "{{ backend_port }}" in wait["uri"]["url"], "the health probe must not restate the port"


def test_every_infrastructure_host_entry_uses_the_guarded_group_idiom() -> None:
    """The idiom all.yml uses for vnc_nodes: index `hostvars[groups[x][0]]` only when `groups.get(x)` is non-empty."""
    path = _ANSIBLE / "inventory" / "group_vars" / "infrastructure.yml"
    hosts = yaml.safe_load(path.read_text(encoding="utf-8"))["infrastructure"]["hosts"]
    pattern = re.compile(
        r"\{\{ \(hostvars\[groups\['(\w+)'\]\[0\]\]\['ansible_host'\] \| default\('127\.0\.0\.1'\)\) "
        r"if groups\.get\('\1'\) else '127\.0\.0\.1' \}\}$"
    )
    templated = {k: v for k, v in hosts.items() if "{{" in str(v)}
    assert templated, "expected templated host entries"
    bad = [k for k, v in templated.items() if not pattern.match(str(v))]
    assert not bad, f"host entries not using the guarded group idiom: {bad}"
