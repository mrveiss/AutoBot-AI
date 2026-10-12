# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one SSH systemd-restart executor builds the command from its explicit parameters (#18186).

Its three callers' own behaviour is pinned in test_ssh_restart_equivalence_18186.py, which also
passes on the tree from before the executor existed. These tests need the executor itself.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import create_autospec

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
_real_orm = importlib.import_module("_real_orm_import")
SLM_ROOT, import_modules_with_real_orm = _real_orm.SLM_ROOT, _real_orm.import_modules_with_real_orm

(service_restart,) = import_modules_with_real_orm(
    (), path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"}
)

_BASE = ["ssh", "-p", "22", "u@h"]


class _Proc:
    returncode = 3

    async def communicate(self) -> tuple[bytes, bytes | None]:
        return b"out", b"err"


def _install(monkeypatch, expire: bool = False) -> dict:
    """Fake the spawn and the wait. Called IN the test body: tests/api/conftest.py's runtest hook
    blocks the real spawn at call time, and only a patch made inside the body wins over it."""
    seen: dict = {}

    async def _spawn(*argv, **kwargs):
        seen["argv"], seen["kwargs"] = list(argv), kwargs
        return _Proc()

    async def _wait_for(aw, timeout=None):
        seen["timeout"] = timeout
        if expire:
            aw.close()
            raise asyncio.TimeoutError
        return await aw

    spawn = create_autospec(asyncio.create_subprocess_exec, spec_set=True, side_effect=_spawn)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(asyncio, "wait_for", create_autospec(asyncio.wait_for, spec_set=True, side_effect=_wait_for))
    return seen


@pytest.mark.parametrize(
    ("sudo_n", "action", "units", "remote"),
    [
        (True, "restart", ["a", "b"], "sudo -n systemctl restart -- a b"),
        (False, "restart", ["a", "b"], "sudo systemctl restart -- a b"),
        (True, "stop", ["a"], "sudo -n systemctl stop -- a"),
        (False, "start", ["a"], "sudo systemctl start -- a"),
    ],
)
async def test_the_remote_command_follows_the_explicit_parameters(monkeypatch, sudo_n, action, units, remote):
    spawned = _install(monkeypatch)
    await service_restart.run_systemctl_over_ssh(_BASE, action, units, use_noninteractive_sudo=sudo_n, timeout=7)
    assert spawned["argv"] == [*_BASE, remote]
    assert spawned["timeout"] == 7


async def test_the_result_carries_the_exit_status_and_both_streams_for_the_caller_to_report(monkeypatch):
    spawned = _install(monkeypatch)
    result = await service_restart.run_systemctl_over_ssh(
        _BASE, "restart", ["a"], use_noninteractive_sudo=True, timeout=1
    )
    assert (result.returncode, result.stdout, result.stderr) == (3, b"out", b"err")
    assert spawned["kwargs"]["stderr"] == asyncio.subprocess.PIPE


async def test_merge_stderr_sends_stderr_to_stdout(monkeypatch):
    spawned = _install(monkeypatch)
    await service_restart.run_systemctl_over_ssh(
        _BASE, "restart", ["a"], use_noninteractive_sudo=False, timeout=1, merge_stderr=True
    )
    assert spawned["kwargs"]["stderr"] == asyncio.subprocess.STDOUT


async def test_a_timeout_propagates_to_the_caller(monkeypatch):
    _install(monkeypatch, expire=True)
    with pytest.raises(asyncio.TimeoutError):
        await service_restart.run_systemctl_over_ssh(_BASE, "restart", ["a"], use_noninteractive_sudo=True, timeout=1)


def test_the_node_ssh_command_is_the_base_plus_the_remote_command():
    node = type("N", (), {"ssh_user": None, "ssh_port": None, "ip_address": "h"})()
    base = service_restart.build_service_ssh_base_cmd(node)
    assert base[-1] == "autobot@h" and base[base.index("-p") + 1] == "22"
    assert service_restart.build_service_ssh_cmd(node, "x") == [*base, "x"]


# --- #18359: the unit and the action can never reach the remote shell unquoted ------------------

_BAD_UNITS = ["foo;id", "$(id)", "`id`", "a b", "-H", "--help", "a\nid", "../x", "a&&b", "a|b", "", "x" * 256]


@pytest.mark.parametrize("unit", _BAD_UNITS)
async def test_an_invalid_unit_name_is_refused_before_anything_is_spawned(monkeypatch, unit):
    spawned = _install(monkeypatch)
    with pytest.raises(ValueError):
        await service_restart.run_systemctl_over_ssh(
            _BASE, "restart", ["ok.service", unit], use_noninteractive_sudo=True, timeout=1
        )
    assert "argv" not in spawned


@pytest.mark.parametrize("unit", ["slm-agent", "getty@tty1.service", "a_b.c:d-e", "x" * 255])
async def test_a_valid_unit_name_passes_the_contrast(monkeypatch, unit):
    spawned = _install(monkeypatch)
    await service_restart.run_systemctl_over_ssh(_BASE, "start", [unit], use_noninteractive_sudo=True, timeout=1)
    assert spawned["argv"][-1] == f"sudo -n systemctl start -- {unit}"


@pytest.mark.parametrize("unit", ["foo;id", "$(id)", "`id`", "a b", "a\nid"])
async def test_the_executor_quotes_even_when_the_validator_is_bypassed(monkeypatch, unit):
    """Defence in depth: with the validator removed, ``shlex.quote`` alone keeps the unit one inert word."""
    import shlex

    spawned = _install(monkeypatch)
    monkeypatch.setattr(service_restart, "validate_unit_name", lambda u: u)
    await service_restart.run_systemctl_over_ssh(_BASE, "stop", [unit], use_noninteractive_sudo=False, timeout=1)
    remote = spawned["argv"][-1]
    assert remote == f"sudo systemctl stop -- {shlex.quote(unit)}"
    assert shlex.quote(unit) != unit
    assert shlex.split(remote)[-1] == unit  # the shell would read the whole unit as ONE argument


@pytest.mark.parametrize("action", ["enable", "restart; id", "--now", "", "RESTART", "is-active"])
async def test_a_non_allowlisted_action_raises(monkeypatch, action):
    spawned = _install(monkeypatch)
    with pytest.raises(ValueError):
        await service_restart.run_systemctl_over_ssh(_BASE, action, ["a"], use_noninteractive_sudo=True, timeout=1)
    assert "argv" not in spawned


@pytest.mark.parametrize("action", ["start", "stop", "restart", "status", "reload"])
async def test_every_allowlisted_action_is_accepted(monkeypatch, action):
    spawned = _install(monkeypatch)
    await service_restart.run_systemctl_over_ssh(_BASE, action, ["a"], use_noninteractive_sudo=True, timeout=1)
    assert spawned["argv"][-1] == f"sudo -n systemctl {action} -- a"


@pytest.mark.parametrize(("tolerate", "tail"), [(True, " || true"), (False, "")])
async def test_tolerate_failure_appends_exactly_or_true(monkeypatch, tolerate, tail):
    spawned = _install(monkeypatch)
    await service_restart.run_systemctl_over_ssh(
        _BASE, "restart", ["a"], use_noninteractive_sudo=False, timeout=1, tolerate_failure=tolerate
    )
    assert spawned["argv"][-1] == f"sudo systemctl restart -- a{tail}"


def test_the_executor_no_longer_accepts_a_raw_shell_suffix():
    import inspect

    assert "shell_suffix" not in inspect.signature(service_restart.run_systemctl_over_ssh).parameters
