# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21035: a link INTO a component dir is only made when that dir is deployed.

`update-all-nodes.yml` links ``autobot_shared`` into ``<base>/<component>/``. On a freshly
enrolled node the component dir does not exist yet, so an unconditioned link fails with
ENOENT and stops the fleet update. The playbook links ONLY through
``roles/_shared/tasks/link_autobot_shared.yml``, and that file's link must be conditioned on
a registered ``stat`` of the same component dir, run earlier in the file.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_SHARED = _ANSIBLE / "roles" / "_shared" / "tasks" / "link_autobot_shared.yml"
_IMPORT_SUFFIX = "roles/_shared/tasks/link_autobot_shared.yml"
_COMPONENT_LINK = re.compile(r"/[\w.{}\s-]+/autobot_shared$")
_COMPONENT_DIR = re.compile(r"/(?P<component>[\w.{}\s-]+)$")


def _walk(tasks: Any):
    """Yield every task dict in document order, descending into block/rescue/always."""
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("block", "rescue", "always"):
            yield from _walk(task.get(key))


def _is_component_link(task: dict) -> bool:
    args = task.get("ansible.builtin.file") or {}
    return args.get("state") == "link" and bool(_COMPONENT_LINK.search(str(args.get("dest", ""))))


def _conditions(task: dict) -> str:
    when = task.get("when", [])
    return " ".join(str(w) for w in when) if isinstance(when, list) else str(when)


def shared_file_violations(tasks: list[dict]) -> list[str]:
    """Component links not conditioned on a prior stat of the SAME component dir."""
    bad: list[str] = []
    stats: dict[str, str] = {}  # registered var -> component expression it stats
    for task in _walk(tasks):
        stat = task.get("ansible.builtin.stat")
        if stat and task.get("register"):
            match = _COMPONENT_DIR.search(str(stat.get("path", "")))
            if match:
                stats[task["register"]] = match["component"]
        if not _is_component_link(task):
            continue
        dest = str(task["ansible.builtin.file"]["dest"])
        conds = _conditions(task)
        ok = any(
            dest.endswith(f"/{comp}/autobot_shared") and re.search(rf"\b{var}\.stat\.exists\b", conds)
            for var, comp in stats.items()
        )
        if not ok:
            bad.append(str(task.get("name")))
    return bad


def playbook_violations(plays: list[dict]) -> list[str]:
    """Playbook tasks that link inline instead of going through the shared task file."""
    return [str(t.get("name")) for p in plays for t in _walk(p.get("tasks")) if _is_component_link(t)]


def _playbook() -> list[dict]:
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))


def _shared() -> list[dict]:
    return yaml.safe_load(_SHARED.read_text(encoding="utf-8"))


def test_the_shared_link_needs_its_component_deployed() -> None:
    tasks = _shared()
    assert sum(_is_component_link(t) for t in _walk(tasks)) == 1, "detector found no link in the shared file"
    assert shared_file_violations(tasks) == []


def test_every_playbook_link_goes_through_the_shared_task() -> None:
    plays = _playbook()
    importers = [
        t
        for p in plays
        for t in _walk(p.get("tasks"))
        if str(t.get("ansible.builtin.import_tasks", "")).endswith(_IMPORT_SUFFIX)
    ]
    assert len(importers) >= 5, "enumeration found too few importing sites; detector is broken"
    assert all(t["vars"]["shared_link_component"] for t in importers)
    assert playbook_violations(plays) == []


def test_control_an_unconditioned_shared_link_is_caught() -> None:
    tasks = _shared()
    link = next(t for t in _walk(tasks) if _is_component_link(t))
    assert shared_file_violations(tasks) == []
    link.pop("when")
    assert shared_file_violations(tasks) == [link["name"]]


def test_control_an_inline_link_in_the_playbook_is_caught() -> None:
    plays = [{"tasks": [{"name": "inline", "ansible.builtin.file": _link_args("autobot-slm-agent")}]}]
    assert playbook_violations(plays) == ["inline"]


def test_control_a_stat_of_another_component_does_not_count() -> None:
    tasks = [
        {"name": "stat", "ansible.builtin.stat": {"path": "{{ b }}/autobot-backend"}, "register": "other"},
        {"name": "link", "ansible.builtin.file": _link_args("autobot-slm-agent"), "when": "other.stat.exists"},
    ]
    assert shared_file_violations(tasks) == ["link"]


def _link_args(component: str) -> dict:
    return {"dest": f"{{{{ b }}}}/{component}/autobot_shared", "state": "link"}
