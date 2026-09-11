# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the pricing post-sync step (#16231, AC1 + AC4).

A code-sync of ``autobot-backend`` must run a pricing refresh right after its
own venv is ready (``api._pricing_post_sync.run_pricing_refresh_post_sync``,
called from ``_run_post_sync_backend_branch``). A frontend sync never routes
through that branch at all, so it must never invoke the step. And a refresh
that fails or times out must never fail the sync itself -- prices stay
*unknown* until the next attempt (#16228 decision), which this file asserts
both by observing the mocked step (AC1) and by faking the refresh
subprocess underneath the real step (AC4).
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# #12572: import api.code_sync via the shared helper — see
# test_code_sync_symlink_restore.py's module docstring for why.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync, patch_real_deployed_root  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

import api.code_sync as cs  # noqa: E402


def _run(coro):
    # A dedicated loop per call, resilient to a prior test having closed the
    # main-thread event loop (see test_code_sync_symlink_restore.py).
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _patch_backend_branch_helpers(stack: contextlib.ExitStack) -> None:
    """Mock every side-effecting helper _run_post_sync_backend_branch touches,
    other than the pricing post-sync step itself (#13312 — otherwise the test
    shells out / rsyncs / polls a real HTTP endpoint for ~180s). Mirrors
    test_code_sync_deploy_bugs.py's test_run_post_sync_steps_pip_ok_true_on_success.
    """
    stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)))
    stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
    stack.enter_context(patch("api.code_sync._deploy_constraints_dir", AsyncMock()))
    stack.enter_context(patch("api.code_sync._deploy_repo_root_requirements", AsyncMock()))
    stack.enter_context(patch("api.code_sync._ensure_target_python_installed", AsyncMock()))
    stack.enter_context(patch("api.code_sync._ensure_venv_python", AsyncMock(return_value=False)))
    stack.enter_context(patch("api.code_sync._install_pip_deps_for_component", AsyncMock(return_value=True)))
    stack.enter_context(patch("api.code_sync.reconcile_component", AsyncMock()))
    stack.enter_context(patch("api.code_sync._run_alembic_migrations", AsyncMock(return_value=True)))
    stack.enter_context(patch("api.code_sync._ensure_autobot_shared_symlink", AsyncMock()))
    stack.enter_context(patch("api.code_sync._restart_component_services", AsyncMock()))
    stack.enter_context(patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=True)))
    stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))


def _patch_frontend_branch_helpers(stack: contextlib.ExitStack) -> None:
    """Mock every side-effecting helper _run_post_sync_frontend_branch touches."""
    stack.enter_context(patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)))
    stack.enter_context(patch("api.code_sync._snapshot_component", AsyncMock(return_value=None)))
    stack.enter_context(patch("api.code_sync._build_npm_frontend_for_component", AsyncMock(return_value=True)))
    stack.enter_context(patch("api.code_sync._restart_component_services", AsyncMock()))
    stack.enter_context(patch("api.code_sync._wait_component_healthy", AsyncMock(return_value=True)))
    stack.enter_context(patch("api.code_sync._rollback_component", AsyncMock()))


# ---------------------------------------------------------------------------
# AC1 — a backend sync invokes the step; a frontend sync does not
# ---------------------------------------------------------------------------


def test_backend_sync_invokes_the_pricing_post_sync_step() -> None:
    """An autobot-backend sync must run the pricing refresh step (#16231 AC1)."""
    with contextlib.ExitStack() as stack:
        pricing_mock = stack.enter_context(patch("api.code_sync.run_pricing_refresh_post_sync", AsyncMock()))
        _patch_backend_branch_helpers(stack)
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )

    assert pip_ok is True
    pricing_mock.assert_awaited_once()
    called_component, called_deployed_dir, called_pip_bin, called_steps = pricing_mock.call_args.args
    assert called_component == "autobot-backend"
    assert called_deployed_dir == "/opt/autobot/autobot-backend"
    assert called_pip_bin == cs._COMPONENT_PIP_PATHS["autobot-backend"][1]
    assert called_steps is steps


def test_frontend_sync_never_invokes_the_pricing_post_sync_step() -> None:
    """A frontend sync doesn't route through the backend branch at all (#16231 AC1)."""
    with contextlib.ExitStack() as stack:
        pricing_mock = stack.enter_context(patch("api.code_sync.run_pricing_refresh_post_sync", AsyncMock()))
        _patch_frontend_branch_helpers(stack)
        _, _, pip_ok = _run(
            cs._run_post_sync_steps(
                "autobot-slm-frontend", "/src/autobot-slm-frontend", "/opt/autobot/autobot-slm-frontend"
            )
        )

    assert pip_ok is True
    pricing_mock.assert_not_called()


# ---------------------------------------------------------------------------
# AC4 — a failing or timed-out refresh records why, and never fails the sync
# ---------------------------------------------------------------------------


def test_a_failing_pricing_refresh_records_the_reason_and_the_sync_still_succeeds(monkeypatch) -> None:
    """rc != 0 from the refresh CLI: recorded as failed, sync unaffected (#16231 AC4).

    The real ``run_pricing_refresh_post_sync`` runs here (not mocked); only the
    subprocess it spawns is faked. It reaches ``_load_env_file``'s containment
    guard (#16229 review) on the way, so it needs the real
    ``deployed_dir_resolver`` (#16236) -- under the conftest stub,
    ``deployed_root()`` is a MagicMock and the guard raises before the
    subprocess is ever spawned, recording a "failed to start" step instead of
    the rc!=0 one this test asserts on. The default root ("/opt/autobot")
    already matches this test's hardcoded deployed_dir, so no
    SLM_DEPLOYED_ROOT override is needed.
    """

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"boom: catalogue unreachable"))
        return proc

    with contextlib.ExitStack() as stack:
        patch_real_deployed_root(monkeypatch)
        _patch_backend_branch_helpers(stack)
        stack.enter_context(patch("asyncio.create_subprocess_exec", side_effect=_fake_exec))
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )

    assert pip_ok is True, "a failed pricing refresh must never fail the sync"
    assert any(
        "pricing refresh" in s and "FAILED" in s and "unknown" in s for s in steps
    ), f"no step names the pricing refresh failure: {steps!r}"


def test_a_timed_out_pricing_refresh_records_the_reason_and_the_sync_still_succeeds(monkeypatch) -> None:
    """A refresh that does not finish in time: recorded as timed out, sync unaffected (#16231 AC4).

    Needs the real ``deployed_dir_resolver`` (#16236) for the same reason as
    the rc!=0 test above: the containment guard ``_load_env_file`` runs
    through must raise for real reasons, not because the stub's
    ``deployed_root()`` is a MagicMock.
    """

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError())
        return proc

    with contextlib.ExitStack() as stack:
        patch_real_deployed_root(monkeypatch)
        _patch_backend_branch_helpers(stack)
        stack.enter_context(patch("asyncio.create_subprocess_exec", side_effect=_fake_exec))
        stack.enter_context(patch("asyncio.wait_for", side_effect=asyncio.TimeoutError))
        _, steps, pip_ok = _run(
            cs._run_post_sync_steps("autobot-backend", "/src/autobot-backend", "/opt/autobot/autobot-backend")
        )

    assert pip_ok is True, "a timed-out pricing refresh must never fail the sync"
    assert any(
        "pricing refresh" in s and "timed out" in s and "unknown" in s for s in steps
    ), f"no step names the pricing refresh timeout: {steps!r}"


# ---------------------------------------------------------------------------
# CodeQL py/path-injection (#16229 review, alerts #1132/#1133; regressed as
# #1134/#1135 by an equality branch, fixed by #16236) — _load_env_file must
# resolve and contain every candidate path against the deployed root, inline
# in its own scope, before touching the filesystem with it.
# ---------------------------------------------------------------------------


def test_load_env_file_accepts_a_path_under_the_deployed_root(tmp_path, monkeypatch) -> None:
    # Needs the real deployed_dir_resolver (#16236): the conftest stub's
    # deployed_root() is a MagicMock, so SLM_DEPLOYED_ROOT alone has nothing to
    # act on and the guard would reject every path, including this one.
    patch_real_deployed_root(monkeypatch, tmp_path)
    deployed = tmp_path / "autobot-backend"
    deployed.mkdir()
    (deployed / ".env").write_text("FOO=bar\n", encoding="utf-8")

    result = cs._load_env_file(deployed / ".env")

    assert result == {"FOO": "bar"}


def test_load_env_file_refuses_a_dot_dot_escape(tmp_path, monkeypatch) -> None:
    # Needs the real deployed_dir_resolver (#16236): under the conftest stub,
    # deployed_root() is a MagicMock and the guard raises for every path
    # regardless of the .. escape, which would pass this test for the wrong
    # reason (it never exercises the escape-detection logic at all).
    patch_real_deployed_root(monkeypatch, tmp_path)
    escaping = tmp_path / "autobot-backend" / ".." / ".." / "etc" / "passwd"

    try:
        cs._load_env_file(escaping)
    except ValueError:
        pass
    else:
        raise AssertionError("a .. escape outside the deployed root must raise ValueError")


def test_load_env_file_refuses_an_absolute_path_outside_the_root(tmp_path, monkeypatch) -> None:
    # Needs the real deployed_dir_resolver (#16236) -- see the .. escape test
    # above for why: without it, the guard raises regardless of this test's
    # specific "outside the root" scenario.
    patch_real_deployed_root(monkeypatch, tmp_path / "deployed")
    outside = tmp_path / "elsewhere" / ".env"
    outside.parent.mkdir()
    outside.write_text("SHOULD_NOT=load\n", encoding="utf-8")

    try:
        cs._load_env_file(outside)
    except ValueError:
        pass
    else:
        raise AssertionError("a path outside the deployed root must raise ValueError, not silently return {}")


def test_load_env_file_missing_file_under_the_root_returns_empty(tmp_path, monkeypatch) -> None:
    """A path that validates but doesn't exist is a normal 'no .env yet' case,
    not an error — distinct from a path that fails validation entirely.

    Needs the real deployed_dir_resolver (#16236): the conftest stub's
    deployed_root() is a MagicMock, so SLM_DEPLOYED_ROOT alone has nothing to
    act on and the guard would reject this path too.
    """
    patch_real_deployed_root(monkeypatch, tmp_path)

    result = cs._load_env_file(tmp_path / "autobot-backend" / ".env")

    assert result == {}


def test_load_env_file_refuses_a_sibling_directory_sharing_the_root_as_a_string_prefix(tmp_path, monkeypatch) -> None:
    """The containment check must be anchored on ``root + os.sep`` -- a naive
    ``startswith(root)`` would wrongly accept a sibling whose name merely
    starts with the same characters (e.g. ``/opt/autobot`` vs
    ``/opt/autobot-evil``).

    Needs the real deployed_dir_resolver (#16236) -- see the .. escape test
    above for why: without it the guard raises regardless of the sibling-prefix
    scenario this test names.
    """
    patch_real_deployed_root(monkeypatch, tmp_path)
    sibling = Path(str(tmp_path) + "-evil") / ".env"

    try:
        cs._load_env_file(sibling)
    except ValueError:
        pass
    else:
        raise AssertionError("a same-prefix sibling directory must raise ValueError")


def test_load_env_file_refuses_the_deployed_root_itself(tmp_path, monkeypatch) -> None:
    """An env file can never *be* the deployed root directory, so the guard
    must not special-case that equality (CodeQL #1134/#1135, #16236) -- the
    single ``startswith(root + os.sep)`` check refuses it like any other
    path that isn't strictly under the root.

    Needs the real deployed_dir_resolver (#16236): under the conftest stub,
    deployed_root() is a MagicMock and every path -- including one nowhere
    near the equality edge case -- raises, so this test would give zero
    regression coverage for #1134/#1135 without it.
    """
    patch_real_deployed_root(monkeypatch, tmp_path)

    try:
        cs._load_env_file(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("the deployed root itself must raise ValueError, not be read as a file")
