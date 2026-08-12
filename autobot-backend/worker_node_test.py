# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test suite for refactored WorkerNode with Strategy Pattern

Verifies that the refactored execute_task method maintains
all original functionality while reducing nesting depth.
"""

import ast
import inspect
import sys
import textwrap
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_handlers import TaskExecutor
from worker_node import WorkerNode


class TestWorkerNodeRefactored:
    """Test refactored WorkerNode functionality"""

    @pytest.fixture
    def worker_node(self):
        """Create a WorkerNode instance for testing"""
        with patch("worker_node.get_redis_client", return_value=None):
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
            assert task_type in registered_types, f"Task type '{task_type}' not registered"

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
        worker_node.llm_interface.chat_completion = AsyncMock(return_value="Test response")

        task_payload = {
            "type": "llm_chat_completion",
            "task_id": "test_123",
            "user_role": "admin",
            "model_name": "test_model",
            "messages": [{"role": "user", "content": "test"}],
        }

        result = await worker_node.execute_task(task_payload)

        # #7154: worker_node now wraps every response in a {status, message,
        # data} envelope. The actual response sits at result["data"]["response"].
        assert result["status"] == "success"
        assert "data" in result
        assert "response" in result["data"]
        worker_node.llm_interface.chat_completion.assert_called_once()
        worker_node.security_layer.audit_log.assert_called()

    @pytest.mark.asyncio
    async def test_kb_search_success(self, worker_node):
        """Test successful knowledge base search task"""
        worker_node.knowledge_base.search = AsyncMock(return_value=[{"content": "test result"}])

        task_payload = {
            "type": "kb_search",
            "task_id": "test_123",
            "user_role": "admin",
            "query": "test query",
            "n_results": 5,
        }

        result = await worker_node.execute_task(task_payload)

        # #7154: worker_node envelope — actual results at result["data"]["results"].
        assert result["status"] == "success"
        assert "data" in result
        assert "results" in result["data"]
        worker_node.knowledge_base.search.assert_called_once_with("test query", 5)

    @pytest.mark.asyncio
    async def test_system_query_info(self, worker_node):
        """Test system query info task"""
        worker_node.system_integration.query_system_info = MagicMock(return_value={"status": "success", "info": {}})

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

    # #13311 triage: these two stay source-level. They are *complexity metrics*,
    # not behavioural contracts asserted by grep — "how deeply nested is this
    # function" has no runtime observable, so measuring the code is the only
    # way to measure it. What changed is that they now measure the syntax tree
    # rather than leading whitespace: a wrapped argument list or a black
    # reformat used to move the number without changing the nesting at all.

    MAX_BLOCK_DEPTH = 6
    MAX_STATEMENTS = 100

    @staticmethod
    def _execute_task_ast() -> ast.AST:
        return ast.parse(textwrap.dedent(inspect.getsource(WorkerNode.execute_task))).body[0]

    @classmethod
    def _block_depth(cls, node, depth: int = 0) -> int:
        """Deepest nesting of control-flow blocks, ignoring line wrapping."""
        nesting = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
        deepest = depth
        for child in ast.iter_child_nodes(node):
            child_depth = depth + 1 if isinstance(child, nesting) else depth
            deepest = max(deepest, cls._block_depth(child, child_depth))
        return deepest

    def test_reduced_nesting_depth(self):
        """The refactoring goal: nesting well below the original 21 levels."""
        depth = self._block_depth(self._execute_task_ast())

        assert depth <= self.MAX_BLOCK_DEPTH, f"execute_task nests {depth} blocks deep (limit {self.MAX_BLOCK_DEPTH})"

    def test_the_depth_metric_counts_nesting_not_indentation(self):
        """Guard the guard: a metric that always returns 0 passes everything."""
        deep = ast.parse("def f():\n if a:\n  for b in c:\n   while d:\n    pass\n").body[0]
        wrapped = ast.parse("def f():\n return g(\n  1,\n  2,\n )\n").body[0]

        assert self._block_depth(deep) == 3
        assert self._block_depth(wrapped) == 0, "line wrapping must not read as nesting"

    def test_line_count_reduction(self):
        """Original was 424 lines; the refactor targeted roughly 60."""
        statements = sum(1 for node in ast.walk(self._execute_task_ast()) if isinstance(node, ast.stmt))

        assert statements < self.MAX_STATEMENTS, f"execute_task still has {statements} statements"


class TestGUIControllerPlatformGate:
    """Issue #11970: the GUIController platform gate must select the real
    (pyautogui/Xvfb) controller on Linux and the no-op dummy elsewhere --
    NOT the previously-inverted opposite.
    """

    @pytest.fixture(autouse=True)
    def _restore_real_worker_node_module(self):
        """Reload the real worker_node module after each test in this class.

        Tests here mutate sys.modules['worker_node'] via reload-under-mock;
        leaving a mocked-platform copy cached in sys.modules could leak into
        any other code in the same session that does `import worker_node`.
        """
        yield
        sys.modules.pop("worker_node", None)
        import worker_node  # noqa: F401 - re-import restores the real module state

    def _reload_worker_node(self, monkeypatch, platform: str, fake_gui_controller=None):
        """Reload worker_node with a mocked platform + gui_controller import."""
        monkeypatch.setattr(sys, "platform", platform)
        if fake_gui_controller is not None:
            monkeypatch.setitem(sys.modules, "gui_controller", fake_gui_controller)
        else:
            # Force `from gui_controller import GUIController` to raise ImportError.
            monkeypatch.setitem(sys.modules, "gui_controller", None)
        sys.modules.pop("worker_node", None)
        import worker_node as reloaded

        return reloaded

    def _make_fake_gui_controller_module(self):
        """Build a minimal fake gui_controller module exposing GUIController."""
        mod = types.ModuleType("gui_controller")

        class FakeGUIController:
            pass

        mod.GUIController = FakeGUIController
        return mod

    def test_linux_with_display_uses_real_controller(self, monkeypatch):
        """Linux + a reachable display must select gui_controller (real)."""
        fake_module = self._make_fake_gui_controller_module()

        reloaded = self._reload_worker_node(monkeypatch, "linux", fake_gui_controller=fake_module)

        assert reloaded.GUIController is fake_module.GUIController
        assert reloaded.GUI_AUTOMATION_SUPPORTED is True

    def test_linux_headless_falls_back_to_dummy(self, monkeypatch):
        """Linux with no display available (import failure) must fall back
        to gui_controller_dummy rather than crashing worker startup.
        """
        import gui_controller_dummy

        reloaded = self._reload_worker_node(monkeypatch, "linux", fake_gui_controller=None)

        assert reloaded.GUIController is gui_controller_dummy.GUIController
        assert reloaded.GUI_AUTOMATION_SUPPORTED is False

    def test_non_linux_uses_dummy_controller(self, monkeypatch):
        """Non-Linux platforms must always use the no-op dummy controller."""
        import gui_controller_dummy

        fake_module = self._make_fake_gui_controller_module()
        reloaded = self._reload_worker_node(monkeypatch, "win32", fake_gui_controller=fake_module)

        assert reloaded.GUIController is gui_controller_dummy.GUIController
        assert reloaded.GUI_AUTOMATION_SUPPORTED is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
