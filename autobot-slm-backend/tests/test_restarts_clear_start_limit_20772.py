# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20772: every restart the updater or a role handler makes clears a start-limit park first.

A unit parked in ``failed`` by its start limit refuses a restart, so a bare ``systemd:
state=restarted`` fails the update on that node. The restarts go through the one shared task
file, which runs ``systemctl reset-failed`` and then restarts. These tests fail when a restart
task in ``update-all-nodes.yml`` or a handler of a role the updater includes calls the
``systemd`` module directly.
"""

from pathlib import Path

import yaml

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_SHARED = _ANSIBLE / "_shared" / "tasks" / "restart_unit.yml"
_SHARED_SUFFIX = "_shared/tasks/restart_unit.yml"
_ROLE_KEYS = ("ansible.builtin.include_role", "include_role", "ansible.builtin.import_role", "import_role")


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _mappings(item)


def _is_direct_restart(task: dict) -> bool:
    spec = task.get("systemd") or task.get("ansible.builtin.systemd")
    return isinstance(spec, dict) and spec.get("state") == "restarted"


def _shared_include(task: dict):
    inc = task.get("ansible.builtin.include_tasks") or task.get("include_tasks")
    target = inc.get("file") if isinstance(inc, dict) else inc
    return inc if isinstance(target, str) and target.endswith(_SHARED_SUFFIX) else None


def _updater_roles() -> list:
    found = set()
    for node in _mappings(_load(_PLAYBOOK)):
        for key in _ROLE_KEYS:
            if isinstance(node.get(key), dict):
                found.add(node[key]["name"])
        for entry in node.get("roles") or []:
            found.add(entry if isinstance(entry, str) else entry.get("role") or entry.get("name"))
    return sorted(found)


def _handler_files() -> list:
    paths = [_ANSIBLE / "roles" / role / "handlers" / "main.yml" for role in _updater_roles()]
    return [p for p in paths if p.is_file()]


def test_the_shared_task_clears_the_park_before_it_restarts() -> None:
    tasks = _load(_SHARED)
    modules = [next(iter(set(t) & {"ansible.builtin.command", "ansible.builtin.systemd"})) for t in tasks]
    assert modules == ["ansible.builtin.command", "ansible.builtin.systemd"]
    assert tasks[0]["ansible.builtin.command"]["argv"][:3] == ["systemctl", "reset-failed", "--"]
    assert tasks[1]["ansible.builtin.systemd"]["state"] == "restarted"
    assert tasks[0]["ansible.builtin.command"]["argv"][3] == tasks[1]["ansible.builtin.systemd"]["name"]


def test_the_updater_playbook_restarts_only_through_the_shared_task() -> None:
    mappings = list(_mappings(_load(_PLAYBOOK)))
    shared = [t for t in mappings if _shared_include(t)]
    direct = [t.get("name") for t in mappings if _is_direct_restart(t)]
    assert len(shared) >= 10, "control: the finder sees the playbook's restart tasks"
    assert not direct, f"these restarts do not clear a start-limit park: {direct}"


def test_every_updater_role_handler_restarts_only_through_the_shared_task() -> None:
    files = _handler_files()
    handlers = [h for f in files for h in _load(f) if isinstance(h, dict)]
    shared = [h for h in handlers if _shared_include(h)]
    direct = [h.get("name") for h in handlers if _is_direct_restart(h)]
    assert len(shared) >= 25, "control: the finder sees the role handlers' restarts"
    assert not direct, f"these handlers do not clear a start-limit park: {direct}"


def test_every_shared_include_names_its_unit() -> None:
    sources = [_PLAYBOOK, *_handler_files()]
    includes = [t for src in sources for t in _mappings(_load(src)) if _shared_include(t)]
    assert includes
    nameless = [t.get("name") for t in includes if not (t.get("vars") or {}).get("restart_unit_name")]
    assert not nameless, f"restart includes without restart_unit_name: {nameless}"


def test_a_playbook_restart_keeps_its_tags_inside_the_include() -> None:
    """include_tasks does not pass its tags down: without ``apply`` a ``--tags`` run skips the restart."""
    for task in _mappings(_load(_PLAYBOOK)):
        inc = _shared_include(task)
        if inc is None:
            continue
        assert isinstance(inc, dict) and inc.get("apply", {}).get("tags") == task.get("tags"), task.get("name")


def test_the_self_update_socket_restart_goes_through_the_shared_task() -> None:
    """#21426: the socket restart in the manager role is the same class of restart as the handlers."""
    path = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "bind_self_update_socket.yml"
    mappings = list(_mappings(_load(path)))
    assert [t.get("name") for t in mappings if _is_direct_restart(t)] == []
    shared = [t for t in mappings if _shared_include(t)]
    assert len(shared) == 1
    assert shared[0]["vars"]["restart_unit_name"] == "{{ slm_self_update_socket_service }}.socket"
    assert shared[0]["ansible.builtin.include_tasks"]["apply"]["tags"] == ["slm", "service", "systemd"]
