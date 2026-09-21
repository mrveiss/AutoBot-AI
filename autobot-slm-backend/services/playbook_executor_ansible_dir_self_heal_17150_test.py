# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`PlaybookExecutor` cached `ansible_dir` forever at construction (#17150).

`PlaybookExecutor` is a module-level lazy singleton (`get_playbook_executor`):
constructed once per SLM backend process, on whichever API call first touches
it. Before this fix, `__init__` resolved `ansible_dir` once -- preferring
code_source's ansible directory, falling back to the deployed copy when that
directory did not exist YET -- and never looked again. A process that started
under the fallback (a host whose `code_source` checkout predated this ansible
subdirectory existing) stayed pinned to it for its entire lifetime, even after
`code_source` was brought fully current by some other means (the code-sync
API is the actual mechanism that populates `code_source`; `_update_code_source`
here is only a pre-playbook freshness safety net, not what creates it).
Restarting the process was the only way to re-resolve it.

The fix moves resolution into `_refresh_ansible_dir`, called at the top of
`execute_playbook`, so a fresh call re-detects the directory rather than
trusting the one from construction. It runs BEFORE `_update_code_source`, not
after: `_update_code_source` derives its OWN sync target from
`self.ansible_dir` (two directories up) -- syncing first against a stale
fallback would target the wrong directory too (`/opt/autobot`, which has no
`.git`, instead of `/opt/autobot/code_source`, which does), silently
reporting "nothing to sync" without ever touching the real checkout.

Like `playbook_executor_timeout_14524_test.py`, the module is loaded from
disk: the package conftest stubs `services.*`, and a plain `import
services.playbook_executor` would yield a MagicMock that passes every
assertion here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_playbook_executor():
    spec = importlib.util.spec_from_file_location(
        "playbook_executor_under_ansible_dir_self_heal_test", _SLM_ROOT / "services" / "playbook_executor.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_ansible_dir_self_heal_test"] = module
    spec.loader.exec_module(module)
    return module


playbook_executor = _load_real_playbook_executor()

_PLAYBOOK_BODY = "- hosts: all\n  tasks: []\n"


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(playbook_executor.PlaybookExecutor, MagicMock)
    assert hasattr(
        playbook_executor.PlaybookExecutor, "_refresh_ansible_dir"
    ), "pre-#17150 code has no refresh method at all -- this must fail fast against it, not silently pass"
    sig = inspect.signature(playbook_executor.PlaybookExecutor.execute_playbook)
    assert "playbook_name" in sig.parameters


def test_explicit_ansible_dir_is_never_refreshed(tmp_path):
    """A caller-supplied `ansible_dir` (tests, wizard provisioning) is a deliberate
    choice, never silently replaced by auto-detection on a later call."""
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    executor = playbook_executor.PlaybookExecutor(ansible_dir=explicit_dir)

    executor._refresh_ansible_dir()

    assert executor.ansible_dir == explicit_dir


def test_a_stale_fallback_makes_update_code_source_target_the_wrong_directory(tmp_path, monkeypatch):
    """Documents why refresh must run BEFORE `_update_code_source`, not after.

    While pinned to the fallback, `_update_code_source` derives its sync
    target as `self.ansible_dir.parent.parent` -- from the fallback, that is
    the installed tree's root, which has no `.git`, not code_source's root,
    which does. `_update_code_source` sees no `.git` and reports a no-op
    success (correctly, for the directory it was told to check) without ever
    looking at the real code_source checkout.
    """
    code_source_root = tmp_path / "code_source"
    (code_source_root / ".git").mkdir(parents=True)  # a REAL checkout exists here

    # A fallback candidate unrelated to code_source_root -- exactly the shape
    # of /opt/autobot/autobot-slm-backend/ansible -> /opt/autobot (no .git).
    fallback_dir = tmp_path / "installed" / "autobot-slm-backend" / "ansible"
    fallback_dir.mkdir(parents=True)
    monkeypatch.setattr(playbook_executor, "FALLBACK_ANSIBLE_DIR", fallback_dir)
    monkeypatch.setattr(
        playbook_executor, "DEFAULT_CODE_SOURCE_ANSIBLE_DIR", str(tmp_path / "code_source_ansible_missing")
    )

    executor = playbook_executor.PlaybookExecutor()
    assert executor.ansible_dir == fallback_dir  # pinned to fallback, pre-heal

    result = asyncio.run(executor._update_code_source())

    assert result is True, "reports success, but never examined code_source_root's real .git"
    assert not (executor.ansible_dir.parent.parent / ".git").exists()


def test_execute_playbook_self_heals_before_syncing_and_before_reading_paths(tmp_path, monkeypatch):
    """The core fix: a process constructed while code_source's ansible dir did
    not exist yet picks it up on its NEXT `execute_playbook` call, not only at
    construction -- proven through `execute_playbook` itself, so a future
    change that moves the refresh call to the wrong spot is also caught here.

    Negative control (verified by temporarily removing the
    `self._refresh_ansible_dir()` call in `execute_playbook` and re-running):
    pre-#17150, `execute_playbook` never re-checks `ansible_dir`, so the run
    below uses the stale `fallback_dir` throughout. Its `site.yml` lives ONLY
    under the fresh `code_source_ansible` directory, so the old code raises
    `FileNotFoundError` naming the STALE fallback path ("Playbook not
    found"), not the fresh path -- this test's final assertion inverts and
    fails against that code.
    """
    fallback_dir = tmp_path / "installed" / "ansible"
    fallback_dir.mkdir(parents=True)
    # No playbook of this name lives in the fallback -- a run that still used
    # it fails here, not at the (also-missing) inventory step below.

    code_source_ansible = tmp_path / "code_source" / "autobot-slm-backend" / "ansible"
    # Does not exist yet -- this instance falls back to fallback_dir at construction.

    monkeypatch.setattr(playbook_executor, "FALLBACK_ANSIBLE_DIR", fallback_dir)
    monkeypatch.setattr(playbook_executor, "DEFAULT_CODE_SOURCE_ANSIBLE_DIR", str(code_source_ansible))

    executor = playbook_executor.PlaybookExecutor()
    assert executor.ansible_dir == fallback_dir  # pinned to fallback, pre-heal

    # code_source's ansible dir "appears" mid-process-lifetime (the code-sync
    # API brought code_source current, independent of this executor). No
    # inventory dir here -- a correctly-refreshed run reaches the (also
    # missing) fresh inventory path, never the stale fallback playbook path.
    code_source_ansible.mkdir(parents=True)
    (code_source_ansible / "site.yml").write_text(_PLAYBOOK_BODY, encoding="utf-8")

    monkeypatch.setattr(
        playbook_executor.PlaybookExecutor,
        "_build_dynamic_inventory",
        AsyncMock(side_effect=RuntimeError("no db in this test -- execute_playbook's own except falls back")),
    )

    async def _go():
        return await executor.execute_playbook("site.yml")

    with pytest.raises(FileNotFoundError) as exc_info:
        asyncio.run(_go())

    message = str(exc_info.value)
    assert str(code_source_ansible) in message, "must fail on the FRESH inventory path, proving ansible_dir healed"
    assert str(fallback_dir) not in message, "must not still be looking at the stale fallback path"
