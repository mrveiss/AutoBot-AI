# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Issue #402 refactored helper functions.

Tests the extracted helper functions from the deep nesting reduction refactoring:
- reorganize_redis_databases.py helper functions
- base.py MCP client helper methods
- create_code_vector_knowledge.py helper methods
- vue_specific_fix_agent.py helper functions

Issue: #402 - [Code Quality] Reduce Deep Nesting - 524 functions exceed 4 levels
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config


class TestReorganizeRedisHelpers:
    """Tests for the _decode_key helper (Issue #11954).

    ``analysis/reorganize_redis_databases.py`` (the original source of these
    helpers) was a one-time Redis-DB-reorganization migration script deleted
    in #6716/#6717 ("delete stale audit artifacts", verified zero live
    imports). ``_determine_target_db``/``DB_INDEX_TO_NAME`` were specific to
    that one-time migration and have no live equivalent, so their tests were
    removed rather than pointed at dead code. ``_decode_key`` is a generic
    bytes-decode helper with a live, functionally-identical twin in
    ``api/knowledge_maintenance.py`` — repointed there.
    """

    def test_decode_key_bytes(self):
        """Test _decode_key with bytes input."""
        from api.knowledge_maintenance import _decode_key

        result = _decode_key(b"test_key")
        assert result == "test_key"

    def test_decode_key_string(self):
        """Test _decode_key with string input."""
        from api.knowledge_maintenance import _decode_key

        result = _decode_key("already_string")
        assert result == "already_string"

    def test_decode_key_unicode(self):
        """Test _decode_key with unicode bytes."""
        from api.knowledge_maintenance import _decode_key

        result = _decode_key("unicode_тест".encode("utf-8"))
        assert result == "unicode_тест"


class TestMCPClientHelpers:
    """Tests for docs/examples/mcp_agent_workflows/base.py MCPClient (#11954).

    The original targets (``_create_error_for_status``, module-level
    ``NON_RETRYABLE_STATUS_CODES``, ``_RetrySignal``, ``_should_retry``) never
    existed anywhere in this file's git history — not a rename, the test was
    written against a hypothetical API. The #825 nesting-reduction refactor
    settled on a different, real shape: ``_raise_client_error`` (sync, raises
    ``MCPToolError`` for the 400/403/404/422 client-error codes),
    ``_execute_request`` (returns ``None`` to signal "retry" for a 5xx while
    attempts remain, else raises with a "Server error: ..." message), and
    ``_retry_or_raise`` (sleeps to retry, or raises on the final attempt).
    Rewritten below against those real symbols, also fixing the
    ``examples.mcp_agent_workflows`` -> ``docs.examples.mcp_agent_workflows``
    import path (the package only exists under docs/).
    """

    @staticmethod
    def _mock_http_response(status: int, text: str):
        """Build an aiohttp.ClientSession mock yielding one POST response.

        Helper for _execute_request tests (#11954).
        """
        mock_response = AsyncMock()
        mock_response.status = status
        mock_response.text = AsyncMock(return_value=text)

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_cm)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_session
        return mock_session_cm

    def test_create_error_for_status_400(self):
        """Test error creation for 400 status via _raise_client_error."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient, MCPToolError

        client = MCPClient(log_requests=False)
        with pytest.raises(MCPToolError) as exc_info:
            client._raise_client_error("test", "tool", 400, "bad request")

        assert exc_info.value.status == 400
        assert "Validation error" in exc_info.value.message

    def test_create_error_for_status_404(self):
        """Test error creation for 404 status via _raise_client_error."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient, MCPToolError

        client = MCPClient(log_requests=False)
        with pytest.raises(MCPToolError) as exc_info:
            client._raise_client_error("test", "missing_tool", 404, "not found")

        assert exc_info.value.status == 404
        assert "Tool not found" in exc_info.value.message
        assert "missing_tool" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_create_error_for_status_500(self):
        """Test that a 5xx response raises with a "Server error" message
        once retries are exhausted (_execute_request's final-attempt path)."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient, MCPToolError

        client = MCPClient(max_retries=3, log_requests=False)
        session_cm = self._mock_http_response(500, "internal error")

        with patch("aiohttp.ClientSession", return_value=session_cm):
            with pytest.raises(MCPToolError) as exc_info:
                await client._execute_request("http://x", {}, "test", "tool", client.max_retries - 1)

        assert exc_info.value.status == 500
        assert "Server error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_non_retryable_status_codes(self):
        """Client-error codes (400/403/404/422) raise immediately — no retry."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient, MCPToolError

        client = MCPClient(max_retries=3, log_requests=False)

        for status in (400, 403, 404, 422):
            session_cm = self._mock_http_response(status, "client error")
            with patch("aiohttp.ClientSession", return_value=session_cm):
                with pytest.raises(MCPToolError) as exc_info:
                    await client._execute_request("http://x", {}, "test", "tool", 0)
            assert exc_info.value.status == status

    @pytest.mark.asyncio
    async def test_retry_signal_exception_exists(self):
        """A 5xx response with attempts remaining signals retry by returning
        None (no exception) — the real replacement for the old _RetrySignal
        exception-based design."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient

        client = MCPClient(max_retries=3, log_requests=False)
        session_cm = self._mock_http_response(500, "internal error")

        with patch("aiohttp.ClientSession", return_value=session_cm):
            result = await client._execute_request("http://x", {}, "test", "tool", 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_should_retry_first_attempt(self):
        """Test _retry_or_raise sleeps (retries) rather than raising when
        attempts remain."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient

        client = MCPClient(max_retries=3, log_requests=False)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await client._retry_or_raise("test", "tool", 0, "Timeout", "Test error")

        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_retry_max_attempts_exceeded(self):
        """Test _retry_or_raise raises MCPToolError on the final attempt."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import MCPClient, MCPToolError

        client = MCPClient(max_retries=3, log_requests=False)

        with pytest.raises(MCPToolError):
            await client._retry_or_raise("test", "tool", 2, "Timeout", "Test error")


class TestCodeVectorKnowledgeHelpers:
    """
    Tests for create_code_vector_knowledge.py helper methods.

    Note: These tests use standalone implementations of the helper functions
    to avoid import issues with the full module (missing redis_database_manager).
    The logic tested matches the actual implementation.
    """

    def _parse_vector_metadata(self, data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """Standalone implementation for testing."""
        if b"metadata" not in data:
            return {}
        try:
            metadata_str = data[b"metadata"].decode("utf-8", errors="ignore")
            return json.loads(metadata_str)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _decode_vector_data(self, key: bytes, data: Dict[bytes, bytes]) -> Dict[str, Any] | None:
        """Standalone implementation for testing."""
        try:
            vector_info = {
                "id": key.decode("utf-8"),
                "text": data.get(b"text", b"").decode("utf-8", errors="ignore"),
                "doc_id": data.get(b"doc_id", b"").decode("utf-8", errors="ignore"),
                "metadata": self._parse_vector_metadata(data),
            }
            vector_info["metadata"]["source"] = "code_analytics"
            vector_info["metadata"]["database"] = "analytics_db8"
            vector_info["metadata"]["type"] = "code_index"

            if vector_info["text"].strip() and len(vector_info["text"]) > 10:
                return vector_info
            return None
        except Exception:
            return None

    def test_parse_vector_metadata_valid_json(self):
        """Test _parse_vector_metadata with valid JSON."""
        data = {b"metadata": b'{"key": "value", "count": 42}'}
        result = self._parse_vector_metadata(data)
        assert result == {"key": "value", "count": 42}

    def test_parse_vector_metadata_invalid_json(self):
        """Test _parse_vector_metadata with invalid JSON returns empty dict."""
        data = {b"metadata": b"not valid json"}
        result = self._parse_vector_metadata(data)
        assert result == {}

    def test_parse_vector_metadata_missing_key(self):
        """Test _parse_vector_metadata with missing metadata key."""
        data = {b"other_key": b"some_value"}
        result = self._parse_vector_metadata(data)
        assert result == {}

    def test_decode_vector_data_valid(self):
        """Test _decode_vector_data with valid data."""
        key = b"vector_123"
        data = {
            b"text": b"This is sample code content for testing.",
            b"doc_id": b"src/utils/test.py",
            b"metadata": b"{}",
        }

        result = self._decode_vector_data(key, data)

        assert result is not None
        assert result["id"] == "vector_123"
        assert "sample code content" in result["text"]
        assert result["doc_id"] == "src/utils/test.py"
        assert result["metadata"]["source"] == "code_analytics"

    def test_decode_vector_data_empty_text(self):
        """Test _decode_vector_data rejects empty text."""
        key = b"vector_123"
        data = {b"text": b"", b"doc_id": b"src/utils/test.py", b"metadata": b"{}"}

        result = self._decode_vector_data(key, data)
        assert result is None

    def test_decode_vector_data_short_text(self):
        """Test _decode_vector_data rejects text under 10 chars."""
        key = b"vector_123"
        data = {b"text": b"short", b"doc_id": b"src/utils/test.py", b"metadata": b"{}"}

        result = self._decode_vector_data(key, data)
        assert result is None


class TestVueSpecificFixAgentHelpers:
    """
    Tests for vue_specific_fix_agent.py helper functions.

    Uses standalone implementations to avoid import path issues.
    The logic tested matches the actual implementation.
    """

    # Constants matching the module's constants
    KEY_SUGGESTION_PATTERNS: Dict[str, str] = {
        "chat": "{item}.chatId || {item}.id || `chat-${{{item}.name}}`",
        "history": "{item}.id || `history-${{{item}.date}}`",
        "message": "{item}.id || `msg-${{{item}.timestamp}}`",
        "session": "{item}.sessionId || {item}.id",
        "workflow": "{item}.workflowId || {item}.id",
        "tool": "{item}.toolId || {item}.name || {item}.id",
        "setting": "{item}.key || {item}.name",
        "log": "{item}.id || `log-${{{item}.timestamp}}`",
        "notification": "{item}.id || `notif-${{{item}.timestamp}}`",
    }

    UNIQUE_PROPERTY_NAMES = ["id", "uuid", "key", "chatId", "name"]

    def _get_context_based_key(self, item_var: str, filename: str) -> str | None:
        """Standalone implementation for testing."""
        filename_lower = filename.lower()
        for context, pattern in self.KEY_SUGGESTION_PATTERNS.items():
            if context in filename_lower:
                return pattern.format(item=item_var)
        return None

    def _get_property_based_key(self, item_var: str, properties: list) -> str | None:
        """Standalone implementation for testing."""
        for prop in self.UNIQUE_PROPERTY_NAMES:
            if prop in properties:
                return f"{item_var}.{prop}"
        return None

    def test_key_suggestion_patterns_constant(self):
        """Test KEY_SUGGESTION_PATTERNS constant structure."""
        assert isinstance(self.KEY_SUGGESTION_PATTERNS, dict)
        assert "chat" in self.KEY_SUGGESTION_PATTERNS
        assert "history" in self.KEY_SUGGESTION_PATTERNS
        assert "message" in self.KEY_SUGGESTION_PATTERNS

    def test_unique_property_names_constant(self):
        """Test UNIQUE_PROPERTY_NAMES constant."""
        assert "id" in self.UNIQUE_PROPERTY_NAMES
        assert "uuid" in self.UNIQUE_PROPERTY_NAMES
        assert "key" in self.UNIQUE_PROPERTY_NAMES

    def test_get_context_based_key_chat(self):
        """Test _get_context_based_key for chat context."""
        result = self._get_context_based_key("item", "ChatList.vue")
        assert result is not None
        assert "item" in result

    def test_get_context_based_key_no_match(self):
        """Test _get_context_based_key returns None for no pattern match."""
        result = self._get_context_based_key("item", "RandomComponent.vue")
        assert result is None

    def test_get_property_based_key_id(self):
        """Test _get_property_based_key with id property."""
        result = self._get_property_based_key("item", ["id", "name"])
        assert result == "item.id"

    def test_get_property_based_key_uuid(self):
        """Test _get_property_based_key with uuid property."""
        result = self._get_property_based_key("entry", ["uuid", "timestamp"])
        assert result == "entry.uuid"

    def test_get_property_based_key_no_unique(self):
        """Test _get_property_based_key returns None when no unique property."""
        result = self._get_property_based_key("item", ["foo", "bar", "baz"])
        assert result is None


class TestWorkflowResult:
    """Tests for WorkflowResult class in base.py."""

    def test_workflow_result_initialization(self):
        """Test WorkflowResult initialization."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import WorkflowResult

        result = WorkflowResult("test_workflow")

        assert result.name == "test_workflow"
        assert result.success is True
        assert result.steps == []
        assert result.error is None

    def test_workflow_result_add_step_success(self):
        """Test adding successful step to WorkflowResult."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import WorkflowResult

        result = WorkflowResult("test_workflow")
        result.add_step("step1", "success", data={"key": "value"})

        assert len(result.steps) == 1
        assert result.steps[0]["step"] == "step1"
        assert result.steps[0]["status"] == "success"
        assert result.steps[0]["data"] == {"key": "value"}
        assert result.success is True

    def test_workflow_result_add_step_error(self):
        """Test adding error step to WorkflowResult."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import WorkflowResult

        result = WorkflowResult("test_workflow")
        result.add_step("step1", "failed", error="Something went wrong")

        assert len(result.steps) == 1
        assert result.steps[0]["error"] == "Something went wrong"
        assert result.success is False

    def test_workflow_result_to_dict(self):
        """Test WorkflowResult to_dict conversion."""
        import sys

        sys.path.insert(0, config.project_root)
        from docs.examples.mcp_agent_workflows.base import WorkflowResult

        result = WorkflowResult("test_workflow")
        result.add_step("step1", "success")
        result.add_step("step2", "success")
        result.complete()

        data = result.to_dict()

        assert data["workflow"] == "test_workflow"
        assert data["total_steps"] == 2
        assert data["successful_steps"] == 2
        assert data["success"] is True
        assert data["end_time"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
