# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20767: a unit parked by its start limit restarts on the first attempt, whichever path restarts it.

Since #4090 and #20764 every long-running unit has a start limit, so a crash-looping unit parks in
`failed`. systemd then refuses start and restart ("start request repeated too quickly") until the
window passes. The reconciler has 3 attempts, 120 s apart, so refused attempts could exhaust it and
leave a Redis or PostgreSQL down for good. Every restart path now clears the park first, as the SLM
watchdog does.
"""

import importlib
import subprocess  # nosec B404 -- runs the built command against a fake systemctl
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
_real_orm = importlib.import_module("_real_orm_import")
# The conftest stubs `services`; load the real module, as test_ssh_restart_executor_18186 does.
(_service_restart,) = _real_orm.import_modules_with_real_orm(
    (), path_loaded={"services.service_restart": _real_orm.SLM_ROOT / "services" / "service_restart.py"}
)
systemctl_remote_command = _service_restart.systemctl_remote_command

_ROOT = Path(__file__).resolve().parents[2]

#: A systemctl that behaves like systemd at the start limit: a parked unit refuses start/restart
#: until `reset-failed` clears it.
_FAKE_SYSTEMCTL = """#!/bin/sh
state="$FAKE_STATE"
[ "$1" = "--user" ] && shift
action="$1"; shift; [ "$1" = "--" ] && shift
case "$action" in
  reset-failed) rm -f "$state.parked"; exit 0 ;;
  start|restart)
    if [ -e "$state.parked" ]; then echo "start request repeated too quickly" >&2; exit 1; fi
    echo active > "$state.active"; exit 0 ;;
  *) exit 0 ;;
esac
"""


def _run(command: str, tmp_path: Path) -> tuple[int, bool]:
    """Run a built remote line against the fake, with the unit parked; (exit status, active after)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "systemctl"
    fake.write_text(_FAKE_SYSTEMCTL, encoding="utf-8")
    fake.chmod(0o755)
    state = tmp_path / "unit"
    (tmp_path / "unit.parked").write_text("", encoding="utf-8")
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_STATE": str(state)}
    proc = subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True, timeout=30, check=False)
    return proc.returncode, (tmp_path / "unit.active").exists()


@pytest.mark.parametrize("action", ["start", "restart"])
def test_a_parked_unit_starts_on_the_first_attempt(tmp_path: Path, action: str) -> None:
    """The line every SSH path builds (the UI's service actions, the fleet route, roles, post-sync)."""
    command = systemctl_remote_command(action, ["autobot-redis.service"], user_scope=True)
    assert _run(command, tmp_path) == (0, True)


def test_control_without_the_reset_a_parked_unit_is_refused(tmp_path: Path) -> None:
    """The fake refuses a parked unit, so the passing test above is the reset at work, not the fake."""
    assert _run("systemctl --user restart -- autobot-redis.service", tmp_path) == (1, False)


@pytest.mark.parametrize("action", ["stop", "status", "reload"])
def test_only_start_and_restart_clear_the_park(action: str) -> None:
    """Stopping or reading a failed unit must not erase the `failed` state an operator is looking at."""
    assert "reset-failed" not in systemctl_remote_command(action, ["u.service"])


def test_the_reset_keeps_the_actions_own_exit_status() -> None:
    """`;`, not `&&`: a reset that fails (an unknown unit) still lets the action run and report."""
    line = systemctl_remote_command("restart", ["u.service"], use_noninteractive_sudo=True)
    assert line == "sudo -n systemctl reset-failed -- u.service 2>/dev/null; sudo -n systemctl restart -- u.service"


def test_the_ansible_path_clears_the_park_before_the_state_change() -> None:
    """manage-service.yml: the reconciler's remediation and the orchestration UI's per-role actions."""
    play = yaml.safe_load((_ROOT / "ansible" / "manage-service.yml").read_text(encoding="utf-8"))[0]
    tasks = play["tasks"]
    names = [t.get("name", "") for t in tasks]
    reset = next(i for i, n in enumerate(names) if "Clear a start-limit park" in n)
    state = next(i for i, t in enumerate(tasks) if "block" in t and t.get("name") == "Manage service state")
    assert reset < state
    task = tasks[reset]
    assert task["ansible.builtin.command"]["argv"] == ["systemctl", "reset-failed", "--", "{{ service_name }}"]
    assert task["when"] == "service_action in ['started', 'restarted']"
    assert task["failed_when"] is False and play["become"] is True
