# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test topology detection for SLM self-sync (#9195).

Verifies that code_sync routes to SSH rsync for remote code sources
and Ansible for local sources, fixing the multi-server regression.

Real-load prologue (#11798, same pattern as tests/api/test_drift_resolve.py):
the root conftest stubs ``models.*`` as MagicMocks, so a bare import here
yields a MagicMock ``Node``/``NodeSyncRequest`` and (solo) exec'ing
api/code_sync.py against real FastAPI + MagicMock response models raises
FastAPIError at decoration time.  Swap in the REAL modules, exec a PRIVATE
api/code_sync.py copy, restore, and pin it per-test so
``patch("api.code_sync.…")`` resolves to the private module.
"""

import contextlib
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)):  # + repo root (autobot_shared)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SWAP_KEYS = (
    "models.database",
    "models.schemas",
    "services.deploy_artifacts",
    "services.drift_checker",
)


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in ("sqlalchemy", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
        importlib.import_module(_name)

    _real_md = _load_real_module("models.database", _BACKEND_ROOT / "models" / "database.py")
    _real_schemas = _load_real_module("models.schemas", _BACKEND_ROOT / "models" / "schemas.py")
    _load_real_module("services.deploy_artifacts", _BACKEND_ROOT / "services" / "deploy_artifacts.py")
    _load_real_module("services.drift_checker", _BACKEND_ROOT / "services" / "drift_checker.py")

    _cs_spec = importlib.util.spec_from_file_location(
        "_code_sync_topology_test", _BACKEND_ROOT / "api" / "code_sync.py"
    )
    _CS = importlib.util.module_from_spec(_cs_spec)  # type: ignore[arg-type]
    _cs_spec.loader.exec_module(_CS)  # type: ignore[union-attr]

    Node = _real_md.Node
    NodeSyncRequest = _real_schemas.NodeSyncRequest
    sync_node = _CS.sync_node
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


@pytest.fixture(autouse=True)
def _pin_private_code_sync():
    """Resolve patch("api.code_sync.…") to the private module (#9780: parent attr too)."""
    saved = sys.modules.get("api.code_sync")
    sys.modules["api.code_sync"] = _CS
    _api_pkg = sys.modules.get("api")
    saved_attr = getattr(_api_pkg, "code_sync", None) if _api_pkg is not None else None
    if _api_pkg is not None:
        _api_pkg.code_sync = _CS
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("api.code_sync", None)
        else:
            sys.modules["api.code_sync"] = saved
        if _api_pkg is not None:
            if saved_attr is None:
                with contextlib.suppress(AttributeError):
                    del _api_pkg.code_sync
            else:
                _api_pkg.code_sync = saved_attr


@pytest.mark.asyncio
async def test_slm_self_sync_remote_code_source_uses_ssh_rsync():
    """Remote code source → _sync_slm_from_code_source (SSH rsync), not Ansible.

    #11798: the #9195 topology routing moved from sync_node into
    _sync_slm_self_node (fleet-sync phase 2, #1209) — test the current seam.
    """
    node_state = _CS.NodeSyncState(
        node_id="slm-node-1",
        hostname="slm.example.com",
        ip_address="10.0.1.10",
        ssh_user="autobot",
        ssh_port=22,
    )
    job = _CS.FleetSyncJob(
        job_id="job-remote",
        strategy="rolling",
        batch_size=1,
        restart=True,
        nodes={"slm-node-1": node_state},
    )

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._update_node_state_db"))
        stack.enter_context(patch("api.code_sync._update_job_status_db"))
        stack.enter_context(
            patch(
                "api.code_sync._fetch_code_source_connection_info",
                return_value=("192.168.1.100", "autobot", "/home/autobot/code"),  # noqa: ssot-path
            )
        )
        stack.enter_context(patch("autobot_shared.network_utils.is_local_ip", return_value=False))
        ssh_sync = stack.enter_context(patch("api.code_sync._sync_slm_from_code_source"))
        ansible_update = stack.enter_context(patch("api.code_sync._ansible_self_update"))

        await _CS._sync_slm_self_node(MagicMock(), job, node_state)

    ssh_sync.assert_awaited_once_with("slm-node-1")
    ansible_update.assert_not_called()
    assert node_state.status == "success"


@pytest.mark.asyncio
async def test_slm_self_sync_local_code_source_uses_ansible():
    """Local code source → _ansible_self_update, not SSH rsync (#9195)."""
    node_state = _CS.NodeSyncState(
        node_id="slm-node-1",
        hostname="slm.example.com",
        ip_address="10.0.1.10",
        ssh_user="autobot",
        ssh_port=22,
    )
    job = _CS.FleetSyncJob(
        job_id="job-local",
        strategy="rolling",
        batch_size=1,
        restart=True,
        nodes={"slm-node-1": node_state},
    )

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("api.code_sync._update_node_state_db"))
        stack.enter_context(patch("api.code_sync._update_job_status_db"))
        stack.enter_context(
            patch(
                "api.code_sync._fetch_code_source_connection_info",
                return_value=("10.0.1.10", "autobot", "/opt/autobot/code_source"),
            )
        )
        stack.enter_context(patch("autobot_shared.network_utils.is_local_ip", return_value=True))
        ssh_sync = stack.enter_context(patch("api.code_sync._sync_slm_from_code_source"))
        ansible_update = stack.enter_context(patch("api.code_sync._ansible_self_update"))

        await _CS._sync_slm_self_node(MagicMock(), job, node_state)

    ansible_update.assert_awaited_once_with("slm-node-1")
    ssh_sync.assert_not_called()
    assert node_state.status == "success"


@pytest.mark.asyncio
async def test_sync_node_self_node_routes_to_ansible_self_update():
    """sync_node on the SLM's own node queues _ansible_self_update (#9073).

    #11798: sync_node no longer branches on code-source locality (that lives
    in _sync_slm_self_node) — self-node + restart always goes to Ansible.
    """
    mock_db = MagicMock()
    mock_node = Node(
        node_id="slm-node-1",
        hostname="slm.example.com",
        ip_address="10.0.1.10",
        ssh_user="autobot",
        ssh_port=22,
    )
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_node)))

    with patch("api.code_sync.settings") as mock_settings:
        mock_settings.external_url = "http://10.0.1.10"

        with patch("api.code_sync.asyncio.create_task") as mock_create_task:
            request = NodeSyncRequest(restart=True)

            response = await sync_node(
                node_id="slm-node-1",
                request=request,
                db=mock_db,
                _={"username": "admin"},
            )

            mock_create_task.assert_called_once()
            task_coro = mock_create_task.call_args[0][0]
            assert task_coro.__name__ == "_ansible_self_update", "Expected _ansible_self_update for SLM self-node"
            task_coro.close()  # never scheduled — silence the un-awaited warning

            assert response.success is True
            assert "Ansible" in response.message
