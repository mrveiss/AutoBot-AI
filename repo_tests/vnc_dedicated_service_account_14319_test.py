# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025-2026 mrveiss
# Author: mrveiss
"""VNC runs under its own dedicated account, and the emergency admin account
is rejected outright, whatever the default is (#14319).

Before this fix, `vnc_user` defaulted to `autobot` -- the SSH/ansible
operational identity -- and nothing stopped an operator from setting
`VNC_USER=autobot_admin`, the emergency safety-net account that
`rotate-ssh-keys.yml` deliberately never touches.

Static only: `ansible-playbook` is never invoked here -- the role provisions
real accounts and sudoers-adjacent state. These tests parse the role's YAML
and the fix-vnc-*.sh scripts, and evaluate the actual guard EXPRESSIONS they
encode (not just their source text) against both an accepted and a rejected
account name, so a test that only checked the happy path would not pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
VNC_ROLE = REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "vnc"
DEFAULTS = VNC_ROLE / "defaults" / "main.yml"
TASKS = VNC_ROLE / "tasks" / "main.yml"
FIX_VNC_SCRIPTS = (
    REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "utilities" / "fix-vnc-desktop.sh",
    REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "utilities" / "fix-vnc-wsl.sh",
)

_EMERGENCY_ACCOUNT = "autobot_" + "admin"


def _load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS.read_text(encoding="utf-8"))


def _find_task(tasks: list[dict], name_fragment: str) -> dict:
    for task in tasks:
        if name_fragment in task.get("name", ""):
            return task
    raise AssertionError(f"no task found containing {name_fragment!r}")


def test_default_account_is_dedicated_not_shared():
    text = DEFAULTS.read_text(encoding="utf-8")
    match = re.search(r"vnc_user:.*default\('([^']+)',\s*true\)", text)
    assert match, "vnc_user default() argument not found"
    assert match.group(1) == "autobot-vnc"
    # never the SSH/ansible operational identity
    assert match.group(1) != "autobot"


def test_forbidden_user_is_the_emergency_admin_account():
    values = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert values["vnc_forbidden_user"] == _EMERGENCY_ACCOUNT


def test_reject_task_denies_the_emergency_admin_account_and_permits_the_default():
    """Evaluate the assert task's actual `that` expression, not its text."""
    tasks = _load_tasks()
    reject_task = _find_task(tasks, "Reject the emergency admin account")
    condition = reject_task["ansible.builtin.assert"]["that"][0]
    assert condition == "vnc_user != vnc_forbidden_user"

    def evaluate(vnc_user: str) -> bool:
        # eval() over a fixed, hand-written boolean expression from this
        # repo's own tracked YAML -- not attacker input.
        return eval(condition, {"__builtins__": {}}, {"vnc_user": vnc_user, "vnc_forbidden_user": _EMERGENCY_ACCOUNT})  # nosec B307

    assert evaluate("autobot-vnc") is True, "the default account must be permitted"
    assert evaluate(_EMERGENCY_ACCOUNT) is False, "the emergency admin account must be denied"


def test_reject_task_runs_before_the_account_is_created():
    tasks = _load_tasks()
    names = [t.get("name", "") for t in tasks]
    reject_idx = next(i for i, n in enumerate(names) if "Reject the emergency admin account" in n)
    create_idx = next(i for i, n in enumerate(names) if n == "Create VNC user if not exists")
    assert reject_idx < create_idx, "the account must never be created before the rejection check runs"


def test_account_is_the_documented_exception_of_home_only_not_shell():
    """PR #14412 review round 2, finding 3: systemd's User= never consults
    /etc/passwd's shell field, and xstartup.j2 carries its own #!/bin/bash
    shebang -- so nologin is safe, and create_home is the only real
    deviation from the other per-service accounts (roles/npu-worker,
    roles/tts-worker)."""
    tasks = _load_tasks()
    create_task = _find_task(tasks, "Create VNC user if not exists")
    user_module = create_task["ansible.builtin.user"]
    assert user_module["system"] is True
    assert user_module["create_home"] is True
    assert user_module["shell"] == "/usr/sbin/nologin"
    assert user_module["shell"] != "/bin/bash"
    assert user_module["group"] == "{{ vnc_group }}"


def test_group_is_created_explicitly_not_left_to_the_distro_default():
    """PR #14412 review round 2: an explicit group task, not implicit
    same-named-group creation, which depends on the host's USERGROUPS_ENAB
    default that the later ownership tasks (chown-equivalent `file` tasks)
    silently rely on."""
    tasks = _load_tasks()
    names = [t.get("name", "") for t in tasks]
    group_idx = next(i for i, n in enumerate(names) if "Create autobot-vnc system group" in n)
    create_idx = next(i for i, n in enumerate(names) if n == "Create VNC user if not exists")
    assert group_idx < create_idx, "the group must exist before the user references it"
    group_task = _find_task(tasks, "Create autobot-vnc system group")
    assert group_task["ansible.builtin.group"]["name"] == "{{ vnc_group }}"


def test_migration_moves_state_before_it_would_be_recreated_empty():
    tasks = _load_tasks()
    names = [t.get("name", "") for t in tasks]
    create_idx = next(i for i, n in enumerate(names) if n == "Create VNC user if not exists")
    migrate_idx = next(i for i, n in enumerate(names) if "Migrate legacy VNC state" in n)
    config_dir_idx = next(i for i, n in enumerate(names) if n == "Create VNC configuration directory")
    assert create_idx < migrate_idx < config_dir_idx, (
        "migration must run after the new account exists but before the config-dir "
        "task would unconditionally (re)create an empty target directory"
    )
    migrate_task = _find_task(tasks, "Migrate legacy VNC state")
    # #14412 review round 2, finding 5: a substring check on "vnc_legacy_user"
    # stays green even if source and destination are swapped -- the actual
    # data-loss bug (mv the NEW account's state onto the OLD one). Pin the
    # full command, and pin which path comes first.
    cmd = migrate_task["ansible.builtin.command"]["cmd"]
    assert cmd == "mv /home/{{ vnc_legacy_user }}/.vnc /home/{{ vnc_user }}/.vnc"
    src_pos = cmd.index("vnc_legacy_user")
    dest_pos = cmd.index("vnc_user }}")
    assert src_pos < dest_pos, "vnc_legacy_user must be the mv SOURCE, vnc_user the DESTINATION"


def test_fix_vnc_scripts_reject_the_emergency_admin_account():
    guard_re = re.compile(
        r'if \[ "\$\{VNC_USER\}" = "' + re.escape(_EMERGENCY_ACCOUNT) + r'" \]; then\n(.*?)\nfi',
        re.DOTALL,
    )
    for script in FIX_VNC_SCRIPTS:
        text = script.read_text(encoding="utf-8")
        match = guard_re.search(text)
        assert match, f"{script.name}: no rejection guard found for {_EMERGENCY_ACCOUNT}"
        assert "exit 1" in match.group(1), f"{script.name}: guard does not actually reject"
        # the default must also have moved off the shared operational account
        assert 'VNC_USER="autobot-vnc"' in text
        assert 'VNC_USER="autobot"' not in text


def test_fix_vnc_scripts_refuse_to_run_against_a_missing_account():
    for script in FIX_VNC_SCRIPTS:
        text = script.read_text(encoding="utf-8")
        assert 'if ! id "${VNC_USER}" &>/dev/null; then' in text
        assert "exit 1" in text
