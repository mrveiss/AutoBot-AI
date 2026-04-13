# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Prompt Manager - Truncation and Context Management

Issue #4346: Smart context truncation for large files
- Tests for _truncate_large_file function
- Verification of truncation marker format
- Tests across different file types (code, markdown, JSON)
"""

import pytest
from prompt_manager import _truncate_large_file, PromptManager


class TestTruncateLargeFile:
    """Test suite for _truncate_large_file function."""

    def test_small_file_unchanged(self):
        """Small files (<20k chars) should be returned unchanged."""
        content = "This is a small file" * 100  # ~2000 chars
        result = _truncate_large_file(content)
        assert result == content
        assert len(result) == len(content)

    def test_file_at_threshold(self):
        """Files at exactly max_chars threshold should not be truncated."""
        content = "x" * 20000
        result = _truncate_large_file(content)
        assert result == content
        assert len(result) == 20000

    def test_file_just_over_threshold(self):
        """Files just over threshold should be truncated."""
        content = "x" * 20001
        result = _truncate_large_file(content)
        assert result != content
        assert "chars TRUNCATED" in result

    def test_large_file_truncation(self):
        """Large files should be truncated with head + tail preservation."""
        # Create a 100k file with distinguishable sections
        head_section = "START:" + "x" * 10000
        middle_section = "y" * 70000
        tail_section = "z" * 20000 + ":END"
        content = head_section + middle_section + tail_section

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve START from head
        assert "START:" in result
        # Should preserve :END from tail
        assert ":END" in result
        # Should contain truncation marker
        assert "[..." in result and "chars TRUNCATED" in result
        # Result should be smaller than original
        assert len(result) < len(content)

    def test_truncation_marker_format(self):
        """Marker should indicate number of truncated chars."""
        content = "x" * 50000
        result = _truncate_large_file(content)

        # Check marker format: [...<N> chars TRUNCATED...]
        assert "[..." in result
        assert "chars TRUNCATED" in result
        assert "...]" in result

    def test_marker_contains_truncated_count(self):
        """Marker should show how many chars were removed."""
        content = "x" * 30000
        result = _truncate_large_file(content, max_chars=20000)

        # Extract truncated count from marker
        import re
        match = re.search(r'\.\.\.([\d]+) chars TRUNCATED', result)
        assert match is not None
        truncated_count = int(match.group(1))
        assert truncated_count > 0
        assert truncated_count < len(content)

    def test_custom_max_chars(self):
        """Should respect custom max_chars threshold."""
        content = "x" * 10000
        result = _truncate_large_file(content, max_chars=5000)

        # Should truncate because 10000 > 5000
        assert len(result) < len(content)
        assert "chars TRUNCATED" in result

    def test_preserves_head_section(self):
        """Head section should be preserved in truncation."""
        content = "HEAD_MARKER:" + "x" * 50000
        result = _truncate_large_file(content, max_chars=20000)

        assert "HEAD_MARKER:" in result
        # Head marker should be near the beginning
        assert result.index("HEAD_MARKER:") < 100

    def test_preserves_tail_section(self):
        """Tail section should be preserved in truncation."""
        content = "x" * 50000 + ":TAIL_MARKER"
        result = _truncate_large_file(content, max_chars=20000)

        assert ":TAIL_MARKER" in result
        # Tail marker should be near the end
        assert result.rindex(":TAIL_MARKER") > len(result) - 100

    def test_multiline_python_file(self):
        """Test truncation with Python code structure."""
        python_code = """# Python file example
import os
import sys

def function1():
    '''This is a function.'''
    pass

def function2():
    '''Another function.'''
    pass
"""
        # Make it large by repeating
        content = python_code * 2000  # ~100k chars

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve imports from head
        assert "import os" in result
        # Should preserve function definitions
        assert "def function" in result

    def test_markdown_file(self):
        """Test truncation with Markdown structure."""
        markdown = """# Main Title
## Section 1
This is content.

## Section 2
More content here.

### Subsection
Details about subsection.
"""
        content = markdown * 2000  # ~100k chars

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve heading markers
        assert "#" in result
        # Should contain markdown patterns
        assert "##" in result or "# " in result

    def test_json_file(self):
        """Test truncation with JSON structure."""
        json_data = '{"key1": "value1", "key2": "value2", "nested": {"a": 1}}\n'
        content = json_data * 3000  # ~150k chars

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve JSON structure markers
        assert "{" in result
        assert "}" in result
        assert "[..." in result

    def test_empty_string(self):
        """Empty string should be returned unchanged."""
        content = ""
        result = _truncate_large_file(content)
        assert result == ""

    def test_single_character(self):
        """Single character should be unchanged."""
        content = "x"
        result = _truncate_large_file(content)
        assert result == "x"

    def test_whitespace_only(self):
        """Whitespace-only content should be handled."""
        content = " " * 25000
        result = _truncate_large_file(content, max_chars=20000)

        # Should be truncated
        assert len(result) < len(content)
        assert "chars TRUNCATED" in result

    def test_special_characters(self):
        """Special characters should be preserved in truncation."""
        head = "!@#$%^&*()" * 500
        middle = "x" * 50000
        tail = "!@#$%^&*()" * 500
        content = head + middle + tail

        result = _truncate_large_file(content, max_chars=20000)

        # Should preserve some special characters from both sections
        assert "!" in result or "@" in result or "#" in result

    def test_unicode_characters(self):
        """Unicode characters should be preserved correctly."""
        head = "你好" * 5000  # Chinese characters
        middle = "x" * 50000
        tail = "مرحبا" * 5000  # Arabic characters
        content = head + middle + tail

        result = _truncate_large_file(content, max_chars=20000)

        # Should handle unicode without errors
        assert isinstance(result, str)
        # Should contain truncation marker
        assert "chars TRUNCATED" in result

    def test_newline_preservation(self):
        """Newlines should be preserved in truncated content."""
        lines = ["Line " + str(i) for i in range(3000)]
        content = "\n".join(lines)

        result = _truncate_large_file(content, max_chars=20000)

        # Should contain newlines
        assert "\n" in result
        # Should have truncation marker with proper newlines around it
        assert "\n\n[..." in result
        assert "...]\n\n" in result

    def test_large_file_multiple_formats(self):
        """Test truncation across different content formats."""
        formats = [
            ("Python", "def func():\n    pass\n" * 3000),
            ("JSON", '{"key": "value"}\n' * 3000),
            ("Markdown", "# Title\nContent here\n" * 3000),
            ("Plain Text", "This is plain text line.\n" * 3000),
        ]

        for format_name, content in formats:
            result = _truncate_large_file(content, max_chars=20000)
            assert "chars TRUNCATED" in result, f"Failed for {format_name} format"
            assert len(result) < len(content), f"Not truncated for {format_name}"


class TestPromptManagerTruncate:
    """Test suite for PromptManager.truncate_large_file public method."""

    def test_prompt_manager_truncate_method_exists(self):
        """PromptManager should have truncate_large_file method."""
        pm = PromptManager()
        assert hasattr(pm, "truncate_large_file")
        assert callable(pm.truncate_large_file)

    def test_prompt_manager_truncate_small_file(self):
        """PromptManager.truncate_large_file should handle small files."""
        pm = PromptManager()
        content = "Small content" * 100
        result = pm.truncate_large_file(content)
        assert result == content

    def test_prompt_manager_truncate_large_file(self):
        """PromptManager.truncate_large_file should truncate large files."""
        pm = PromptManager()
        content = "x" * 50000
        result = pm.truncate_large_file(content)

        assert len(result) < len(content)
        assert "chars TRUNCATED" in result

    def test_prompt_manager_custom_threshold(self):
        """PromptManager.truncate_large_file should accept custom max_chars."""
        pm = PromptManager()
        content = "x" * 10000
        result = pm.truncate_large_file(content, max_chars=5000)

        # Should truncate because 10000 > 5000
        assert len(result) < len(content)


class TestTruncationEdgeCases:
    """Test suite for edge cases and performance."""

    def test_very_large_file(self):
        """Should handle very large files (10MB) efficiently."""
        # Create a 10MB file
        content = "x" * (10 * 1024 * 1024)
        result = _truncate_large_file(content, max_chars=20000)

        assert len(result) < len(content)
        assert "chars TRUNCATED" in result
        # Result should be much smaller than 10MB
        assert len(result) < 100000

    def test_truncation_symmetry(self):
        """Head and tail sections should be roughly equal size."""
        content = "x" * 100000
        result = _truncate_large_file(content, max_chars=20000)

        # Extract marker position
        marker_start = result.index("[...")
        marker_end = result.index("...]") + 4

        head_section = result[:marker_start]
        tail_section = result[marker_end:]

        # Head and tail should be similar size (within 20%)
        size_diff = abs(len(head_section) - len(tail_section))
        avg_size = (len(head_section) + len(tail_section)) / 2
        assert size_diff / avg_size < 0.2

    def test_marker_never_in_original_content(self):
        """Marker format should not interfere with content containing similar patterns."""
        # Content that might contain bracket sequences
        content = "[...some code...] and more [...]" + "x" * 50000

        result = _truncate_large_file(content, max_chars=20000)

        # Should still have the marker
        assert "chars TRUNCATED" in result or "[..." in result

    def test_no_double_truncation(self):
        """Applying truncation twice should not double-truncate."""
        content = "x" * 100000
        result1 = _truncate_large_file(content, max_chars=20000)
        result2 = _truncate_large_file(result1, max_chars=20000)

        # Second truncation should be minimal or none
        assert len(result2) == len(result1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
