# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression guard for clear-text storage of the Redis replication password.

Issue #12283 / CodeQL alert #993 (py/clear-text-storage-sensitive-data):
``_run_ansible_replication`` previously embedded the Redis password directly
into the ad-hoc Ansible playbook written to disk. These tests prove the
plaintext credential is NEVER written to the playbook file and is instead
passed to the ansible-playbook subprocess through the environment.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Load the REAL services.replication (#12283) ──────────────────────────────
# The slm-backend root conftest stubs ``services.replication`` as a MagicMock
# (it is an api import); pop the stub, import the real module through the
# hollow ``services`` package, then restore the stub for sibling tests.
_REPL_KEY = "services.replication"
_orig_repl = sys.modules.get(_REPL_KEY)
sys.modules.pop(_REPL_KEY, None)
try:
    _repl_mod = importlib.import_module(_REPL_KEY)
finally:
    if _orig_repl is not None:
        sys.modules[_REPL_KEY] = _orig_repl
    else:
        sys.modules.pop(_REPL_KEY, None)

ReplicationService = _repl_mod.ReplicationService

_SECRET_PW = "S3cr3t-Replica-Pw-12283"


def _service(tmp_path: Path) -> "ReplicationService":
    # __new__ skips __init__ (which only builds ansible_dir from settings);
    # the ansible runner does not touch other instance state.
    svc = ReplicationService.__new__(ReplicationService)
    svc.ansible_dir = tmp_path
    return svc


async def _run_capture(tmp_path: Path) -> dict:
    """Invoke _run_ansible_replication with a mocked subprocess and capture
    the playbook-file content (while it exists) plus the subprocess env."""
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        # args: ("ansible-playbook", "<playbook_path>", "-i", ...)
        playbook_path = Path(args[1])
        captured["content"] = playbook_path.read_text(encoding="utf-8")
        captured["env"] = kwargs.get("env")
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", None))
        proc.returncode = 0
        return proc

    with patch.object(_repl_mod.asyncio, "create_subprocess_exec", new=fake_exec):
        captured["result"] = await _service(tmp_path)._run_ansible_replication(
            target_ip="10.0.0.5",
            ssh_user="autobot",
            ssh_port=22,
            master_ip="10.0.0.1",
            redis_password=_SECRET_PW,
        )
    return captured


@pytest.mark.asyncio
async def test_password_not_written_to_playbook_file(tmp_path):
    """The plaintext Redis password must never appear in the on-disk playbook."""
    captured = await _run_capture(tmp_path)
    assert _SECRET_PW not in captured["content"], "plaintext password leaked into playbook file"
    # Indirection marker: the file references the env var, not the value.
    assert "lookup('env', 'AUTOBOT_REDIS_REPL_AUTH')" in captured["content"]


@pytest.mark.asyncio
async def test_password_passed_via_environment(tmp_path):
    """The credential must reach ansible via the subprocess environment."""
    captured = await _run_capture(tmp_path)
    assert captured["env"] is not None, "subprocess env not supplied"
    assert captured["env"]["AUTOBOT_REDIS_REPL_AUTH"] == _SECRET_PW
    assert captured["result"] is True


@pytest.mark.asyncio
async def test_nonsensitive_master_ip_still_templated(tmp_path):
    """Non-sensitive master IP is still interpolated into the playbook."""
    captured = await _run_capture(tmp_path)
    assert "10.0.0.1" in captured["content"]


@pytest.mark.asyncio
async def test_temp_playbook_is_cleaned_up(tmp_path):
    """The temp playbook must be removed after the run (no lingering file)."""
    await _run_capture(tmp_path)
    assert not (tmp_path / "temp_replication.yml").exists()
