# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Operation Timeout Integration - Issue #712."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils.long_running_operations_framework import (
    OperationPriority,
    OperationStatus,
    OperationType,
)
from backend.utils.operation_timeout_integration import (
    CreateOperationRequest,
    OperationIntegrationManager,
    OperationMigrator,
    ProgressUpdateRequest,
    long_running_operation,
)


class TestPydanticModels:
    """Tests for Pydantic request/response models."""

    def test_create_operation_request(self):
        req = CreateOperationRequest(
            operation_type="code_analysis",
            name="Test Op",
            description="Test description",
        )
        assert req.operation_type == "code_analysis"
        assert req.name == "Test Op"
        assert req.priority == "normal"
        assert req.execute_immediately is False

    def test_create_operation_request_with_options(self):
        req = CreateOperationRequest(
            operation_type="codebase_indexing",
            name="Index",
            description="Full index",
            priority="high",
            estimated_items=1000,
            execute_immediately=True,
        )
        assert req.priority == "high"
        assert req.estimated_items == 1000
        assert req.execute_immediately is True

    def test_progress_update_request(self):
        req = ProgressUpdateRequest(
            operation_id="op-123",
            current_step="Processing",
            processed_items=50,
            total_items=100,
        )
        assert req.operation_id == "op-123"
        assert req.processed_items == 50


class TestOperationIntegrationManager:
    """Tests for OperationIntegrationManager class."""

    def test_init(self):
        manager = OperationIntegrationManager()
        assert manager.redis_client is None
        assert manager.operation_manager is None
        assert manager.websocket_connections == {}
        assert manager.router is not None

    def test_router_has_routes(self):
        manager = OperationIntegrationManager()
        routes = [r.path for r in manager.router.routes]
        assert "/create" in routes or any("/create" in str(r) for r in routes)

    @pytest.mark.asyncio
    async def test_initialize_without_redis(self):
        manager = OperationIntegrationManager(redis_url="redis://invalid:6379/9")
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
            mock_redis.return_value = mock_client
            await manager.initialize()
            assert manager.redis_client is None or manager.operation_manager is not None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        manager = OperationIntegrationManager()
        manager.operation_manager = MagicMock()
        manager.operation_manager.stop_background_processor = AsyncMock()
        manager.redis_client = AsyncMock()
        manager.redis_client.close = AsyncMock()
        await manager.shutdown()

    def test_get_all_operations_empty(self):
        manager = OperationIntegrationManager()
        manager.operation_manager = None
        assert manager.get_all_operations() == []

    def test_get_all_operations_with_manager(self):
        manager = OperationIntegrationManager()
        manager.operation_manager = MagicMock()
        mock_op = MagicMock()
        manager.operation_manager.operations = {"op1": mock_op}
        ops = manager.get_all_operations()
        assert len(ops) == 1

    @pytest.mark.asyncio
    async def test_list_operation_checkpoints_no_manager(self):
        manager = OperationIntegrationManager()
        manager.operation_manager = None
        result = await manager.list_operation_checkpoints("op-123")
        assert result == []

    def test_calculate_operation_stats(self):
        manager = OperationIntegrationManager()
        manager.operation_manager = MagicMock()

        mock_ops = []
        for status in [
            OperationStatus.RUNNING,
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
        ]:
            op = MagicMock()
            op.status = status
            mock_ops.append(op)

        manager.operation_manager.operations = {
            f"op{i}": op for i, op in enumerate(mock_ops)
        }
        total, active, completed, failed = manager._calculate_operation_stats()
        assert total == 3
        assert active == 1
        assert completed == 1
        assert failed == 1


class TestOperationWrappers:
    """Tests for operation wrapper methods."""

    def test_get_operation_function_codebase_indexing(self):
        manager = OperationIntegrationManager()
        func = manager._get_operation_function(
            OperationType.CODEBASE_INDEXING, {"codebase_path": "/test"}
        )
        assert callable(func)

    def test_get_operation_function_test_suite(self):
        manager = OperationIntegrationManager()
        func = manager._get_operation_function(
            OperationType.COMPREHENSIVE_TEST_SUITE, {"test_path": "/tests"}
        )
        assert callable(func)

    def test_get_operation_function_code_analysis(self):
        manager = OperationIntegrationManager()
        func = manager._get_operation_function(OperationType.CODE_ANALYSIS, {})
        assert callable(func)

    def test_get_operation_function_kb_population(self):
        manager = OperationIntegrationManager()
        func = manager._get_operation_function(OperationType.KB_POPULATION, {})
        assert callable(func)

    def test_get_operation_function_invalid_type(self):
        manager = OperationIntegrationManager()
        with pytest.raises(ValueError):
            manager._get_operation_function(MagicMock(value="invalid"), {})

    @pytest.mark.asyncio
    async def test_collect_test_files(self):
        manager = OperationIntegrationManager()
        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_rglob.return_value = []
            result = await manager._collect_test_files("/tests", ["test_*.py"])
            assert result == []

    def test_calculate_test_success_rate_empty(self):
        manager = OperationIntegrationManager()
        assert manager._calculate_test_success_rate([]) == 0.0

    def test_calculate_test_success_rate(self):
        manager = OperationIntegrationManager()
        results = [
            {"exit_code": 0},
            {"exit_code": 0},
            {"exit_code": 1},
        ]
        rate = manager._calculate_test_success_rate(results)
        assert abs(rate - 66.67) < 1


class TestBroadcastProgress:
    """Tests for WebSocket broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        manager = OperationIntegrationManager()
        await manager._broadcast_progress_update({"operation_id": "op-123"})

    @pytest.mark.asyncio
    async def test_broadcast_with_connections(self):
        manager = OperationIntegrationManager()
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        manager.websocket_connections["op-123"] = [mock_ws]

        await manager._broadcast_progress_update(
            {"operation_id": "op-123", "progress": 50}
        )
        mock_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected(self):
        manager = OperationIntegrationManager()
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=Exception("Disconnected"))
        manager.websocket_connections["op-123"] = [mock_ws]

        await manager._broadcast_progress_update({"operation_id": "op-123"})
        assert mock_ws not in manager.websocket_connections.get("op-123", [])


class TestOperationMigrator:
    """Tests for OperationMigrator class."""

    def test_wrap_existing_function_with_progress(self):
        async def original():
            return "result"

        wrapped = OperationMigrator.wrap_existing_function_with_progress(original)
        assert callable(wrapped)

    def test_wrap_function_with_progress_callback(self):
        async def original(progress_callback=None):
            if progress_callback:
                progress_callback("step", 1, 10)
            return "result"

        wrapped = OperationMigrator.wrap_existing_function_with_progress(original)
        assert callable(wrapped)


class TestLongRunningOperationDecorator:
    """Tests for long_running_operation decorator."""

    def test_decorator_creates_wrapper(self):
        @long_running_operation(
            OperationType.CODE_ANALYSIS,
            name="Test Analysis",
            estimated_items=100,
        )
        async def test_func():
            return "done"

        assert asyncio.iscoroutinefunction(test_func)

    def test_decorator_with_priority(self):
        @long_running_operation(
            OperationType.CODEBASE_INDEXING,
            name="Priority Index",
            priority=OperationPriority.HIGH,
        )
        async def priority_func():
            return "indexed"

        assert asyncio.iscoroutinefunction(priority_func)


class TestTerminalStatuses:
    """Tests for operation status constants."""

    def test_failed_statuses(self):
        from utils.operation_timeout_integration import FAILED_OPERATION_STATUSES

        assert OperationStatus.FAILED in FAILED_OPERATION_STATUSES
        assert OperationStatus.TIMEOUT in FAILED_OPERATION_STATUSES

    def test_terminal_statuses(self):
        from utils.operation_timeout_integration import TERMINAL_OPERATION_STATUSES

        assert OperationStatus.COMPLETED in TERMINAL_OPERATION_STATUSES
        assert OperationStatus.FAILED in TERMINAL_OPERATION_STATUSES
        assert OperationStatus.CANCELLED in TERMINAL_OPERATION_STATUSES
