# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for SLM WebSocket API.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from api.slm.websockets import SLMWebSocketManager, create_reconciler_callbacks
from starlette.websockets import WebSocketState


class TestSLMWebSocketManager:
    """Test SLM WebSocket manager functionality."""

    @pytest.fixture
    def manager(self):
        """Create fresh WebSocket manager for each test."""
        return SLMWebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_connect_adds_client(self, manager, mock_websocket):
        """Test client is added on connect."""
        assert manager.client_count == 0

        await manager.connect(mock_websocket)

        assert manager.client_count == 1
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_subscriptions(self, manager, mock_websocket):
        """Test client subscriptions are stored."""
        await manager.connect(mock_websocket, subscriptions=["state_change", "alert"])

        assert mock_websocket in manager._client_subscriptions
        assert manager._client_subscriptions[mock_websocket] == {
            "state_change",
            "alert",
        }

    @pytest.mark.asyncio
    async def test_connect_default_all_events(self, manager, mock_websocket):
        """Test default subscription is all events."""
        await manager.connect(mock_websocket)

        assert manager._client_subscriptions[mock_websocket] == {"*"}

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, manager, mock_websocket):
        """Test client is removed on disconnect."""
        await manager.connect(mock_websocket)
        assert manager.client_count == 1

        await manager.disconnect(mock_websocket)

        assert manager.client_count == 0
        assert mock_websocket not in manager._client_subscriptions

    @pytest.mark.asyncio
    async def test_broadcast_to_all_clients(self, manager, mock_websocket):
        """Test broadcast sends to all connected clients."""
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED

        await manager.connect(mock_websocket)
        await manager.connect(ws2)

        await manager.broadcast("test_event", {"key": "value"})

        mock_websocket.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_filters_by_subscription(self, manager, mock_websocket):
        """Test broadcast only sends to subscribed clients."""
        # Subscribe only to state_change
        await manager.connect(mock_websocket, subscriptions=["state_change"])

        # Broadcast alert event
        await manager.broadcast("alert", {"level": "warning"})

        # Should not receive (not subscribed)
        mock_websocket.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_star_receives_all(self, manager, mock_websocket):
        """Test wildcard subscription receives all events."""
        await manager.connect(mock_websocket)  # Default is ["*"]

        await manager.broadcast("any_event", {})

        mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected(self, manager, mock_websocket):
        """Test disconnected clients are removed during broadcast."""
        mock_websocket.send_json.side_effect = Exception("Connection closed")
        await manager.connect(mock_websocket)

        await manager.broadcast("test", {})

        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_state_change(self, manager, mock_websocket):
        """Test state change broadcast."""
        await manager.connect(mock_websocket)

        await manager.broadcast_state_change(
            node_id="node-1",
            old_state="online",
            new_state="degraded",
            node_name="test-node",
        )

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "state_change"
        assert call_args["data"]["node_id"] == "node-1"
        assert call_args["data"]["old_state"] == "online"
        assert call_args["data"]["new_state"] == "degraded"

    @pytest.mark.asyncio
    async def test_broadcast_alert(self, manager, mock_websocket):
        """Test alert broadcast."""
        await manager.connect(mock_websocket)

        await manager.broadcast_alert(
            node_id="node-1",
            level="warning",
            details={"message": "Node degraded"},
        )

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "alert"
        assert call_args["data"]["level"] == "warning"
        assert call_args["data"]["message"] == "Node degraded"

    @pytest.mark.asyncio
    async def test_broadcast_health_update(self, manager, mock_websocket):
        """Test health update broadcast."""
        await manager.connect(mock_websocket)

        await manager.broadcast_health_update(
            node_id="node-1",
            health_data={"cpu_percent": 45.2, "memory_percent": 62.1},
        )

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "health_update"
        assert call_args["data"]["cpu_percent"] == 45.2


class TestReconcilerCallbacks:
    """Test reconciler callback factory."""

    def test_create_callbacks_returns_tuple(self):
        """Test callback factory returns two functions."""
        on_state_change, on_alert = create_reconciler_callbacks()

        assert callable(on_state_change)
        assert callable(on_alert)

    @pytest.mark.asyncio
    async def test_state_change_callback_broadcasts(self):
        """Test state change callback triggers broadcast."""
        with patch("api.slm.websockets.get_ws_manager") as mock_get:
            mock_manager = AsyncMock()
            mock_get.return_value = mock_manager

            on_state_change, _ = create_reconciler_callbacks()

            # Call the callback (it creates a task)
            on_state_change("node-1", "online", "degraded")

            # Allow task to run
            await asyncio.sleep(0.1)

            mock_manager.broadcast_state_change.assert_called_once_with(
                "node-1", "online", "degraded"
            )

    @pytest.mark.asyncio
    async def test_alert_callback_broadcasts(self):
        """Test alert callback triggers broadcast."""
        with patch("api.slm.websockets.get_ws_manager") as mock_get:
            mock_manager = AsyncMock()
            mock_get.return_value = mock_manager

            _, on_alert = create_reconciler_callbacks()

            on_alert("node-1", "warning", {"message": "test"})

            await asyncio.sleep(0.1)

            mock_manager.broadcast_alert.assert_called_once_with(
                "node-1", "warning", {"message": "test"}
            )
