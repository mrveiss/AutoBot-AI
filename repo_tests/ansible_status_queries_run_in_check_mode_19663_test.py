# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A read-only status query in an Ansible task runs in check mode (#19663).

Under `ansible-playbook --check` a `command`/`shell` task is skipped and registers no
`stdout`, so a later `when:` that reads the result fails with an undefined attribute and
the dry run dies at the probe instead of reporting what it would change. A query reads
state and changes nothing, so it is safe in check mode: it carries `check_mode: false`
(run it anyway) and `changed_when: false` (it never reports a change).

The exception is a verify-after-install query (`<bin> --version`, `systemctl is-active` AFTER the
install or start it checks). Under `--check` that install is skipped, so on an unprovisioned host
the query would FAIL the dry run if forced to run. It is marked `when: not ansible_check_mode`
(alone or as one element of a `when:` list), still carries `changed_when: false`, and must not
carry `check_mode: false`. The rule: a query whose registered result decides a later task is a
probe (`check_mode: false`); a query that only confirms the outcome of an earlier task is a verify.

The queries are `dpkg-query`, `apt-cache policy`, `systemctl is-active|is-enabled`,
`<binary> --version` and `rpm -q`. Only a command that STARTS with one is a query: a
mutating task is never given `check_mode: false` (`apt`, `systemctl start`, or a command
that chains a second command after the query).

Detection lives in `repo_tests/_ansible_query_tasks.py`. Deliberately not matched, and
left alone: compound shell (`if ...; then ... --version ...`) and `<query> && <mutation>`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._ansible_query_tasks import (
    has_check_mode_off,
    is_check_safe,
    is_status_query,
    is_verify_after_install,
    marked_verify_read_unguarded,
    query_tasks,
)
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_TREE = "autobot-slm-backend/ansible"


def _ansible_yaml(root: Path) -> list[Path]:
    """Tracked YAML under the SLM ansible tree; ``[]`` on an empty tree (never raises)."""
    try:
        tracked = tracked_paths(root, _TREE)
    except EmptyEnumeration:
        return []
    return [root / rel for rel in tracked if rel.endswith((".yml", ".yaml"))]


#: 346 tracked YAML files measured at declaration; ``growth`` because roles add task files steadily.
REACH = declare(
    "ansible-status-queries-check-mode-sweep",
    discover=_ansible_yaml,
    floor=330,
    growth=40,
    skips=0,
    what="Ansible YAML files",
    roots=(_TREE,),
)

_QUERY_COMMANDS = (
    "dpkg-query -W --showformat=${Status} nginx",
    "apt-cache policy grafana",
    "systemctl is-active nginx",
    "systemctl is-enabled nginx",
    "node --version",
    "{{ venv }}/bin/python --version",
    "rpm -q nginx",
)


def _task(command: str, module: str = "ansible.builtin.command", **extra: object) -> dict:
    return {"name": "probe", module: {"cmd": command}, **extra}


#: Probe sites that must always be found: a detector that stops matching one of them (for example the
#: backslash-continued `dpkg-query` shell task) would otherwise leave the sweep green over fewer tasks.
_KNOWN_SITES = (
    ("check-system-updates.yml", "Resolve installed versions for ESM packages via dpkg-query"),
    ("roles/postgresql/tasks/install.yml", "Check if PostgreSQL is already installed"),
    ("roles/redis/tasks/main.yml", "Check if Redis Stack is already installed"),
    ("playbooks/disable-idle-nginx.yml", "Check if nginx is installed"),
    ("roles/monitoring/tasks/grafana_install.yml", "Read the installed Grafana"),
    ("roles/agent_config/tasks/nodejs.yml", "Verify Node.js installation"),
)
#: 31 queries measured at declaration (19 probes plus 12 marked verifies), 29 once #19661 folded three
#: Grafana probes into one; a drop means the detector lost some.
_QUERY_FLOOR = 29


def test_every_status_query_runs_in_check_mode() -> None:
    """Each query is a `check_mode: false` probe or a `when: not ansible_check_mode` verify."""
    scanned = REACH.examined(repo_root())
    missing: list[str] = []
    found: set[tuple[str, str]] = set()
    count = 0
    for path in scanned:
        rel = str(path.relative_to(repo_root()))
        for task in query_tasks(path.read_text(encoding="utf-8")):
            count += 1
            found.add((rel, str(task.get("name"))))
            if not is_check_safe(task):
                missing.append(f"{rel}: {task.get('name')}")
    assert count >= _QUERY_FLOOR, f"the detector found {count} status queries, expected >= {_QUERY_FLOOR}"
    lost = [site for site in _KNOWN_SITES if not any(r.endswith(site[0]) and site[1] in n for r, n in found)]
    assert not lost, f"the detector stopped matching known query sites: {lost}"
    assert not missing, (
        "these read-only status queries are skipped under --check, so a dry run dies at the task that reads "
        "them; a probe needs `check_mode: false` + `changed_when: false`, a verify-after-install needs "
        "`when: not ansible_check_mode` + `changed_when: false` (#19663):\n  " + "\n  ".join(missing)
    )


@pytest.mark.parametrize("command", _QUERY_COMMANDS)
@pytest.mark.parametrize("module", ["command", "shell", "ansible.builtin.command", "ansible.builtin.shell"])
def test_a_query_without_check_mode_is_flagged(command: str, module: str) -> None:
    """Contrast: a query lacking `check_mode: false` is a query and is not accepted."""
    task = _task(command, module, changed_when=False)
    assert is_status_query(task)
    assert not has_check_mode_off(task)


@pytest.mark.parametrize("command", _QUERY_COMMANDS)
def test_a_query_with_check_mode_off_is_accepted(command: str) -> None:
    """Contrast: the fixed spelling passes."""
    assert has_check_mode_off(_task(command, check_mode=False, changed_when=False))


def test_check_mode_without_changed_when_is_flagged() -> None:
    """Both keys are required: `changed_when: false` is what keeps the query out of the change count."""
    assert not has_check_mode_off(_task("node --version", check_mode=False))


@pytest.mark.parametrize(
    "task",
    [
        {"name": "install", "ansible.builtin.apt": {"name": "nginx", "state": "present"}},
        {"name": "start", "ansible.builtin.systemd": {"name": "nginx", "state": "started"}},
        _task("systemctl start nginx"),
        _task("systemctl restart nginx"),
        _task("apt-get install -y nginx"),
        _task("systemctl is-active nginx && systemctl reload nginx"),
        _task("dpkg-query -W nginx; apt-get install -y nginx"),
        _task("dpkg-query -W nginx\napt-get install -y nginx"),
        _task("dpkg-query -W | xargs apt-get remove"),
        _task("systemctl is-active nginx &"),
    ],
    ids=[
        "apt",
        "systemd-start",
        "systemctl-start",
        "systemctl-restart",
        "apt-get",
        "chained-reload",
        "chained-install",
        "newline-chained",
        "pipe-to-xargs",
        "backgrounded",
    ],
)
def test_a_mutating_task_is_not_a_query(task: dict) -> None:
    """Contrast: a mutating task is ignored, so it is never handed `check_mode: false`."""
    assert not is_status_query(task)


def test_queries_are_found_in_nested_blocks() -> None:
    """A query inside `block:` is found, so grouping tasks does not hide one."""
    text = "- hosts: all\n  tasks:\n    - block:\n        - name: q\n          command: node --version\n"
    assert [t["name"] for t in query_tasks(text)] == ["q"]


@pytest.mark.parametrize(
    "command",
    [
        "dpkg-query -W -f='${Package}=${Version}\\n' \\\n  nginx \\\n  2>/dev/null || true",
        "dpkg-query -W nginx 2>/dev/null || true",
        "{{ venv }}/bin/python3 --version 2>/dev/null | grep -oP '\\d+\\.\\d+'",
        "rpm -q nginx | head -1",
    ],
    ids=["backslash-continued-or-true", "or-true", "read-only-filter", "head-filter"],
)
def test_accepted_spellings_are_still_queries(command: str) -> None:
    """Positive fixtures: the continuation, `|| true` and read-only-filter forms in the tree are found."""
    assert is_status_query(_task(command, "ansible.builtin.shell"))


def test_a_verify_after_install_is_marked_not_forced_into_check_mode() -> None:
    """A verify is accepted with the marker and `changed_when: false`, and refused with `check_mode: false`."""
    marked = _task("node --version", when="not ansible_check_mode", changed_when=False)
    assert is_verify_after_install(marked) and is_check_safe(marked)
    in_list = _task("node --version", when=["install_nodejs", "not ansible_check_mode"], changed_when=False)
    assert is_check_safe(in_list)
    assert not is_check_safe(_task("node --version", when="not ansible_check_mode"))
    assert not is_check_safe(
        _task("node --version", when="not ansible_check_mode", changed_when=False, check_mode=False)
    )
    assert not is_check_safe(_task("node --version", when="install_nodejs", changed_when=False))


def test_no_marked_verify_has_a_reader_that_breaks_under_check() -> None:
    """The marker is only true of a query nothing later depends on (#19883)."""
    found = {
        str(path.relative_to(repo_root())): names
        for path in REACH.examined(repo_root())
        if (names := marked_verify_read_unguarded(path.read_text(encoding="utf-8")))
    }
    assert not found, f"a marked verify's result is read unguarded, so `--check` dies at the reader: {found}"


_VERIFY = """
- name: v
  command: node --version
  register: v_out
  when: not ansible_check_mode
  changed_when: false
"""


@pytest.mark.parametrize(
    ("reader", "names"),
    [
        ("- name: r\n  debug: {msg: x}\n  when: v_out.rc == 0\n", ["v_out"]),
        ("- name: r\n  debug: {msg: '{{ v_out.stdout }}'}\n", ["v_out"]),
        ("- name: r\n  debug: {msg: '{{ v_out.stdout | default(\"\") }}'}\n", []),
        ("- name: r\n  debug: {msg: x}\n  when: v_out is defined and v_out.rc == 0\n", []),
        ("- name: r\n  debug: {msg: \"{{ 'x' if v_out.rc is not defined else v_out.rc }}\"}\n", []),
        ("- name: r\n  debug: {msg: '{{ v_out.stdout }}'}\n  when: not ansible_check_mode\n", []),
        ("- name: r\n  debug: {msg: unrelated}\n", []),
    ],
    ids=["when-read", "template-read", "default", "is-defined", "is-not-defined", "reader-also-marked", "no-read"],
)
def test_a_marked_verify_may_not_decide_a_later_task(reader: str, names: list[str]) -> None:
    assert marked_verify_read_unguarded(_VERIFY + reader) == names


def test_a_read_inside_a_block_is_seen() -> None:
    text = _VERIFY + "- block:\n    - name: r\n      debug: {msg: x}\n      when: v_out.rc == 0\n"
    assert marked_verify_read_unguarded(text) == ["v_out"]


def test_the_marker_with_check_mode_off_is_rejected() -> None:
    """The contradiction: the marker says skip under `--check`, `check_mode: false` says run."""
    both = _task("node --version", when="not ansible_check_mode", check_mode=False, changed_when=False)
    assert is_verify_after_install(both) and not is_check_safe(both)


def test_contrast_the_marker_alone_passes() -> None:
    assert is_check_safe(_task("node --version", when="not ansible_check_mode", changed_when=False))
