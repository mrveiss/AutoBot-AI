# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11496: post-restart health poll + rollback in the autobot_shared restart path.

The _COMPONENT_SERVICES branch of _run_post_sync_steps (the autobot_shared
library component) restarts every dependent service but previously had NO
_wait_component_healthy poll and NO rollback — the only sync path without
post-restart verification, despite being the one that cold-restarts BOTH
backends onto freshly-imported shared code.

Now: non-self dependents restart first, each is verified (HTTP health poll for
dependents with a URL, systemd 'failed' check for the rest), a failure rolls
back the shared dir from the pre-mutation snapshot, and only when all others
are healthy is our own unit (autobot-slm-backend) restarted last — the
self-restart kills this process (#11460), so it must never run before
verification.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Minimal real Pydantic models for models.schemas so the router imports without a
# full SLM venv (mirrors the sibling code-sync tests).
if "models" not in sys.modules or isinstance(sys.modules.get("models"), MagicMock):
    from pydantic import BaseModel as _BM

    def _pydantic_stub(name: str) -> type:
        return type(name, (_BM,), {})

    _schemas = types.ModuleType("models.schemas")
    for _cls in [
        "CodeSyncStatusResponse",
        "CodeSyncRefreshResponse",
        "CodeVersionNotification",
        "CodeVersionNotificationResponse",
        "ComponentSyncJobStatus",
        "DriftResolveJobResponse",
        "DriftResolveRequest",
        "DriftResolveResponse",
        "FileDriftReport",
        "FleetSyncJobStatus",
        "FleetSyncNodeStatus",
        "FleetSyncRequest",
        "FleetSyncResponse",
        "MarkSyncedResponse",
        "NodeSyncRequest",
        "NodeSyncResponse",
        "PendingNodeResponse",
        "PendingNodesResponse",
        "ScheduleCreate",
        "ScheduleResponse",
        "ScheduleRunResponse",
        "ScheduleUpdate",
    ]:
        setattr(_schemas, _cls, _pydantic_stub(_cls))
    _models = sys.modules.get("models") or types.ModuleType("models")
    _models.schemas = _schemas  # type: ignore[attr-defined]
    sys.modules["models"] = _models
    sys.modules["models.schemas"] = _schemas

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import asyncio  # noqa: E402

import api.code_sync as cs  # noqa: E402
from api.code_sync import _run_post_sync_steps  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_SHARED = "autobot_shared"
_SELF = cs._SELF_SERVICE_NAME
_OTHERS = [s for s in cs._COMPONENT_SERVICES[_SHARED] if s != _SELF]


def _shared_branch_patches(**overrides):
    """Common patches for driving _run_post_sync_steps('autobot_shared', ...)."""
    mocks = {
        "_compute_deps_changed": AsyncMock(return_value=False),
        "_snapshot_component": AsyncMock(return_value="/opt/autobot/snapshots/autobot_shared_X"),
        "_ensure_autobot_shared_symlink": AsyncMock(),
        "_restart_component_services": AsyncMock(),
        "_wait_component_healthy": AsyncMock(return_value=True),
        "_is_systemd_unit_failed": AsyncMock(return_value=False),
        "_rollback_component": AsyncMock(),
    }
    mocks.update(overrides)
    patchers = [patch(f"api.code_sync.{name}", mock) for name, mock in mocks.items()]
    return patchers, mocks


def _run_shared_post_sync(mocks_overrides=None):
    patchers, mocks = _shared_branch_patches(**(mocks_overrides or {}))
    for p in patchers:
        p.start()
    try:
        deps_changed, steps, pip_ok = _run(
            _run_post_sync_steps(_SHARED, "/opt/autobot/code_source/autobot_shared", "/opt/autobot/autobot_shared")
        )
        mocks["guard_after"] = cs._restart_is_pending()
    finally:
        for p in patchers:
            p.stop()
        # The helper arms the #11437 guard through the verification window; the
        # mocked restart never disarms it — reset so state can't leak.
        cs._restart_pending = False
    return steps, pip_ok, mocks


# ---------------------------------------------------------------------------
# Ordering invariant — self-restart must be last (#11460/#11496)
# ---------------------------------------------------------------------------


def test_self_unit_is_last_in_shared_restart_order() -> None:
    """autobot-slm-backend restarts LAST: its restart kills this process, so any
    service after it would never restart and no verification could run."""
    assert cs._COMPONENT_SERVICES[_SHARED][-1] == _SELF


# ---------------------------------------------------------------------------
# poll-success path
# ---------------------------------------------------------------------------


def test_shared_sync_polls_dependents_then_restarts_self_last() -> None:
    """All dependents healthy → pip_ok True, no rollback, and the restart order
    is: non-self dependents first, self alone last."""
    steps, pip_ok, mocks = _run_shared_post_sync()

    assert pip_ok is True
    mocks["_rollback_component"].assert_not_awaited()

    restart_calls = mocks["_restart_component_services"].await_args_list
    assert len(restart_calls) == 2
    # First: every dependent except our own unit.
    assert restart_calls[0].kwargs["services"] == _OTHERS
    assert _SELF not in restart_calls[0].kwargs["services"]
    # Last: our own unit alone (kills this process when it lands).
    assert restart_calls[1].kwargs["services"] == [_SELF]

    # Each URL-bearing dependent is polled with slow_start=True (cold re-import).
    polled = [c.args[0] for c in mocks["_wait_component_healthy"].await_args_list]
    assert polled == [d for d in _OTHERS if d in cs._COMPONENT_HEALTH_URLS]
    assert all(c.kwargs.get("slow_start") is True for c in mocks["_wait_component_healthy"].await_args_list)


def test_shared_sync_checks_systemd_state_of_url_less_dependents() -> None:
    """Dependents without an HTTP health URL (celery, ai-stack, npu-worker) are
    verified via systemd 'failed' state."""
    _, pip_ok, mocks = _run_shared_post_sync()

    assert pip_ok is True
    checked = [c.args[0] for c in mocks["_is_systemd_unit_failed"].await_args_list]
    assert checked == [d for d in _OTHERS if d not in cs._COMPONENT_HEALTH_URLS]


def test_guard_stays_armed_during_verification_window() -> None:
    """#11437: the 409 resolve-guard must stay armed while dependents are being
    health-polled — the chain still ends in a self-restart, so a resolve job
    accepted during the poll window would be killed mid-run."""
    seen: list[bool] = []

    async def _poll(dep, steps, *, slow_start=False):
        seen.append(cs._restart_is_pending())
        return True

    _run_shared_post_sync({"_wait_component_healthy": AsyncMock(side_effect=_poll)})
    assert seen and all(seen), seen


# ---------------------------------------------------------------------------
# poll-timeout / unhealthy → rollback
# ---------------------------------------------------------------------------


def test_unhealthy_backend_triggers_rollback_and_blocks_self_restart() -> None:
    """A dependent backend failing its health poll rolls back the shared dir and
    the self-restart never runs (would restart onto broken code)."""
    steps, pip_ok, mocks = _run_shared_post_sync(
        {"_wait_component_healthy": AsyncMock(return_value=False)}
    )

    assert pip_ok is False
    mocks["_rollback_component"].assert_awaited_once()
    rb_args = mocks["_rollback_component"].await_args.args
    assert rb_args[0] == _SHARED
    assert rb_args[1] == "/opt/autobot/snapshots/autobot_shared_X"

    restart_calls = mocks["_restart_component_services"].await_args_list
    # Only the initial non-self restart — never the self-restart.
    assert len(restart_calls) == 1
    assert restart_calls[0].kwargs["services"] == _OTHERS
    assert any("rolled back to last-known-good" in s for s in steps), steps
    # Survived the rollback ⇒ the #11437 guard is disarmed so recovery resolves
    # aren't 409-blocked (#11460).
    assert mocks["guard_after"] is False


def test_failed_url_less_dependent_triggers_rollback() -> None:
    """A systemd-'failed' dependent without a health URL (e.g. celery crashloop
    on a broken shared import) also triggers rollback."""

    async def _celery_failed(service: str) -> bool:
        return service == "autobot-celery"

    steps, pip_ok, mocks = _run_shared_post_sync(
        {"_is_systemd_unit_failed": AsyncMock(side_effect=_celery_failed)}
    )

    assert pip_ok is False
    mocks["_rollback_component"].assert_awaited_once()
    assert any("autobot-celery" in s and "'failed'" in s for s in steps), steps


# ---------------------------------------------------------------------------
# rollback-failure path — no snapshot available (structured failure, no swallow)
# ---------------------------------------------------------------------------


def test_rollback_without_snapshot_surfaces_manual_recovery() -> None:
    """snapshot=None + unhealthy dependent → real _rollback_component records the
    'manual recovery required' step and the sync still reports failure."""
    from api.code_sync import _rollback_component as real_rollback

    steps, pip_ok, _ = _run_shared_post_sync(
        {
            "_snapshot_component": AsyncMock(return_value=None),
            "_wait_component_healthy": AsyncMock(return_value=False),
            "_rollback_component": real_rollback,
        }
    )

    assert pip_ok is False
    assert any("no snapshot available" in s and "manual recovery" in s for s in steps), steps


# ---------------------------------------------------------------------------
# deferred restart (async job path) — unchanged behaviour
# ---------------------------------------------------------------------------


def test_restart_false_defers_and_skips_health_poll() -> None:
    """restart=False (async job path, #11303) defers the restart entirely — no
    restart, no poll, no rollback."""
    patchers, mocks = _shared_branch_patches()
    for p in patchers:
        p.start()
    try:
        _, steps, pip_ok = _run(
            _run_post_sync_steps(
                _SHARED,
                "/opt/autobot/code_source/autobot_shared",
                "/opt/autobot/autobot_shared",
                restart=False,
            )
        )
    finally:
        for p in patchers:
            p.stop()

    assert pip_ok is True
    mocks["_restart_component_services"].assert_not_awaited()
    mocks["_wait_component_healthy"].assert_not_awaited()
    mocks["_rollback_component"].assert_not_awaited()
    assert any("restart deferred" in s for s in steps), steps


# ---------------------------------------------------------------------------
# _restart_component_services — services override (#11496)
# ---------------------------------------------------------------------------


def test_restart_component_services_honours_services_override() -> None:
    """The services= override restricts which units restart (subset restarts)."""
    restarted: list[str] = []

    async def _fake_exec(*cmd, **kw):
        restarted.append(cmd[-1])
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    steps: list[str] = []
    with patch("api.code_sync.asyncio.create_subprocess_exec", side_effect=_fake_exec):
        _run(cs._restart_component_services(_SHARED, steps, services=["autobot-backend"]))

    assert restarted == ["autobot-backend"]
    # Surviving return disarms the #11437 guard (#11460) — unchanged contract.
    assert cs._restart_is_pending() is False
