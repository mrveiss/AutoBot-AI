# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the autobot_shared symlink-restore step (#10912).

The builtin code-sync drift/resolve rsyncs with --delete, which removes the
autobot_shared symlink inside each Python backend component dir because the
symlink is not present in the code_source tree. Without the symlink the
restarted process dies with ModuleNotFoundError.

_ensure_autobot_shared_symlink() recreates the symlink after rsync and before
the service restart.  _run_post_sync_steps() calls it at the right points:
  - for pip backend components: after pip install, before service restart
  - for autobot_shared: before restarting all dependent services
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock  # MagicMock used in sys.modules guard below

# ---------------------------------------------------------------------------
# Dev-host stub: models.schemas contains real Pydantic models in CI but on
# the dev box (no SLM venv) it is a MagicMock that makes FastAPI's
# response_model validation fail at decoration time.  Pre-populate the module
# with minimal real BaseModel subclasses so the router can be imported.
# Must happen before the api.code_sync import below.
# ---------------------------------------------------------------------------
if "models" not in sys.modules or isinstance(sys.modules.get("models"), MagicMock):
    from pydantic import BaseModel as _BM

    def _pydantic_stub(name: str, **fields) -> type:
        return type(name, (_BM,), {"__annotations__": {k: type(v) for k, v in fields.items()}, **fields})

    _schemas = types.ModuleType("models.schemas")
    # Enumerate every name imported from models.schemas in api/code_sync.py.
    for _cls in [
        "CodeSyncStatusResponse",
        "CodeSyncRefreshResponse",
        "CodeVersionNotification",
        "CodeVersionNotificationResponse",
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

# Add autobot-slm-backend to path so api.code_sync imports resolve.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import asyncio  # noqa: E402

from api.code_sync import (  # noqa: E402
    _BACKEND_COMPONENTS,
    _COMPONENT_PIP_PATHS,
    _ensure_autobot_shared_symlink,
    _run_post_sync_steps,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _BACKEND_COMPONENTS covers exactly the pip-backend components
# ---------------------------------------------------------------------------

def test_backend_components_match_pip_paths() -> None:
    """_BACKEND_COMPONENTS must equal the pip-backend set so no component is missed."""
    assert _BACKEND_COMPONENTS == frozenset(_COMPONENT_PIP_PATHS.keys())


def test_backend_components_are_pip_backends() -> None:
    assert "autobot-backend" in _BACKEND_COMPONENTS
    assert "autobot-slm-backend" in _BACKEND_COMPONENTS


# ---------------------------------------------------------------------------
# _ensure_autobot_shared_symlink — filesystem-level behaviour
# ---------------------------------------------------------------------------

def test_symlink_created_when_missing(tmp_path) -> None:
    """Symlink is created when the link path does not yet exist."""
    shared_target = tmp_path / "autobot_shared"
    shared_target.mkdir()
    component = "autobot-backend"
    (tmp_path / component).mkdir()
    link_path = tmp_path / component / "autobot_shared"

    steps: list = []
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)
    ):
        _run(_ensure_autobot_shared_symlink(component, steps))

    assert link_path.is_symlink()
    assert link_path.resolve() == shared_target.resolve()
    assert any("restored" in s for s in steps)


def test_symlink_replaced_when_wrong_target(tmp_path) -> None:
    """A symlink pointing at the wrong target is replaced."""
    from unittest.mock import patch

    shared_target = tmp_path / "autobot_shared"
    shared_target.mkdir()
    component = "autobot-slm-backend"
    comp_dir = tmp_path / component
    comp_dir.mkdir()
    wrong_dir = tmp_path / "wrong"
    wrong_dir.mkdir()
    link_path = comp_dir / "autobot_shared"
    link_path.symlink_to(wrong_dir)

    steps: list = []
    with patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)):
        _run(_ensure_autobot_shared_symlink(component, steps))

    assert link_path.is_symlink()
    assert link_path.resolve() == shared_target.resolve()
    assert any("restored" in s for s in steps)


def test_symlink_noop_when_already_correct(tmp_path) -> None:
    """No-op (step says 'already correct') when the symlink is already correct."""
    from unittest.mock import patch

    shared_target = tmp_path / "autobot_shared"
    shared_target.mkdir()
    component = "autobot-backend"
    comp_dir = tmp_path / component
    comp_dir.mkdir()
    link_path = comp_dir / "autobot_shared"
    link_path.symlink_to(shared_target)

    steps: list = []
    with patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)):
        _run(_ensure_autobot_shared_symlink(component, steps))

    assert link_path.is_symlink()
    assert any("already correct" in s for s in steps)


def test_skipped_for_non_backend_component(tmp_path) -> None:
    """Helper is a no-op for non-pip-backend components."""
    from unittest.mock import patch

    steps: list = []
    with patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)):
        _run(_ensure_autobot_shared_symlink("autobot-slm-frontend", steps))
    assert steps == []


def test_skipped_when_shared_target_missing(tmp_path) -> None:
    """If /opt/autobot/autobot_shared doesn't exist, helper skips gracefully."""
    from unittest.mock import patch

    component = "autobot-backend"
    (tmp_path / component).mkdir()
    steps: list = []
    with patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)):
        _run(_ensure_autobot_shared_symlink(component, steps))
    assert any("not found" in s for s in steps)


# ---------------------------------------------------------------------------
# _run_post_sync_steps — pip backend path calls symlink restore before restart
# ---------------------------------------------------------------------------

def test_pip_backend_emits_symlink_step(tmp_path) -> None:
    """Symlink step is emitted for pip backend components via _run_post_sync_steps."""
    from unittest.mock import patch

    for component in ("autobot-backend", "autobot-slm-backend"):
        shared_target = tmp_path / "autobot_shared"
        shared_target.mkdir(exist_ok=True)
        (tmp_path / component).mkdir(exist_ok=True)

        steps_collected: list[str] = []

        async def _fake_ensure(comp: str, steps: list) -> None:
            steps.append(f"symlink-called:{comp}")

        with (
            patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)),
            patch("api.code_sync._ensure_autobot_shared_symlink", side_effect=_fake_ensure),
            patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
            patch("api.code_sync._install_pip_deps_for_component", AsyncMock()),
            patch("api.code_sync._restart_component_services", AsyncMock()),
        ):
            _, steps = _run(
                _run_post_sync_steps(component, f"/src/{component}", f"/opt/autobot/{component}")
            )
            steps_collected.extend(steps)

        assert any(f"symlink-called:{component}" in s for s in steps_collected), (
            f"No symlink call for {component}: {steps_collected}"
        )


# ---------------------------------------------------------------------------
# _run_post_sync_steps — autobot_shared path restores BOTH backends' symlinks
# ---------------------------------------------------------------------------

def test_autobot_shared_component_restores_both_backends(tmp_path) -> None:
    """When syncing autobot_shared, _ensure_autobot_shared_symlink called for each backend."""
    from unittest.mock import patch

    called_for: list[str] = []

    async def _fake_ensure(component: str, steps: list) -> None:
        called_for.append(component)

    with (
        patch("api.code_sync._AUTOBOT_DEPLOY_BASE", str(tmp_path)),
        patch("api.code_sync._ensure_autobot_shared_symlink", side_effect=_fake_ensure),
        patch("api.code_sync._restart_component_services", AsyncMock()),
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
    ):
        _run(
            _run_post_sync_steps(
                "autobot_shared",
                "/src/autobot_shared",
                "/opt/autobot/autobot_shared",
            )
        )

    assert set(called_for) == _BACKEND_COMPONENTS, (
        f"Expected symlinks for {_BACKEND_COMPONENTS}, got {set(called_for)}"
    )
