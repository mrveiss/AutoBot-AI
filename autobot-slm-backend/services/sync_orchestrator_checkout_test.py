# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The checkout that returns a detached code_source to its branch is bounded, hook and all (#20214)."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest

from autobot_shared.eventually import eventually
from autobot_shared.isolated_git import git, make_repo

# The root conftest stubs ``services.sync_orchestrator`` (an api/code_sync.py import); load the real module
# and put the stub back (the pattern of tests/services/test_sync_orchestrator_ssh.py, #11737).
_KEY = "services.sync_orchestrator"
_stub = sys.modules.pop(_KEY, None)
try:
    so = importlib.import_module(_KEY)
finally:
    if _stub is not None:
        sys.modules[_KEY] = _stub
    else:
        sys.modules.pop(_KEY, None)


def _detached_repo(tmp_path: Path, hook: str | None) -> Path:
    root = make_repo(tmp_path / "code_source")
    (root / "a.txt").write_text("a", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "one")
    git(root, "checkout", "-q", "--detach", "HEAD")
    if hook:
        path = root / ".git" / "hooks" / "post-checkout"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(hook, encoding="utf-8")
        path.chmod(0o755)
    return root


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_a_detached_head_is_put_back_on_the_branch(tmp_path):
    root = _detached_repo(tmp_path, hook=None)
    await so.SyncOrchestrator.__new__(so.SyncOrchestrator)._return_to_branch(str(root), "main")
    assert git(root, "symbolic-ref", "-q", "HEAD").stdout.strip() == "refs/heads/main"


async def test_a_hung_checkout_hook_is_killed_with_git_not_orphaned(tmp_path, monkeypatch):
    pid_file = tmp_path / "hook-child.pid"
    root = _detached_repo(tmp_path, hook=f"#!/bin/sh\nsleep 300 &\necho $! > {pid_file}\nwait\n")
    monkeypatch.setattr(so, "BRANCH_CHECKOUT_TIMEOUT_S", 1.0)
    with pytest.raises(asyncio.TimeoutError):
        await so.SyncOrchestrator.__new__(so.SyncOrchestrator)._return_to_branch(str(root), "main")
    child = int(await asyncio.to_thread(pid_file.read_text, encoding="utf-8"))
    await eventually(lambda: not _alive(child), deadline=10)
    assert not _alive(child), "the hook's child outlived the timed-out checkout"
