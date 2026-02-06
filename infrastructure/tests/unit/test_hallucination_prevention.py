# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #727 - LLM Hallucination Prevention.

Tests verify:
1. Tool call completion regex detects </tool_call> tags correctly
2. Both uppercase and lowercase tags are detected
3. Tags with whitespace variations are handled
"""

import pytest


class TestToolCallCompletionRegex:
    """Test the _TOOL_CALL_COMPLETE_RE regex pattern."""

    @pytest.fixture
    def pattern(self):
        """Get the compiled regex pattern."""
        from src.chat_workflow.manager import _TOOL_CALL_COMPLETE_RE

        return _TOOL_CALL_COMPLETE_RE

    def test_lowercase_tag(self, pattern):
        """Test detection of lowercase </tool_call> tag."""
        text = (
            '<tool_call name="execute_command" params=\'{"command":"ls"}\'></tool_call>'
        )
        assert pattern.search(text) is not None

    def test_uppercase_tag(self, pattern):
        """Test detection of uppercase </TOOL_CALL> tag."""
        text = (
            '<TOOL_CALL name="execute_command" params=\'{"command":"ls"}\'></TOOL_CALL>'
        )
        assert pattern.search(text) is not None

    def test_mixed_case_tag(self, pattern):
        """Test detection of mixed case </Tool_Call> tag."""
        text = "<Tool_Call name=\"test\" params='{}'></Tool_Call>"
        assert pattern.search(text) is not None

    def test_tag_with_internal_whitespace(self, pattern):
        """Test detection of tag with whitespace variations."""
        text = "<tool_call name=\"test\" params='{}'></ tool_call >"
        assert pattern.search(text) is not None

    def test_underscore_variant_tag(self, pattern):
        """Test detection of underscore variant </TOOL_ CALL> tag.

        Some LLMs generate TOOL_CALL with space before CALL which is
        normalized by _TOOL_CALL_CLOSE_RE. Ensure hallucination prevention
        also handles this variant.
        """
        text = "<TOOL_ CALL name=\"test\" params='{}'></TOOL_ CALL>"
        assert pattern.search(text) is not None

    def test_no_false_positive_on_open_tag(self, pattern):
        """Ensure open <tool_call> tags don't match."""
        text = '<tool_call name="execute_command" params=\'{"command":"ls"}\'>'
        assert pattern.search(text) is None

    def test_partial_response_no_match(self, pattern):
        """Test that incomplete tags don't match."""
        text = "<tool_call name=\"test\" params='{}'>description"
        assert pattern.search(text) is None

    def test_hallucination_scenario(self, pattern):
        """Test the actual hallucination scenario from issue #727."""
        # Simulates what a smaller model might generate
        text = """I'll scan your network for devices.

<tool_call name="execute_command" params='{"command":"nmap -sn 192.168.1.0/24"}'>Scan network</tool_call>

Here are the devices I found:
1. 192.168.1.1 (Gateway)
2. 192.168.1.100 (This device)
3. 192.168.1.105
4. 192.168.1.110

**Current user message:** yes, please keep monitoring my network"""

        # The pattern should find the closing tag
        match = pattern.search(text)
        assert match is not None

        # Verify we can use the match position to truncate hallucinations
        end_of_tool_call = match.end()
        content_before = text[:end_of_tool_call]
        hallucinated_content = text[end_of_tool_call:]

        # Hallucinated content should contain the fake results
        assert "192.168.1.1" in hallucinated_content
        assert "Current user message" in hallucinated_content

        # Content before should have the valid tool call
        assert "nmap" in content_before
        assert "</tool_call>" in content_before


class TestHallucinationPreventionLogic:
    """Test the streaming interruption logic for hallucination prevention."""

    def test_detect_tool_call_completion_in_stream(self):
        """Simulate chunk-by-chunk tool call detection."""
        from src.chat_workflow.manager import _TOOL_CALL_COMPLETE_RE

        # Simulate streaming chunks
        chunks = [
            "I'll scan ",
            "your network.\n\n<tool_call ",
            'name="execute_command" ',
            'params=\'{"command":"nmap"}\'>',
            "Scanning</tool_call>",  # This chunk completes the tag
            "\n\nHere are fake results:",  # Hallucination starts
            "\n1. 192.168.1.1",
        ]

        accumulated = ""
        tool_call_detected_at_chunk = None

        for i, chunk in enumerate(chunks):
            accumulated += chunk
            if _TOOL_CALL_COMPLETE_RE.search(accumulated):
                tool_call_detected_at_chunk = i
                break

        # Should detect at chunk index 4 (the one with </tool_call>)
        assert tool_call_detected_at_chunk == 4

        # The accumulated content at detection should NOT include hallucinations
        assert "fake results" not in accumulated
        assert "192.168.1.1" not in accumulated
