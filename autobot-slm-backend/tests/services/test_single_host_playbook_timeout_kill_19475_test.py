# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""run_single_host_playbook kills a hung run's whole process group before re-raising (#19475).

asyncio.wait_for abandons communicate() on timeout but leaves the child running, and ansible
forks ssh workers that a pid-only kill would orphan. A real shell that backgrounds a sleeper
stands in for ansible-playbook, so the group-wide kill is exercised against real processes.
"""

import asyncio
import os

import pytest

from services import ansible_utils, process_group

_REAL_EXEC = asyncio.create_subprocess_exec


def _hung_ansible(spawned):
    async def _exec(*_argv, **kwargs):
        assert kwargs.get("start_new_session") is True, "the run needs its own process group"
        process = await _REAL_EXEC("sh", "-c", "sleep 60 & sleep 60", **kwargs)
        spawned.append(process)
        return process

    return _exec


@pytest.mark.asyncio
async def test_a_timed_out_run_leaves_no_process_behind(monkeypatch, tmp_path):
    spawned = []
    monkeypatch.setattr(ansible_utils.asyncio, "create_subprocess_exec", _hung_ansible(spawned))
    monkeypatch.setattr(process_group, "KILL_GRACE_S", 0.3)

    with pytest.raises(asyncio.TimeoutError):
        await ansible_utils.run_single_host_playbook(tmp_path, tmp_path / "p.yml", "node", "u", 22, timeout=0.3)

    assert await process_group.wait_for_process_group_death(spawned[0].pid, 2.0), "the sleeper outlived the kill"


@pytest.mark.asyncio
async def test_a_cancelled_run_is_killed_too(monkeypatch, tmp_path):
    spawned = []
    monkeypatch.setattr(ansible_utils.asyncio, "create_subprocess_exec", _hung_ansible(spawned))
    task = asyncio.create_task(
        ansible_utils.run_single_host_playbook(tmp_path, tmp_path / "p.yml", "node", "u", 22, timeout=30)
    )
    while not spawned:
        await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process_group.process_group_is_dead(spawned[0].pid) or await process_group.wait_for_process_group_death(
        spawned[0].pid, 2.0
    )
    assert os.getpgid(os.getpid()) != spawned[0].pid, "the test runner is not in the killed group"
