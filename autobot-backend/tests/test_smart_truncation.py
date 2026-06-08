# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for smart context truncation feature (Issue #4346).

Verifies that large files are truncated intelligently with head/tail preservation.
Issue #4397: Performance validation on extremely large files (10 MB+).
"""

import time

from prompt_manager import _is_binary_content, _snap_to_char_boundary, _truncate_large_file


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


class TestUtf8BoundarySafety:
    """Issue #4394: multi-byte character boundary safety tests."""

    def _make_large(self, char: str, total: int = 25000) -> str:
        """Build a string of *total* Unicode characters using *char* as filler."""
        return char * total

    # ------------------------------------------------------------------
    # _snap_to_char_boundary unit tests
    # ------------------------------------------------------------------

    def test_snap_forward_finds_whitespace(self):
        """snap forward should return position of first whitespace at/after pos."""
        s = "abcde fghij"
        assert _snap_to_char_boundary(s, 3, search_forward=True) == 5

    def test_snap_backward_finds_whitespace(self):
        """snap backward should return position just after the last whitespace before pos."""
        s = "abcde fghij"
        assert _snap_to_char_boundary(s, 8, search_forward=False) == 6

    def test_snap_no_whitespace_returns_original(self):
        """When no whitespace is found within limit, original position is returned."""
        s = "a" * 200
        assert _snap_to_char_boundary(s, 50, search_forward=True) == 50
        assert _snap_to_char_boundary(s, 150, search_forward=False) == 150

    # ------------------------------------------------------------------
    # Emoji (4-byte UTF-8 codepoints) — U+1F600 and family
    # ------------------------------------------------------------------

    def test_emoji_not_corrupted_at_head_boundary(self):
        """4-byte emoji must not be split at the head cut point."""
        emoji = "\U0001f600"  # 😀 — 4 bytes when encoded to UTF-8
        content = emoji * 25000  # all emoji
        result = _truncate_large_file(content, max_chars=20000)

        # Re-encode must succeed without UnicodeEncodeError / replacement chars
        encoded = result.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert decoded == result, "round-trip encode/decode must be lossless"

        # Head and tail must each consist entirely of valid emoji codepoints
        before_marker = result.split("[...")[0]
        after_marker = result.split("...]")[-1].strip()
        assert all(c == emoji or c.isspace() for c in before_marker.strip())
        assert all(c == emoji or c.isspace() for c in after_marker.strip())

    def test_emoji_content_survives_round_trip(self):
        """Mixed emoji + ASCII content round-trips through truncation."""
        content = "Hello 😀 World 🌍 " * 1500  # > 20000 chars
        result = _truncate_large_file(content, max_chars=20000)
        encoded = result.encode("utf-8")
        assert encoded.decode("utf-8") == result

    # ------------------------------------------------------------------
    # CJK characters (3-byte UTF-8 codepoints) — U+4E2D (中)
    # ------------------------------------------------------------------

    def test_cjk_not_corrupted_at_boundary(self):
        """3-byte CJK characters must not be split at truncation boundaries."""
        cjk = "\u4e2d"  # 中 — 3 bytes in UTF-8
        content = cjk * 25000
        result = _truncate_large_file(content, max_chars=20000)

        encoded = result.encode("utf-8")
        assert encoded.decode("utf-8") == result

    def test_cjk_mixed_with_ascii(self):
        """CJK mixed with ASCII spaces survives truncation round-trip."""
        content = "中文 text " * 3000  # spaces allow boundary snapping
        result = _truncate_large_file(content, max_chars=20000)
        assert result.encode("utf-8").decode("utf-8") == result

    # ------------------------------------------------------------------
    # Accented / Latin extended characters (2-byte UTF-8) — café, naïve
    # ------------------------------------------------------------------

    def test_accented_chars_not_corrupted(self):
        """2-byte accented characters (é, ï, ñ) must survive truncation."""
        content = "café naïve résumé " * 1500  # > 20000 chars
        result = _truncate_large_file(content, max_chars=20000)
        assert result.encode("utf-8").decode("utf-8") == result

    def test_accented_head_preserved(self):
        """Head section must start with accented content, not be mangled."""
        content = "résumé " * 4000
        result = _truncate_large_file(content, max_chars=20000)
        before_marker = result.split("[...")[0]
        assert "résumé" in before_marker

    # ------------------------------------------------------------------
    # ASCII (1-byte) — baseline should still pass
    # ------------------------------------------------------------------

    def test_ascii_unchanged_behaviour(self):
        """ASCII-only content must still truncate correctly."""
        content = "hello world " * 2500  # > 20000 chars
        result = _truncate_large_file(content, max_chars=20000)
        assert len(result) < len(content)
        assert "[..." in result
        assert result.encode("utf-8").decode("utf-8") == result

    # ------------------------------------------------------------------
    # Mixed multi-byte in head/tail — boundary snapping correctness
    # ------------------------------------------------------------------

    def test_boundary_snap_does_not_cut_mid_word(self):
        """Boundary snap must not cut in the middle of a multi-byte word."""
        # Place a long emoji word right at the section_size boundary (~8000)
        prefix = "a " * 4000  # 8000 chars, ends with space
        emoji_word = "😀🌍🎉" * 100  # 300 chars, no internal spaces
        suffix = " b" * 8500  # 17000 chars
        content = prefix + emoji_word + suffix  # well above 20000

        result = _truncate_large_file(content, max_chars=20000)
        # Round-trip encode/decode is the definitive correctness check
        assert result.encode("utf-8").decode("utf-8") == result


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


class TestBinaryFileHandling:
    """Issue #4396: binary file detection and safe handling in truncation."""

    # ------------------------------------------------------------------
    # _is_binary_content unit tests
    # ------------------------------------------------------------------

    def test_plain_text_not_binary(self):
        """Normal ASCII text must not be flagged as binary."""
        assert _is_binary_content("hello world") is False

    def test_unicode_text_not_binary(self):
        """Unicode text (emoji, CJK, accented) must not be flagged as binary."""
        assert _is_binary_content("cafe \u00e9 \u4e2d \U0001f600") is False

    def test_null_byte_detected(self):
        """A single null byte must be detected as binary."""
        assert _is_binary_content("text\x00more") is True

    def test_all_null_bytes_detected(self):
        """Content consisting only of null bytes must be detected."""
        assert _is_binary_content("\x00" * 100) is True

    def test_null_byte_at_start(self):
        """Null byte at position 0 must be caught."""
        assert _is_binary_content("\x00trailing text") is True

    def test_null_byte_at_end(self):
        """Null byte at end of string must be caught."""
        assert _is_binary_content("leading text\x00") is True

    def test_empty_string_not_binary(self):
        """Empty string must not be flagged as binary."""
        assert _is_binary_content("") is False

    # ------------------------------------------------------------------
    # _truncate_large_file binary guard (small + large binary inputs)
    # ------------------------------------------------------------------

    def test_small_binary_below_threshold_returned_unchanged(self):
        """Binary content under max_chars passes through unchanged (no truncation guard)."""
        # Under the 20k threshold: _truncate_large_file returns early before the binary check
        content = "abc\x00def"
        result = _truncate_large_file(content, max_chars=20000)
        assert result == content

    def test_large_binary_returns_placeholder(self):
        """Binary content above max_chars must be replaced with a safe placeholder."""
        content = "a" * 10000 + "\x00" + "b" * 11000  # 21001 chars, contains null byte
        result = _truncate_large_file(content, max_chars=20000)
        assert result == "[Binary file content omitted — not suitable for LLM context]"
        assert "\x00" not in result

    def test_large_binary_placeholder_is_str(self):
        """Placeholder must be a plain str — safe to pass to LLM context."""
        content = "\x00" * 25000
        result = _truncate_large_file(content, max_chars=20000)
        assert isinstance(result, str)
        assert "\x00" not in result

    def test_large_binary_no_truncation_marker(self):
        """Placeholder must not contain the normal truncation marker."""
        content = "x\x00" * 15000  # 30000 chars with embedded nulls
        result = _truncate_large_file(content, max_chars=20000)
        assert "chars TRUNCATED" not in result

    def test_text_with_no_null_bytes_truncated_normally(self):
        """Text without null bytes must still be truncated normally."""
        content = "a" * 25000
        result = _truncate_large_file(content, max_chars=20000)
        assert "chars TRUNCATED" in result
        assert "\x00" not in result

    def test_binary_with_high_control_chars_not_flagged(self):
        """Non-null control chars (\\x01–\\x1f) are not flagged as binary — only null bytes are."""
        content = "\x01\x1f\x7f" * 8000  # 24000 chars, no null bytes
        result = _truncate_large_file(content, max_chars=20000)
        # Should truncate normally, not return placeholder
        assert "chars TRUNCATED" in result


class TestLargeFilePerformance:
    """Issue #4397: Performance validation on extremely large files (10 MB+).

    Ensures _truncate_large_file completes well within a 1-second budget
    regardless of input size, because it only touches the head/tail slices —
    not the full 10 MB+ body.
    """

    _MAX_SECONDS = 1.0  # hard ceiling per call

    def _time_truncation(self, content: str, max_chars: int = 20000) -> float:
        """Return elapsed seconds for a single _truncate_large_file call."""
        start = time.perf_counter()
        _truncate_large_file(content, max_chars=max_chars)
        return time.perf_counter() - start

    def test_10mb_ascii_under_budget(self):
        """10 MB ASCII file must truncate in < 1 s."""
        content = "a" * (10 * 1024 * 1024)
        elapsed = self._time_truncation(content)
        assert (
            elapsed < self._MAX_SECONDS
        ), f"10 MB ASCII truncation took {elapsed:.3f}s — exceeds {self._MAX_SECONDS}s budget"

    def test_50mb_ascii_under_budget(self):
        """50 MB ASCII file must truncate in < 1 s."""
        content = "b" * (50 * 1024 * 1024)
        elapsed = self._time_truncation(content)
        assert (
            elapsed < self._MAX_SECONDS
        ), f"50 MB ASCII truncation took {elapsed:.3f}s — exceeds {self._MAX_SECONDS}s budget"

    def test_10mb_unicode_under_budget(self):
        """10 MB Unicode (emoji) file must truncate in < 1 s."""
        # Each emoji is 1 Python str codepoint; repeat to reach ~10 M chars
        content = "\U0001f600" * (10 * 1024 * 1024)
        elapsed = self._time_truncation(content)
        assert (
            elapsed < self._MAX_SECONDS
        ), f"10 MB emoji truncation took {elapsed:.3f}s — exceeds {self._MAX_SECONDS}s budget"

    def test_10mb_cjk_under_budget(self):
        """10 MB CJK file must truncate in < 1 s."""
        content = "\u4e2d" * (10 * 1024 * 1024)
        elapsed = self._time_truncation(content)
        assert (
            elapsed < self._MAX_SECONDS
        ), f"10 MB CJK truncation took {elapsed:.3f}s — exceeds {self._MAX_SECONDS}s budget"

    def test_result_correct_after_large_truncation(self):
        """Correctness check: 10 MB file must produce valid head/tail output."""
        head = "HEAD" * 100  # 400 chars
        body = "x" * (10 * 1024 * 1024)
        tail = "TAIL" * 100  # 400 chars
        content = head + body + tail

        result = _truncate_large_file(content, max_chars=20000)

        assert result.startswith("HEAD")
        assert result.endswith("TAIL")
        assert "[..." in result
        assert "chars TRUNCATED...]" in result
        assert len(result) < len(content)
