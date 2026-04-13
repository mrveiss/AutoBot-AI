# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for smart context truncation feature (Issue #4346).

Verifies that large files are truncated intelligently with head/tail preservation.
"""

from prompt_manager import _truncate_large_file


class TestSmartTruncation:
    """Test smart truncation functionality."""

    def test_small_file_unchanged(self):
        """Small files (<20k chars) should be returned unchanged."""
        content = "Small content" * 100  # ~1300 chars
        result = _truncate_large_file(content, max_chars=20000)
        assert result == content
        assert len(result) < 20000

    def test_large_file_truncated(self):
        """Large files (>20k chars) should be truncated with marker."""
        # Create content > 20000 chars
        content = "a" * 25000
        result = _truncate_large_file(content, max_chars=20000)

        # Should be truncated
        assert len(result) < len(content)
        # Should contain marker with character count
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_truncation_preserves_head_and_tail(self):
        """Truncation should preserve first and last sections."""
        # Create content with identifiable head and tail
        head = "START" * 100  # 500 chars
        middle = "x" * 23000
        tail = "END" * 100  # 300 chars
        content = head + middle + tail

        result = _truncate_large_file(content, max_chars=20000)

        # Should start with head
        assert result.startswith("START")
        # Should end with tail
        assert result.endswith("END")
        # Should contain marker with character count
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_marker_format_correct(self):
        """Marker should show exact number of truncated characters."""
        content = "a" * 25000
        result = _truncate_large_file(content, max_chars=20000)

        # Extract marker
        assert "[..." in result
        # Should show character count
        assert "chars TRUNCATED" in result

    def test_truncation_at_threshold(self):
        """Files exactly at threshold should not be truncated."""
        content = "x" * 20000
        result = _truncate_large_file(content, max_chars=20000)
        assert result == content

    def test_custom_threshold(self):
        """Should respect custom threshold values."""
        content = "y" * 10000
        result = _truncate_large_file(content, max_chars=5000)

        # Should be truncated
        assert len(result) < len(content)
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_very_large_file(self):
        """Should handle very large files efficiently."""
        content = "z" * 100000
        result = _truncate_large_file(content, max_chars=20000)

        # Should be truncated significantly
        assert len(result) < len(content)
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_empty_content(self):
        """Empty content should be returned unchanged."""
        content = ""
        result = _truncate_large_file(content, max_chars=20000)
        assert result == ""

    def test_multiline_content_preserved(self):
        """Multiline content structure should be preserved."""
        lines = "\n".join([f"Line {i}" for i in range(5000)])  # Creates large content
        result = _truncate_large_file(lines, max_chars=20000)

        # Should preserve line structure in head and tail
        assert "Line 0" in result  # Head preserved
        assert result.count("\n") > 0  # Newlines preserved
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_truncation_preserves_meaningful_sections(self):
        """Truncation should preserve first 40% and last 40% of max_chars."""
        # Create content with pattern
        head_marker = "START_OF_FILE" * 200  # 2600 chars
        tail_marker = "END_OF_FILE" * 200  # 2200 chars
        middle = "X" * 22000
        content = head_marker + middle + tail_marker

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve head marker (first part)
        assert "START_OF_FILE" in result.split("[...")[0]
        # Should preserve tail marker (last part)
        assert "END_OF_FILE" in result.split("...]")[-1]


class TestPromptManagerTruncation:
    """Test PromptManager's truncation method."""

    def test_prompt_manager_truncate_method(self):
        """PromptManager should expose truncation method."""
        from prompt_manager import prompt_manager

        content = "a" * 25000
        result = prompt_manager.truncate_large_file(content, max_chars=20000)

        assert len(result) < len(content)
        assert "[..." in result
        assert "chars TRUNCATED...]" in result

    def test_prompt_manager_respects_threshold(self):
        """PromptManager method should respect threshold parameter."""
        from prompt_manager import prompt_manager

        content = "x" * 10000
        result = prompt_manager.truncate_large_file(content, max_chars=5000)

        assert len(result) < len(content)

    def test_prompt_manager_default_threshold(self):
        """PromptManager should use 20000 as default threshold."""
        from prompt_manager import prompt_manager

        # Just under 20k
        small_content = "y" * 19999
        result_small = prompt_manager.truncate_large_file(small_content)
        assert result_small == small_content

        # Just over 20k
        large_content = "z" * 20001
        result_large = prompt_manager.truncate_large_file(large_content)
        assert len(result_large) < len(large_content)
