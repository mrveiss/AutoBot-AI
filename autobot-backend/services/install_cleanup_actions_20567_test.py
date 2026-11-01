# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: .env.*~ copies and the stale directory go only after approval, by server-computed paths."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import approval_execution
from services import install_cleanup_actions as acts

_ADMIN, _OTHER = uuid.uuid4(), uuid.uuid4()
_SECRET = "SECRET-VALUE-MUST-NOT-APPEAR"  # pragma: allowlist secret


def _session(admins: int = 2) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: admins))
    return session


def _approval(action: str, decider=_OTHER, context: dict | None = None) -> SimpleNamespace:
    approval = SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="owner",
        context=context or {"action": action},
        requested_by_agent=f"cleanup-proposal:{_ADMIN}",
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


def _make_env(root: Path, mtimes: dict[str, int]) -> Path:
    backend = root / "autobot-backend"
    backend.mkdir(parents=True)
    (backend / ".env").write_text(_SECRET, encoding="utf-8")
    for name, mtime in mtimes.items():
        path = backend / name
        path.write_text(_SECRET, encoding="utf-8")
        os.utime(path, (mtime, mtime))
    return backend


def _names(backend: Path) -> list[str]:
    return sorted(p.name for p in backend.iterdir())


async def _run(handler, approval, root: Path, session=None) -> MagicMock:
    audit = AsyncMock()
    with patch.object(acts, "install_root", return_value=root), patch.object(acts, "audit_log", audit):
        await handler(approval, session or _session())
    return audit


async def test_env_copies_keep_only_the_newest(tmp_path: Path) -> None:
    backend = await asyncio.to_thread(_make_env, tmp_path, {".env.1~": 100, ".env.3~": 300, ".env.2~": 200})
    session = _session()
    audit = await _run(acts.execute_env_copies_cleanup, _approval(acts.ENV_COPIES_ACTION), tmp_path, session)
    assert await asyncio.to_thread(_names, backend) == [".env", ".env.3~"]
    details = audit.await_args.kwargs["details"]
    assert audit.await_args.kwargs["result"] == "success" and details["removed"] == 2
    assert _SECRET not in repr(audit.await_args_list) and _SECRET not in session.add.call_args.args[0].body


async def test_nothing_to_do_removes_nothing(tmp_path: Path) -> None:
    backend = await asyncio.to_thread(_make_env, tmp_path, {".env.1~": 100})
    session = _session()
    await _run(acts.execute_env_copies_cleanup, _approval(acts.ENV_COPIES_ACTION), tmp_path, session)
    assert await asyncio.to_thread(_names, backend) == [".env", ".env.1~"]
    assert "Nothing to remove" in session.add.call_args.args[0].body


async def test_a_symlinked_copy_refuses_and_removes_nothing(tmp_path: Path) -> None:
    backend = await asyncio.to_thread(_make_env, tmp_path, {".env.1~": 100, ".env.2~": 200})
    outside = tmp_path / "outside.txt"
    await asyncio.to_thread(outside.write_text, "x", encoding="utf-8")
    await asyncio.to_thread((backend / ".env.3~").symlink_to, outside)
    audit = AsyncMock()
    with patch.object(acts, "install_root", return_value=tmp_path), patch.object(acts, "audit_log", audit):
        with pytest.raises(ValueError, match="symlink"):
            await acts.execute_env_copies_cleanup(_approval(acts.ENV_COPIES_ACTION), _session())
    assert await asyncio.to_thread(_names, backend) == [".env", ".env.1~", ".env.2~", ".env.3~"]
    assert await asyncio.to_thread(outside.exists)
    assert audit.await_args.kwargs["result"] == "denied"


async def test_a_context_path_is_ignored(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    await asyncio.to_thread(victim.mkdir)
    approval = _approval(acts.INFRA_DIR_ACTION, context={"action": acts.INFRA_DIR_ACTION, "path": str(victim)})
    await _run(acts.execute_infrastructure_dir_removal, approval, tmp_path)
    assert await asyncio.to_thread(victim.exists)


def _make_infra(root: Path, git: bool = False) -> Path:
    (root / "code_source" / acts.INFRA_DIR_NAME).mkdir(parents=True)
    infra = root / "autobot-infrastructure"
    (infra / "sub").mkdir(parents=True)
    (infra / "sub" / "a.txt").write_text(_SECRET, encoding="utf-8")
    (infra / "b.txt").write_text(_SECRET, encoding="utf-8")
    if git:
        (infra / ".git").mkdir()
    return infra


async def test_stale_directory_is_removed_after_approval(tmp_path: Path) -> None:
    infra = await asyncio.to_thread(_make_infra, tmp_path)
    audit = await _run(acts.execute_infrastructure_dir_removal, _approval(acts.INFRA_DIR_ACTION), tmp_path)
    assert not await asyncio.to_thread(infra.exists)
    assert audit.await_args.kwargs["details"]["removed"] == 2


async def test_without_approval_nothing_changes(tmp_path: Path) -> None:
    infra = await asyncio.to_thread(_make_infra, tmp_path)
    plan = await asyncio.to_thread(acts.plan_infrastructure_dir, tmp_path)
    assert plan.count == 1 and await asyncio.to_thread(infra.exists)
    unverified = _approval(acts.INFRA_DIR_ACTION, decider=None)
    with pytest.raises(ValueError):
        await _run(acts.execute_infrastructure_dir_removal, unverified, tmp_path)
    assert await asyncio.to_thread(infra.exists)


async def test_a_checkout_is_refused(tmp_path: Path) -> None:
    infra = await asyncio.to_thread(_make_infra, tmp_path, True)
    with pytest.raises(ValueError, match=r"\.git"):
        await _run(acts.execute_infrastructure_dir_removal, _approval(acts.INFRA_DIR_ACTION), tmp_path)
    assert await asyncio.to_thread(infra.exists)


async def test_a_symlinked_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere"
    root = tmp_path / "root"
    await asyncio.to_thread(real.mkdir)
    await asyncio.to_thread(root.mkdir)
    await asyncio.to_thread((root / "autobot-infrastructure").symlink_to, real, True)
    with pytest.raises(ValueError, match="symlink"):
        await _run(acts.execute_infrastructure_dir_removal, _approval(acts.INFRA_DIR_ACTION), root)
    assert await asyncio.to_thread(real.exists)


async def test_absent_directory_is_nothing_to_do(tmp_path: Path) -> None:
    plan = await asyncio.to_thread(acts.plan_infrastructure_dir, tmp_path)
    assert plan.count == 0 and plan.refused is None
    session = _session()
    await _run(acts.execute_infrastructure_dir_removal, _approval(acts.INFRA_DIR_ACTION), tmp_path, session)
    assert "Nothing to remove" in session.add.call_args.args[0].body


async def test_four_eyes_applies(tmp_path: Path) -> None:
    infra = await asyncio.to_thread(_make_infra, tmp_path)
    with pytest.raises(ValueError, match="different admin"):
        await _run(
            acts.execute_infrastructure_dir_removal,
            _approval(acts.INFRA_DIR_ACTION, decider=_ADMIN),
            tmp_path,
            _session(admins=2),
        )
    assert await asyncio.to_thread(infra.exists)
    await _run(
        acts.execute_infrastructure_dir_removal,
        _approval(acts.INFRA_DIR_ACTION, decider=_ADMIN),
        tmp_path,
        _session(admins=1),
    )
    assert not await asyncio.to_thread(infra.exists)


def test_registration_is_server_only() -> None:
    acts.register_install_cleanup_actions()
    assert approval_execution.is_server_only_action(acts.ENV_COPIES_ACTION)
    assert approval_execution.is_server_only_action(acts.INFRA_DIR_ACTION)


async def test_no_audit_entry_means_nothing_is_removed(tmp_path: Path) -> None:
    """#17038: the paper trail comes first."""
    backend = _make_env(tmp_path, {".env.1~": 100, ".env.2~": 200})
    before = _names(backend)
    with (
        patch.object(acts, "install_root", return_value=tmp_path),
        patch.object(acts, "audit_log", AsyncMock(return_value=False)),
        pytest.raises(ValueError),
    ):
        await acts.execute_env_copies_cleanup(_approval(acts.ENV_COPIES_ACTION), _session())
    assert _names(backend) == before


def test_the_stale_directory_is_refused_while_code_source_has_no_copy(tmp_path: Path) -> None:
    """Role manifests are read from code_source; without it this may be the only copy."""
    (tmp_path / acts.INFRA_DIR_NAME).mkdir()
    assert "code_source" in acts.plan_infrastructure_dir(tmp_path).refused


def test_a_checkout_as_install_root_refuses_both(tmp_path: Path) -> None:
    """On a dev checkout, `<root>/autobot-infrastructure` is tracked source and `.git` is one level up."""
    (tmp_path / ".git").mkdir()
    (tmp_path / acts.INFRA_DIR_NAME).mkdir()
    (tmp_path / "code_source" / acts.INFRA_DIR_NAME).mkdir(parents=True)
    assert "checkout" in acts.plan_infrastructure_dir(tmp_path).refused
    assert "checkout" in acts.plan_env_copies(tmp_path).refused
