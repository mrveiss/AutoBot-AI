# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for ReconcilerService._check_node_health() (#11963).

Verifies the reconciler's ICMP-ping-based offline/degraded demotion never
overrides the manager/self node's status -- it is heartbeated locally from
real-time metrics of this very process (services/compose_fleet.py) -- while a
genuinely stale + unreachable remote node is still correctly demoted.
"""

import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path bootstrap (mirrors main_ensure_local_node_test.py's #11798 fix)
# ---------------------------------------------------------------------------
_SLM_ROOT = Path(__file__).parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_MANAGER_NODE_ID = "00-SLM-Manager"
_REMOTE_NODE_ID = "01-Backend"

# ---------------------------------------------------------------------------
# Persistent stubs for reconciler.py's LAZY (function-body) imports.
# ``_check_node_health`` imports ``services.compose_fleet`` and
# ``services.database`` at call time, not at module-load time, so a
# ``patch.dict`` scoped to ``_load_module()``'s ``exec_module`` call would be
# reverted before the function under test ever runs. Register real, persistent
# stand-ins instead (mirrors the root conftest's ``_stub()`` pattern).
# ---------------------------------------------------------------------------
for _lazy_mod in ("services.compose_fleet", "services.database"):
    if _lazy_mod not in sys.modules:
        sys.modules[_lazy_mod] = MagicMock(unsafe=True, name=_lazy_mod)


def _fake_node(node_id: str, status: str, ip: str = "10.0.0.5") -> SimpleNamespace:
    """Minimal stand-in for a Node row: attribute access only, no DB behavior."""
    return SimpleNamespace(node_id=node_id, status=status, ip_address=ip)


class _AlwaysComparableColumn:
    """Stand-in for ``Node.last_heartbeat`` (a mocked SQLAlchemy Column).

    Only the operators ``_check_node_health`` builds its query with need to
    resolve without raising; the resulting (fake) expression is never
    evaluated -- ``db.execute`` is mocked to return canned rows directly.
    """

    def __lt__(self, other):
        return True

    def is_(self, other):
        return True


_MODULE_CACHE: dict = {}


def _load_module():
    """Load services/reconciler.py with its heavy module-level imports stubbed.

    Follows the isolated-load pattern established in
    main_ensure_local_node_test.py (#11798) so the real function body under
    test runs unmodified, without pulling in sqlalchemy/models/config.
    """
    if "isolated_reconciler" in _MODULE_CACHE:
        return _MODULE_CACHE["isolated_reconciler"]

    stubs = {
        "sqlalchemy": MagicMock(),
        "sqlalchemy.ext": MagicMock(),
        "sqlalchemy.ext.asyncio": MagicMock(),
        "config": MagicMock(),
        "models.database": MagicMock(),
        "services.service_categorizer": MagicMock(),
        "services.service_extra_data": MagicMock(),
    }
    stubs["config"].settings = SimpleNamespace(heartbeat_interval=30, unhealthy_threshold=3)
    stubs["models.database"].NodeStatus = SimpleNamespace(
        ONLINE=SimpleNamespace(value="online"),
        DEGRADED=SimpleNamespace(value="degraded"),
        OFFLINE=SimpleNamespace(value="offline"),
        ERROR=SimpleNamespace(value="error"),
    )
    # ``Node.last_heartbeat < cutoff`` is a real Python comparison at query-build
    # time (SQLAlchemy's Column overloads ``__lt__``); a bare MagicMock's default
    # comparison returns NotImplemented -> TypeError, so give it a stand-in that
    # tolerates the operators the query actually uses.
    stubs["models.database"].Node.last_heartbeat = _AlwaysComparableColumn()

    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("isolated_reconciler", _SLM_ROOT / "services" / "reconciler.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    _MODULE_CACHE["isolated_reconciler"] = mod
    return mod


class TestCheckNodeHealthManagerExclusion:
    """ReconcilerService._check_node_health() manager-node exclusion (#11963)."""

    def setup_method(self):
        self._mod = _load_module()

    def _make_service(self, nodes, is_manager_side_effect):
        """Build a ReconcilerService instance wired to a fake DB session."""
        service = self._mod.ReconcilerService()
        service._ping_host = AsyncMock(return_value=False)  # unreachable
        service._handle_offline_node = AsyncMock()
        service._handle_degraded_node = AsyncMock()

        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None  # no timeout override
        execute_result.scalars.return_value.all.return_value = nodes

        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)
        db.commit = AsyncMock()

        @asynccontextmanager
        async def _session():
            yield db

        mock_db_service = MagicMock()
        mock_db_service.session = _session

        compose_fleet_stub = sys.modules["services.compose_fleet"]
        compose_fleet_stub.is_manager_node = MagicMock(side_effect=is_manager_side_effect)

        return service, mock_db_service

    @pytest.mark.asyncio
    async def test_manager_node_skipped_even_when_unreachable_and_stale(self):
        """The manager/self node is never pinged or demoted (#11963)."""
        node = _fake_node(_MANAGER_NODE_ID, "online")
        service, mock_db_service = self._make_service(
            [node], is_manager_side_effect=lambda nid: nid == _MANAGER_NODE_ID
        )

        with patch.object(sys.modules["services.database"], "db_service", mock_db_service):
            await service._check_node_health()

        service._ping_host.assert_not_called()
        service._handle_offline_node.assert_not_called()
        service._handle_degraded_node.assert_not_called()
        assert node.status == "online"

    @pytest.mark.asyncio
    async def test_genuinely_stale_remote_node_still_marked_offline(self):
        """A real remote node that is stale + unreachable is still demoted (#11963)."""
        node = _fake_node(_REMOTE_NODE_ID, "online")
        service, mock_db_service = self._make_service(
            [node], is_manager_side_effect=lambda nid: nid == _MANAGER_NODE_ID
        )

        with patch.object(sys.modules["services.database"], "db_service", mock_db_service):
            await service._check_node_health()

        service._ping_host.assert_awaited_once_with(node.ip_address)
        service._handle_offline_node.assert_awaited_once()
        service._handle_degraded_node.assert_not_called()
