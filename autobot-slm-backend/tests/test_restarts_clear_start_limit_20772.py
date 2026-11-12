# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20772: every restart the updater or a role handler makes clears a start-limit park first.

A unit parked in ``failed`` by its start limit refuses a restart, so a bare ``systemd:
state=restarted`` fails the update on that node. The restarts go through the one shared task
file, which runs ``systemctl reset-failed`` and then restarts. These tests fail when a restart
task or handler anywhere under ``ansible/`` restarts a unit through the ``systemd``/``service`` module
directly, unless the site is on ``_DIRECT_RESTARTS`` with its reason.
"""

from pathlib import Path

import yaml

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_SHARED = _ANSIBLE / "_shared" / "tasks" / "restart_unit.yml"
_SHARED_SUFFIX = "_shared/tasks/restart_unit.yml"
_ROLE_KEYS = ("ansible.builtin.include_role", "include_role", "ansible.builtin.import_role", "import_role")


class _Loader(yaml.SafeLoader):
    """SafeLoader that reads Ansible's custom tags (``!unsafe``, ``!vault``) as plain data."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def _load(path: Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader) or []  # noqa: S506 - SafeLoader subclass


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
    sources = _all_yaml()
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


_RESTART_MODULES = ("systemd", "ansible.builtin.systemd", "service", "ansible.builtin.service")
_NOT_A_UNIT_OF_OURS = (
    "OS or third-party daemon: AutoBot renders no unit for it and sets no start limit on it (#20772 is AutoBot units)."
)
_CONSUMES_REGISTER = "a later task reads this restart's own register; include_tasks cannot return it (#21429)."
# (file under ansible/, unit as written) -> why this restart stays a direct module call.
_DIRECT_RESTARTS = {
    (
        "fix-slm-env-ports.yml",
        "autobot-slm-backend",
    ): "async: 1 / poll: 0 fire-and-forget; an include cannot be detached (#21429).",
    ("migrate-grafana-to-vm.yml", "grafana-server"): "third-party daemon; the task also sets enabled (one call).",
    (
        "playbooks/deploy-native-services.yml",
        "redis-stack-server",
    ): "the same call also sets enabled on first configuration (#21429).",
    ("playbooks/deploy-base.yml", "ssh"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "systemd-resolved"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-base.yml", "fail2ban"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/deploy-time-sync.yml", "{{ item }}"): _NOT_A_UNIT_OF_OURS + " Loops chrony/timesyncd, rsyslog, cron.",
    ("playbooks/enroll-node.yml", "ssh"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/enroll-node.yml", "ufw"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/setup-vm-names-and-lvm.yml", "systemd-networkd"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/setup-vm-names-and-lvm.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("playbooks/toggle-enforcement.yml", "autobot-backend"): _CONSUMES_REGISTER,
    ("playbooks/update-node.yml", "{{ item }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/post-update.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback-system.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/centralized_logging/handlers/main.yml", "loki"): _NOT_A_UNIT_OF_OURS,
    ("roles/centralized_logging/handlers/main.yml", "promtail"): _NOT_A_UNIT_OF_OURS,
    ("roles/common/handlers/main.yml", "sshd"): _NOT_A_UNIT_OF_OURS,
    ("roles/common/handlers/main.yml", "logrotate.timer"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "dnsmasq"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "systemd-resolved"): _NOT_A_UNIT_OF_OURS,
    ("roles/docker/handlers/main.yml", "docker"): _NOT_A_UNIT_OF_OURS,
    ("roles/llm/handlers/main.yml", "ollama"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-timesyncd"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "chrony"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "cron"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-logind"): _NOT_A_UNIT_OF_OURS,
    ("roles/xrdp/handlers/main.yml", "{{ xrdp_service_name }}"): _NOT_A_UNIT_OF_OURS,
}


def _all_yaml() -> list:
    return [p for p in sorted(_ANSIBLE.rglob("*.yml")) if not {"tests", "_shared"} & set(p.relative_to(_ANSIBLE).parts)]


def _direct_restart_sites() -> list:
    found = []
    for path in _all_yaml():
        for node in _mappings(_load(path)):
            for module in _RESTART_MODULES:
                spec = node.get(module)
                if isinstance(spec, dict) and spec.get("state") == "restarted":
                    found.append((path.relative_to(_ANSIBLE).as_posix(), str(spec.get("name"))))
    return found


def test_no_restart_anywhere_under_ansible_skips_the_shared_task_unless_justified() -> None:
    sites = _direct_restart_sites()
    assert len(sites) >= len(_DIRECT_RESTARTS), "control: the finder sees the allow-listed sites"
    unlisted = [s for s in sites if s not in _DIRECT_RESTARTS]
    assert not unlisted, f"direct restarts that clear no start-limit park and are not on the allow-list: {unlisted}"


def test_the_allow_list_has_no_stale_entry() -> None:
    assert sorted(set(_DIRECT_RESTARTS) - set(_direct_restart_sites())) == []


# Every restart that tolerates failure, as (file, unit as written). The first eight had `failed_when: false`
# on origin/main before the shared task (browser x2, frontend, slm_manager handlers; NPU, browser, AI Stack
# x2 in update-all-nodes.yml); the last four carried `ignore_errors: true` / `failed_when: false` in the
# TLS and certificate playbooks and keep that behaviour when converted.
_TOLERANT = [
    ("roles/browser/handlers/main.yml", "autobot-vnc"),
    ("roles/browser/handlers/main.yml", "autobot-playwright"),
    ("roles/frontend/handlers/main.yml", "autobot-frontend"),
    ("roles/slm_manager/handlers/main.yml", "{{ slm_backend_service }}"),
    ("playbooks/update-all-nodes.yml", "autobot-npu-worker"),
    ("playbooks/update-all-nodes.yml", "autobot-playwright"),
    ("playbooks/update-all-nodes.yml", "autobot-ai-stack"),
    ("playbooks/update-all-nodes.yml", "autobot-chromadb"),
    ("enable-tls.yml", "autobot-backend"),
    ("enable-tls.yml", "{{ redis_service_name | default('redis-stack-server') }}"),
    ("playbooks/rotate-certs.yml", "{{ _service }}"),
    ("playbooks/rotate-certs.yml", "{{ _service }}"),
]


def test_exactly_the_sites_that_tolerated_failure_still_tolerate_it() -> None:
    found = []
    for path in _all_yaml():
        for node in _mappings(_load(path)):
            vars_ = node.get("vars") if _shared_include(node) else None
            if isinstance(vars_, dict) and vars_.get("restart_unit_tolerate_failure") is True:
                found.append((path.relative_to(_ANSIBLE).as_posix(), vars_["restart_unit_name"]))
    assert sorted(found) == sorted(_TOLERANT)
