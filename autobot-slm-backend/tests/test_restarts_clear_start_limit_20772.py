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

import re
from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_SHARED = _ANSIBLE / "_shared" / "tasks" / "restart_unit.yml"
_SHARED_SUFFIX = "_shared/tasks/restart_unit.yml"
_ROLE_KEYS = ("ansible.builtin.include_role", "include_role", "ansible.builtin.import_role", "import_role")


class _Loader(yaml.SafeLoader):
    """SafeLoader that reads Ansible's custom tags (``!unsafe``, ``!vault``) as plain data."""


_Loader.add_multi_constructor("!", lambda loader, suffix, node: None)


def _load(path: Path) -> list:
    """Every document of the file, flattened: a list document contributes its items, any other its value.

    Handles multi-document files (``---`` x N), dict-shaped vars files and empty documents. A file
    that does not parse fails the test with its name; it is never skipped.
    """
    try:
        docs = list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader))  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise AssertionError(f"{path.name} does not parse as YAML: {exc}") from exc
    flat: list = []
    for doc in docs:
        if isinstance(doc, list):
            flat.extend(doc)
        elif doc is not None:
            flat.append(doc)
    return flat


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


def _mappings_in_context(node, in_handler: bool = False):
    """Yield (mapping, in_handler); a ``handlers:`` subtree is handler context."""
    if isinstance(node, dict):
        yield node, in_handler
        for key, value in node.items():
            yield from _mappings_in_context(value, in_handler or key == "handlers")
    elif isinstance(node, list):
        for item in node:
            yield from _mappings_in_context(item, in_handler)


def _lacks_apply(task: dict, inc) -> bool:
    return not (isinstance(inc, dict) and (inc.get("apply") or {}).get("tags") == task["tags"])


def _tagged_includes_without_apply() -> list:
    """Non-handler shared includes whose own ``tags`` are not repeated in ``apply.tags``.

    A dynamic ``include_tasks`` at a play site is itself tag-filtered, and its tags do not reach the
    included tasks, so under ``--tags`` the include runs but the inner restart is filtered out unless
    ``apply: {tags: ...}`` repeats them (ansible-core 2.17 ``playbook/task.py`` ``evaluate_tags`` and
    ``plugins/strategy/linear.py`` ``filter_tagged_tasks``). Handlers are exempt: they ignore tags
    (docs "Handlers ignore tags"; the handler branch of ``linear.py`` never calls ``filter_tagged_tasks``).
    Limit: handler context is a ``handlers:`` key or a file under ``handlers/``; a handler file pulled in
    by name from elsewhere would be judged as a play site.
    """
    bad = []
    for path in _all_yaml():
        rel = path.relative_to(_ANSIBLE).as_posix()
        for task, in_handler in _mappings_in_context(_load(path), "handlers" in path.relative_to(_ANSIBLE).parts):
            inc = _shared_include(task)
            if inc is None or in_handler or "tags" not in task:
                continue
            if _lacks_apply(task, inc):
                bad.append((rel, task.get("name")))
    return bad


def test_every_play_site_restart_keeps_its_tags_inside_the_include() -> None:
    assert _tagged_includes_without_apply() == []


def test_the_tag_check_sees_a_missing_apply() -> None:
    """Control: the finder is not blind; it reports a fixture include whose tags are not applied."""
    fixture = "- ansible.builtin.include_tasks: _shared/tasks/restart_unit.yml\n  tags: [restart]\n"
    tasks = list(_mappings_in_context(yaml.load(fixture, Loader=_Loader)))  # noqa: S506
    assert [_lacks_apply(t, _shared_include(t)) for t, _ in tasks if _shared_include(t)] == [True]


def test_the_loader_reads_every_document_of_a_multi_document_file(tmp_path: Path) -> None:
    sample = tmp_path / "two.yml"
    sample.write_text("---\n- name: a\n  hosts: x\n---\n- name: b\n  hosts: y\n---\n---\nkey: !vault |\n  abc\n", encoding="utf-8")
    assert [d.get("name", d.get("key")) for d in _load(sample)] == ["a", "b", None]
    broken = tmp_path / "broken.yml"
    broken.write_text("- a: [unclosed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="broken.yml"):
        _load(broken)


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
    "distro-packaged daemon: this repo renders its configuration at most, never its unit file or a systemd "
    "drop-in, and sets no start limit on it (#20772 is AutoBot-managed units)."
)
_CONSUMES_REGISTER = "a later task reads this restart's own register; include_tasks cannot return it (#21429)."
# (file under ansible/, unit as written) -> why this restart stays a direct module call.
_DIRECT_RESTARTS = {
    (
        "fix-slm-env-ports.yml",
        "autobot-slm-backend",
    ): "async: 1 / poll: 0 fire-and-forget; an include cannot be detached (#21429).",
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
    (
        "playbooks/update-all-nodes.yml",
        "autobot-frontend",
    ): "`systemctl try-restart`: leaves a stopped unit alone, which the shared task (a plain restart) would start; "
    "it also reads its own register (#19661, #21429).",
    ("roles/dependency_patching/tasks/post-update.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback-system.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/dependency_patching/tasks/rollback.yml", "{{ current_service.service_name }}"): _CONSUMES_REGISTER,
    ("roles/common/handlers/main.yml", "sshd"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "dnsmasq"): _NOT_A_UNIT_OF_OURS,
    ("roles/dns/handlers/main.yml", "systemd-resolved"): _NOT_A_UNIT_OF_OURS,
    ("roles/docker/handlers/main.yml", "docker"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-timesyncd"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "chrony"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "rsyslog"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "cron"): _NOT_A_UNIT_OF_OURS,
    ("roles/time_sync/handlers/main.yml", "systemd-logind"): _NOT_A_UNIT_OF_OURS,
    ("roles/xrdp/handlers/main.yml", "{{ xrdp_service_name }}"): _NOT_A_UNIT_OF_OURS,
}


_COMMAND_MODULES = ("command", "ansible.builtin.command", "shell", "ansible.builtin.shell")
_SYSTEMCTL_RESTART = re.compile(r"systemctl\s+(?:--?\S+\s+)*(?:try-)?restart\s+(?:--\s+)?(\S+)")


def _all_yaml() -> list:
    found = [p for ext in ("yml", "yaml") for p in _ANSIBLE.rglob(f"*.{ext}")]
    return sorted(p for p in found if not {"tests", "_shared"} & set(p.relative_to(_ANSIBLE).parts))


def _command_restart_unit(node: dict):
    """The unit of a ``systemctl [try-]restart <unit>`` run through command/shell, else None."""
    for module in _COMMAND_MODULES:
        spec = node.get(module)
        text = spec.get("cmd") or spec.get("argv") if isinstance(spec, dict) else spec
        text = " ".join(map(str, text)) if isinstance(text, list) else text
        hit = _SYSTEMCTL_RESTART.search(text) if isinstance(text, str) else None
        if hit:
            return hit.group(1)
    return None


def _direct_restart_sites() -> list:
    """(file, unit as written) of each restart made without the shared task.

    Finds ``systemd``/``service`` modules with a literal ``state: restarted`` and ``systemctl [try-]restart
    <unit>`` in command/shell ``cmd``/``argv``/free-form, in ``*.yml`` and ``*.yaml`` under ``ansible/``
    except ``tests/`` and ``_shared/``. Limits: a state or command built from a variable
    (``state: "{{ x }}"``), a restart inside a script file or a template, and a restart through
    ``ansible.builtin.service_facts``-style indirection are not seen.
    """
    found = []
    for path in _all_yaml():
        rel = path.relative_to(_ANSIBLE).as_posix()
        for node in _mappings(_load(path)):
            for module in _RESTART_MODULES:
                spec = node.get(module)
                if isinstance(spec, dict) and spec.get("state") == "restarted":
                    found.append((rel, str(spec.get("name"))))
            unit = _command_restart_unit(node)
            if unit:
                found.append((rel, unit))
    return found


def test_no_restart_anywhere_under_ansible_skips_the_shared_task_unless_justified() -> None:
    sites = _direct_restart_sites()
    assert len(sites) >= len(_DIRECT_RESTARTS), "control: the finder sees the allow-listed sites"
    unlisted = [s for s in sites if s not in _DIRECT_RESTARTS]
    assert not unlisted, f"direct restarts that clear no start-limit park and are not on the allow-list: {unlisted}"


def test_the_allow_list_has_no_stale_entry() -> None:
    assert sorted(set(_DIRECT_RESTARTS) - set(_direct_restart_sites())) == []


# Every restart that tolerates failure, as (file, unit as written). Eight had `failed_when: false`
# on origin/main before the shared task (browser x2, frontend, slm_manager handlers; NPU, browser, AI Stack
# x2 in update-all-nodes.yml); four carried `ignore_errors: true` / `failed_when: false` in the TLS and
# certificate playbooks, and the logrotate-timer handler had `failed_when: false`; all keep that behaviour.
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
    ("roles/common/handlers/main.yml", "logrotate.timer"),
]


def test_exactly_the_sites_that_tolerated_failure_still_tolerate_it() -> None:
    found = []
    for path in _all_yaml():
        for node in _mappings(_load(path)):
            vars_ = node.get("vars") if _shared_include(node) else None
            if isinstance(vars_, dict) and vars_.get("restart_unit_tolerate_failure") is True:
                found.append((path.relative_to(_ANSIBLE).as_posix(), vars_["restart_unit_name"]))
    assert sorted(found) == sorted(_TOLERANT)
