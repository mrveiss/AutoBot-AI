# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #654 - Explicit Response Tool (break_loop) pattern.

Tests verify:
1. The respond tool is parsed correctly from LLM responses
2. The break_loop flag is extracted and honored
3. The continuation loop stops when break_loop=True
4. Regular execute_command tools still work as before
"""

import pytest

# Test fixtures for tool call parsing


class TestRespondToolParsing:
    """Test that respond tool calls are parsed correctly."""

    def test_parse_respond_tool_basic(self):
        """Test basic respond tool parsing."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        text = """Here is the summary.
<TOOL_CALL name="respond" params='{"text":"Task completed successfully"}'>Final response</TOOL_CALL>
"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "respond"
        assert tool_calls[0]["params"]["text"] == "Task completed successfully"

    def test_parse_respond_tool_with_break_loop_true(self):
        """Test respond tool with explicit break_loop=true."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        text = """<TOOL_CALL name="respond" params='{"text":"Done!","break_loop":true}'>Complete</TOOL_CALL>"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "respond"
        assert tool_calls[0]["params"]["text"] == "Done!"
        assert tool_calls[0]["params"]["break_loop"] is True

    def test_parse_respond_tool_with_break_loop_false(self):
        """Test respond tool with break_loop=false (continue loop)."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        text = """<TOOL_CALL name="respond" params='{"text":"Partial update","break_loop":false}'>Update</TOOL_CALL>"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "respond"
        assert tool_calls[0]["params"]["break_loop"] is False

    def test_parse_mixed_tool_calls(self):
        """Test parsing both execute_command and respond tools."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        text = """Let me run this command first.
<TOOL_CALL name="execute_command" params='{"command":"ls -la"}'>List files</TOOL_CALL>

Now the final summary:
<TOOL_CALL name="respond" params='{"text":"Found 10 files in the directory"}'>Done</TOOL_CALL>
"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 2
        assert tool_calls[0]["name"] == "execute_command"
        assert tool_calls[1]["name"] == "respond"

    def test_parse_respond_tool_with_newlines_in_text(self):
        """Test respond tool with newlines in the text parameter."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        # JSON with escaped newlines
        text = r"""<TOOL_CALL name="respond" params='{"text":"Line 1\nLine 2\nLine 3"}'>Summary</TOOL_CALL>"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "respond"
        assert "Line 1" in tool_calls[0]["params"]["text"]


class TestRespondToolProcessing:
    """Test that respond tool is processed correctly in _process_tool_calls."""

    @pytest.mark.asyncio
    async def test_process_respond_tool_yields_response_message(self):
        """Test that respond tool yields a WorkflowMessage with type=response."""
        from src.async_chat_workflow import WorkflowMessage
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None  # Not needed for respond tool

        tool_calls = [
            {
                "name": "respond",
                "params": {"text": "Task completed successfully", "break_loop": True},
                "description": "Final response",
            }
        ]

        messages = []
        break_loop_result = None

        async for item in handler._process_tool_calls(
            tool_calls, "session_1", "terminal_1", "http://localhost:11434", "llama3"
        ):
            if isinstance(item, tuple):
                break_loop_result = item
            elif isinstance(item, WorkflowMessage):
                messages.append(item)

        # Should have yielded a response message
        response_msgs = [m for m in messages if m.type == "response"]
        assert len(response_msgs) == 1
        assert response_msgs[0].content == "Task completed successfully"
        assert response_msgs[0].metadata.get("break_loop") is True
        assert response_msgs[0].metadata.get("explicit_completion") is True

        # Should have yielded break_loop signal
        assert break_loop_result is not None
        assert break_loop_result[0] is True  # break_loop_requested

    @pytest.mark.asyncio
    async def test_process_respond_tool_default_break_loop(self):
        """Test that respond tool defaults to break_loop=True."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None

        # No break_loop specified - should default to True
        tool_calls = [
            {"name": "respond", "params": {"text": "Done"}, "description": "Complete"}
        ]

        break_loop_result = None
        async for item in handler._process_tool_calls(
            tool_calls, "session_1", "terminal_1", "http://localhost:11434", "llama3"
        ):
            if isinstance(item, tuple):
                break_loop_result = item

        assert break_loop_result is not None
        assert break_loop_result[0] is True  # Defaults to True

    @pytest.mark.asyncio
    async def test_process_respond_tool_break_loop_false(self):
        """Test respond tool with break_loop=False continues the loop."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None

        tool_calls = [
            {
                "name": "respond",
                "params": {"text": "Partial update", "break_loop": False},
                "description": "Update",
            }
        ]

        break_loop_result = None
        async for item in handler._process_tool_calls(
            tool_calls, "session_1", "terminal_1", "http://localhost:11434", "llama3"
        ):
            if isinstance(item, tuple):
                break_loop_result = item

        assert break_loop_result is not None
        assert break_loop_result[0] is False  # break_loop=False

    @pytest.mark.asyncio
    async def test_process_unknown_tool_skipped(self):
        """Test that unknown tools are skipped (not processed)."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None

        tool_calls = [
            {"name": "unknown_tool", "params": {"foo": "bar"}, "description": "Unknown"}
        ]

        messages = []
        async for item in handler._process_tool_calls(
            tool_calls, "session_1", "terminal_1", "http://localhost:11434", "llama3"
        ):
            if not isinstance(item, tuple):
                messages.append(item)

        # No messages should be yielded for unknown tools
        # Only the final tuple is yielded
        assert len(messages) == 0


class TestBreakLoopIntegration:
    """Test that break_loop signal properly stops the continuation loop."""

    @pytest.mark.asyncio
    async def test_break_loop_stops_continuation(self):
        """Test that break_loop=True stops the continuation loop."""
        # This is an integration test that would require mocking the full manager
        # For now, we verify the tuple structure is correct
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None

        tool_calls = [
            {
                "name": "respond",
                "params": {"text": "Done", "break_loop": True},
                "description": "",
            }
        ]

        final_tuple = None
        async for item in handler._process_tool_calls(
            tool_calls, "s1", "t1", "http://localhost:11434", "llama3"
        ):
            if isinstance(item, tuple) and len(item) == 2:
                final_tuple = item

        # The tuple should signal break_loop=True
        assert final_tuple is not None
        break_loop_requested, respond_content = final_tuple
        assert break_loop_requested is True
        assert respond_content == "Done"


class TestBackwardsCompatibility:
    """Test that existing execute_command tools still work."""

    def test_execute_command_still_parsed(self):
        """Test that execute_command tools are still parsed correctly."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()

        text = """<TOOL_CALL name="execute_command" params='{"command":"ls -la","host":"main"}'>List files</TOOL_CALL>"""
        tool_calls = handler._parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "execute_command"
        assert tool_calls[0]["params"]["command"] == "ls -la"
        assert tool_calls[0]["params"]["host"] == "main"

    @pytest.mark.asyncio
    async def test_no_respond_tool_yields_break_loop_false(self):
        """Test that when no respond tool is used, break_loop=False."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        handler.terminal_tool = None

        # Empty tool calls (no respond tool)
        tool_calls = []

        final_tuple = None
        async for item in handler._process_tool_calls(
            tool_calls, "s1", "t1", "http://localhost:11434", "llama3"
        ):
            if isinstance(item, tuple) and len(item) == 2:
                final_tuple = item

        assert final_tuple is not None
        break_loop_requested, respond_content = final_tuple
        assert break_loop_requested is False
        assert respond_content is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
