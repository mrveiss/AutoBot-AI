# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test suite for refactored WorkerNode with Strategy Pattern

Verifies that the refactored execute_task method maintains
all original functionality while reducing nesting depth.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.task_handlers import TaskExecutor
from src.worker_node import WorkerNode


class TestWorkerNodeRefactored:
    """Test refactored WorkerNode functionality"""

    @pytest.fixture
    def worker_node(self):
        """Create a WorkerNode instance for testing"""
        with patch("src.worker_node.get_redis_client", return_value=None):
            worker = WorkerNode()
            # Mock the modules to avoid dependencies
            worker.llm_interface = MagicMock()
            worker.knowledge_base = MagicMock()
            worker.gui_controller = MagicMock()
            worker.system_integration = MagicMock()
            worker.security_layer = MagicMock()
            worker.security_layer.check_permission = MagicMock(return_value=True)
            worker.security_layer.audit_log = MagicMock()
            return worker

    def test_task_executor_initialized(self, worker_node):
        """Test that TaskExecutor is properly initialized"""
        assert hasattr(worker_node, "task_executor")
        assert isinstance(worker_node.task_executor, TaskExecutor)

    def test_task_executor_has_handlers(self, worker_node):
        """Test that TaskExecutor has all expected handlers registered"""
        expected_task_types = [
            "llm_chat_completion",
            "kb_add_file",
            "kb_search",
            "kb_store_fact",
            "execute_shell_command",
            "gui_click_element",
            "gui_read_text_from_region",
            "gui_type_text",
            "gui_move_mouse",
            "gui_bring_window_to_front",
            "system_query_info",
            "system_list_services",
            "system_manage_service",
            "system_execute_command",
            "system_get_process_info",
            "system_terminate_process",
            "web_fetch",
            "respond_conversationally",
            "ask_user_for_manual",
            "ask_user_command_approval",
        ]

        registered_types = worker_node.task_executor.get_supported_task_types()

        for task_type in expected_task_types:
            assert (
                task_type in registered_types
            ), f"Task type '{task_type}' not registered"

    @pytest.mark.asyncio
    async def test_permission_denied(self, worker_node):
        """Test that permission denied is handled correctly"""
        worker_node.security_layer.check_permission = MagicMock(return_value=False)

        task_payload = {
            "type": "llm_chat_completion",
            "task_id": "test_123",
            "user_role": "guest",
            "model_name": "test_model",
            "messages": [],
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "error"
        assert "Permission denied" in result["message"]
        worker_node.security_layer.audit_log.assert_called()

    @pytest.mark.asyncio
    async def test_unknown_task_type(self, worker_node):
        """Test that unknown task types are handled gracefully"""
        task_payload = {
            "type": "unknown_task_type",
            "task_id": "test_123",
            "user_role": "admin",
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "error"
        assert "Unsupported task type" in result["message"]

    @pytest.mark.asyncio
    async def test_llm_chat_completion_success(self, worker_node):
        """Test successful LLM chat completion task"""
        worker_node.llm_interface.chat_completion = AsyncMock(
            return_value="Test response"
        )

        task_payload = {
            "type": "llm_chat_completion",
            "task_id": "test_123",
            "user_role": "admin",
            "model_name": "test_model",
            "messages": [{"role": "user", "content": "test"}],
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "success"
        assert "response" in result
        worker_node.llm_interface.chat_completion.assert_called_once()
        worker_node.security_layer.audit_log.assert_called()

    @pytest.mark.asyncio
    async def test_kb_search_success(self, worker_node):
        """Test successful knowledge base search task"""
        worker_node.knowledge_base.search = AsyncMock(
            return_value=[{"content": "test result"}]
        )

        task_payload = {
            "type": "kb_search",
            "task_id": "test_123",
            "user_role": "admin",
            "query": "test query",
            "n_results": 5,
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "success"
        assert "results" in result
        worker_node.knowledge_base.search.assert_called_once_with("test query", 5)

    @pytest.mark.asyncio
    async def test_system_query_info(self, worker_node):
        """Test system query info task"""
        worker_node.system_integration.query_system_info = MagicMock(
            return_value={"status": "success", "info": {}}
        )

        task_payload = {
            "type": "system_query_info",
            "task_id": "test_123",
            "user_role": "admin",
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "success"
        worker_node.system_integration.query_system_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_required_parameter(self, worker_node):
        """Test that missing required parameters are handled"""
        task_payload = {
            "type": "llm_chat_completion",
            "task_id": "test_123",
            "user_role": "admin",
            # Missing required 'model_name' and 'messages'
        }

        result = await worker_node.execute_task(task_payload)

        assert result["status"] == "error"
        assert "parameter" in result["message"].lower()

    def test_reduced_nesting_depth(self):
        """
        Verify that the refactored execute_task has reduced nesting.

        This is a structural test to ensure the refactoring goal is met.
        """
        import inspect

        source = inspect.getsource(WorkerNode.execute_task)
        lines = source.split("\n")

        # Count maximum indentation depth
        max_indent = 0
        for line in lines:
            if line.strip():  # Ignore empty lines
                indent = len(line) - len(line.lstrip())
                max_indent = max(max_indent, indent)

        # Maximum nesting should be significantly reduced from original 21
        # New implementation should have max depth around 4-6
        assert max_indent <= 24, f"Nesting depth too high: {max_indent} spaces"

    def test_line_count_reduction(self):
        """
        Verify that execute_task method has significantly fewer lines.

        Original was 424 lines, new version should be ~60 lines.
        """
        import inspect

        source = inspect.getsource(WorkerNode.execute_task)
        lines = [line for line in source.split("\n") if line.strip()]

        # Allow some buffer, but should be dramatically reduced
        assert (
            len(lines) < 100
        ), f"execute_task method still too long: {len(lines)} lines"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
