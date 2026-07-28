# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the rewritten WebSocket ``ConnectionManager`` (#12515).

Follow-up to #12455, which deleted the dead ``websockets_test.py`` (it imported
the removed ``SLMWebSocketManager`` + ``create_reconciler_callbacks``).  The
current ``api/websocket.py`` uses a channel-keyed ``ConnectionManager`` plus a
set of ``send_*`` fan-out helpers, none of which had coverage.

These tests import ``ConnectionManager`` directly (the root conftest already
stubs ``services.*`` so ``api.websocket`` imports cleanly — see the existing
``tests/test_websocket_auth_smoke.py``) and drive it with fake AsyncMock
WebSockets.  They assert real behaviour: channel registration on connect,
cleanup on disconnect, message fan-out on broadcast, silent pruning of dead
sockets, and the dual global+node channel routing of the ``send_*`` helpers.

The accept-then-close-on-auth-fail convention (#12366) is already covered for
``_authenticate_websocket_token`` in ``tests/test_websocket_auth_smoke.py``;
this module focuses on the previously-uncovered ``ConnectionManager``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from api.websocket import ConnectionManager


def _fake_ws(protocols: str = "") -> AsyncMock:
    """A fake WebSocket exposing the sync ``headers`` the manager reads."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(
        side_effect=lambda key, default="": protocols if key == "sec-websocket-protocol" else default
    )
    return ws


class TestConnectLifecycle:
    """connect/disconnect channel bookkeeping (#12515)."""

    async def test_connect_accepts_and_registers(self):
        mgr = ConnectionManager()
        ws = _fake_ws()
        await mgr.connect(ws, "events:global")
        ws.accept.assert_awaited_once()
        assert ws in mgr._connections["events:global"]

    async def test_connect_uses_bearer_subprotocol_when_offered(self):
        mgr = ConnectionManager()
        ws = _fake_ws(protocols="bearer, sometoken")
        await mgr.connect(ws, "events:global")
        assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"

    async def test_connect_without_bearer_has_no_subprotocol(self):
        mgr = ConnectionManager()
        ws = _fake_ws(protocols="")
        await mgr.connect(ws, "events:global")
        assert ws.accept.call_args.kwargs.get("subprotocol") is None

    async def test_disconnect_removes_and_prunes_empty_channel(self):
        mgr = ConnectionManager()
        ws = _fake_ws()
        await mgr.connect(ws, "node:n1")
        await mgr.disconnect(ws, "node:n1")
        # Last socket gone -> channel key removed entirely.
        assert "node:n1" not in mgr._connections

    async def test_disconnect_keeps_channel_with_remaining_sockets(self):
        mgr = ConnectionManager()
        ws1, ws2 = _fake_ws(), _fake_ws()
        await mgr.connect(ws1, "node:n1")
        await mgr.connect(ws2, "node:n1")
        await mgr.disconnect(ws1, "node:n1")
        assert "node:n1" in mgr._connections
        assert ws2 in mgr._connections["node:n1"]
        assert ws1 not in mgr._connections["node:n1"]

    async def test_disconnect_unknown_channel_is_noop(self):
        mgr = ConnectionManager()
        # Must not raise even though the channel was never registered.
        await mgr.disconnect(_fake_ws(), "never")


class TestBroadcast:
    """broadcast fan-out + dead-socket pruning (#12515)."""

    async def test_broadcast_sends_to_all_on_channel(self):
        mgr = ConnectionManager()
        ws1, ws2 = _fake_ws(), _fake_ws()
        await mgr.connect(ws1, "events:global")
        await mgr.connect(ws2, "events:global")
        message = {"type": "ping"}
        await mgr.broadcast("events:global", message)
        ws1.send_json.assert_awaited_once_with(message)
        ws2.send_json.assert_awaited_once_with(message)

    async def test_broadcast_unknown_channel_is_noop(self):
        mgr = ConnectionManager()
        # No connections/channel -> should simply do nothing.
        await mgr.broadcast("nobody", {"type": "x"})

    async def test_broadcast_prunes_failed_socket(self):
        mgr = ConnectionManager()
        good, bad = _fake_ws(), _fake_ws()
        bad.send_json = AsyncMock(side_effect=RuntimeError("closed"))
        await mgr.connect(good, "events:global")
        await mgr.connect(bad, "events:global")
        await mgr.broadcast("events:global", {"type": "ping"})
        # The failed socket is dropped; the healthy one is retained.
        assert bad not in mgr._connections["events:global"]
        assert good in mgr._connections["events:global"]


class TestSendHelpers:
    """The send_* helpers fan out to both global and node channels (#12515)."""

    async def _connect_global_and_node(self, mgr, node_id):
        g, n = _fake_ws(), _fake_ws()
        await mgr.connect(g, "events:global")
        await mgr.connect(n, f"node:{node_id}")
        return g, n

    async def test_send_node_status_dual_channel(self):
        mgr = ConnectionManager()
        g, n = await self._connect_global_and_node(mgr, "n1")
        await mgr.send_node_status("n1", "online", hostname="host-1")
        for ws in (g, n):
            ws.send_json.assert_awaited_once()
            payload = ws.send_json.call_args.args[0]
            assert payload["type"] == "node_status"
            assert payload["node_id"] == "n1"
            assert payload["data"]["status"] == "online"
            assert payload["data"]["hostname"] == "host-1"

    async def test_send_health_update_dual_channel_payload(self):
        mgr = ConnectionManager()
        g, n = await self._connect_global_and_node(mgr, "n2")
        await mgr.send_health_update("n2", cpu=12.5, memory=40.0, disk=55.0, status="online")
        for ws in (g, n):
            payload = ws.send_json.call_args.args[0]
            assert payload["type"] == "health_update"
            assert payload["node_id"] == "n2"
            assert payload["data"]["cpu_percent"] == 12.5
            assert payload["data"]["memory_percent"] == 40.0
            assert payload["data"]["disk_percent"] == 55.0
            # last_heartbeat is auto-filled when not supplied.
            assert payload["data"]["last_heartbeat"]

    async def test_send_remediation_event_dual_channel(self):
        mgr = ConnectionManager()
        g, n = await self._connect_global_and_node(mgr, "n3")
        await mgr.send_remediation_event("n3", "restart_service", success=True, message="ok")
        for ws in (g, n):
            payload = ws.send_json.call_args.args[0]
            assert payload["type"] == "remediation_event"
            assert payload["node_id"] == "n3"
            assert payload["data"]["event_type"] == "restart_service"
            assert payload["data"]["success"] is True

    async def test_send_node_status_only_targets_matching_node_channel(self):
        """A watcher on node:other must NOT receive node:n1's status event."""
        mgr = ConnectionManager()
        other = _fake_ws()
        await mgr.connect(other, "node:other")
        await mgr.send_node_status("n1", "offline")
        other.send_json.assert_not_called()

    async def test_send_to_deployment_routes_to_deployment_channel(self):
        mgr = ConnectionManager()
        ws = _fake_ws()
        await mgr.connect(ws, "deployment:dep-1")
        await mgr.send_to_deployment("dep-1", {"type": "status", "status": "running"})
        ws.send_json.assert_awaited_once()
        assert ws.send_json.call_args.args[0]["status"] == "running"
