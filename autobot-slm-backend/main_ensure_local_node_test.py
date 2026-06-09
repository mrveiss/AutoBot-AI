# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for _ensure_local_node() lifespan helper (#3225).

Verifies that the SLM manager self-registers on every startup and self-heals
a stale IP when SLM_EXTERNAL_URL has been corrected, without importing the
full FastAPI application stack.
"""

import importlib
import importlib.util
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_SLM_ROOT = Path(__file__).parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

# ---------------------------------------------------------------------------
# Stub models.database before any module load so that the lazy import inside
# _ensure_local_node() resolves at function-call time.  Python looks up
# "models" and "models.database" as separate sys.modules keys; both must be
# present or the submodule lookup raises ImportError.
# ---------------------------------------------------------------------------
_models_db_stub = MagicMock()
_models_db_stub.Node = MagicMock()
_models_db_stub.NodeRole = MagicMock()
_models_db_stub.NodeStatus = MagicMock()
sys.modules.setdefault("models", MagicMock())
sys.modules.setdefault("models.database", _models_db_stub)

# ---------------------------------------------------------------------------
# Constants that must match main.py
# ---------------------------------------------------------------------------
_NODE_ID = "00-SLM-Manager"
_ROLES = ["slm-backend", "slm-frontend", "slm-database", "slm-monitoring"]


# ---------------------------------------------------------------------------
# Session / DB helpers
# ---------------------------------------------------------------------------
def _make_mock_node(ip: str = "10.0.0.1") -> MagicMock:
    node = MagicMock()
    node.node_id = _NODE_ID
    node.ip_address = ip
    return node


def _make_session(existing_node=None) -> AsyncMock:
    """Return a mock async session whose SELECT returns *existing_node*."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing_node
    session.execute = AsyncMock(return_value=execute_result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@asynccontextmanager
async def _ctx(session: AsyncMock):
    yield session


# ---------------------------------------------------------------------------
# Load _ensure_local_node in isolation from main.py
# ---------------------------------------------------------------------------
_MODULE_CACHE: dict = {}


def _load_module():
    """Load main.py with its heavy module-level imports stubbed out.

    Returns the loaded module so callers can patch attributes on it.
    """
    if "isolated_main" in _MODULE_CACHE:
        return _MODULE_CACHE["isolated_main"]

    stubs = {
        "fastapi": MagicMock(),
        "fastapi.middleware.cors": MagicMock(),
        "api": MagicMock(),
        "api.code_source": MagicMock(),
        "api.performance": MagicMock(),
        "api.personality_proxy": MagicMock(),
        "api.roles": MagicMock(),
        "api.voice_proxy": MagicMock(),
        "config": MagicMock(),
        "middleware": MagicMock(),
        "services.a2a_card_fetcher": MagicMock(),
        "services.database": MagicMock(),
        "services.git_tracker": MagicMock(),
        "services.reconciler": MagicMock(),
        "services.schedule_executor": MagicMock(),
    }
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("isolated_main", _SLM_ROOT / "main.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    _MODULE_CACHE["isolated_main"] = mod
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestEnsureLocalNode:
    """Tests for _ensure_local_node() (#3225)."""

    def setup_method(self):
        self._mod = _load_module()
        self._fn = self._mod._ensure_local_node

    # ------------------------------------------------------------------
    # Node absent — creates Node + 4 NodeRole records
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_creates_node_when_absent(self):
        """A new Node and four NodeRole rows are inserted when none exist."""
        session = _make_session(existing_node=None)
        added_objects: list = []
        session.add = MagicMock(side_effect=added_objects.append)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": "https://192.168.1.50"}),
        ):
            await self._fn()

        # 1 Node + 4 NodeRole = 5 objects
        assert len(added_objects) == 5

        node_obj = added_objects[0]
        assert node_obj.node_id == _NODE_ID
        assert node_obj.ip_address == "192.168.1.50"
        assert node_obj.status == "online"
        assert node_obj.roles == _ROLES

        role_names = {obj.role_name for obj in added_objects[1:]}
        assert role_names == set(_ROLES)

        session.commit.assert_awaited_once()

    # ------------------------------------------------------------------
    # Node present, IP current — idempotent, no writes
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_idempotent_when_ip_unchanged(self):
        """No DB write occurs when the node already has the correct IP."""
        current_ip = "192.168.1.50"
        existing = _make_mock_node(ip=current_ip)
        session = _make_session(existing_node=existing)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": f"https://{current_ip}"}),
        ):
            await self._fn()

        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    # ------------------------------------------------------------------
    # Node present, IP stale — updates IP field only
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_heals_stale_ip(self):
        """Stale ip_address on existing node is updated to match SLM_EXTERNAL_URL."""
        old_ip = "10.0.0.1"
        new_ip = "192.168.1.99"
        existing = _make_mock_node(ip=old_ip)
        session = _make_session(existing_node=existing)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": f"https://{new_ip}"}),
        ):
            await self._fn()

        assert existing.ip_address == new_ip
        session.commit.assert_awaited_once()
        session.add.assert_not_called()

    # ------------------------------------------------------------------
    # No SLM_EXTERNAL_URL — falls back to UDP probe or 127.0.0.1
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fallback_ip_when_no_env(self):
        """When SLM_EXTERNAL_URL is absent a non-empty IP is still determined."""
        session = _make_session(existing_node=None)
        added_objects: list = []
        session.add = MagicMock(side_effect=added_objects.append)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        env_without_url = {k: v for k, v in os.environ.items() if k != "SLM_EXTERNAL_URL"}

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, env_without_url, clear=True),
        ):
            await self._fn()

        node_obj = added_objects[0]
        assert node_obj.ip_address  # not empty / None

    # ------------------------------------------------------------------
    # Correct node_id sentinel
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_node_id_is_slm_manager_sentinel(self):
        """Created node always uses the '00-SLM-Manager' sentinel ID."""
        session = _make_session(existing_node=None)
        added_objects: list = []
        session.add = MagicMock(side_effect=added_objects.append)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": "https://10.10.10.1"}),
        ):
            await self._fn()

        node_obj = added_objects[0]
        assert node_obj.node_id == "00-SLM-Manager"
        assert node_obj.ansible_name == "00-SLM-Manager"

    # ------------------------------------------------------------------
    # NodeRole metadata
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_node_roles_have_correct_metadata(self):
        """Created NodeRole rows carry assignment_type='auto' and status='active'."""
        session = _make_session(existing_node=None)
        added_objects: list = []
        session.add = MagicMock(side_effect=added_objects.append)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": "https://10.10.10.1"}),
        ):
            await self._fn()

        role_objs = added_objects[1:]
        assert len(role_objs) == 4
        for role_obj in role_objs:
            assert role_obj.assignment_type == "auto"
            assert role_obj.status == "active"
            assert role_obj.node_id == _NODE_ID

    # ------------------------------------------------------------------
    # HTTPS URL with port is parsed correctly
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_parses_url_with_port(self):
        """IP is extracted correctly from URLs that include a port number."""
        session = _make_session(existing_node=None)
        added_objects: list = []
        session.add = MagicMock(side_effect=added_objects.append)

        mock_db = MagicMock()
        mock_db.session = MagicMock(return_value=_ctx(session))

        # URL includes port — regex must not capture the port as part of IP
        with (
            patch.object(self._mod, "db_service", mock_db),
            patch.dict(os.environ, {"SLM_EXTERNAL_URL": "https://172.16.0.10:8443"}),
        ):
            await self._fn()

        node_obj = added_objects[0]
        assert node_obj.ip_address == "172.16.0.10"
