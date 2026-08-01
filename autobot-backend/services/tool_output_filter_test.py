# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the ToolOutputFilter hard-size cap (#11543).

No tool output may enter conversation history above the hard ceiling
(``_MAX_UNMATCHED_OUTPUT_CHARS``), regardless of whether a filter rule matched.
Oversized output is head/tail-truncated with a pointer to the teed full copy.
"""

from __future__ import annotations

from services import tool_output_filter as tof
from services.tool_output_filter import ToolOutputFilter, cap_unmatched_output

_LIMIT = tof._MAX_UNMATCHED_OUTPUT_CHARS


def _huge(n_chars: int) -> str:
    # Distinct-ish content so the cap can't be mistaken for dedup.
    return "\n".join(f"line {i} " + "x" * 40 for i in range(n_chars // 48))


class TestHardSizeCap:
    def test_unmatched_multi_mb_output_is_capped(self, tmp_path, monkeypatch):
        """AC: an unmatched command's multi-MB output is capped below the ceiling
        with a truncation marker and a pointer to the teed full output."""
        monkeypatch.setattr(tof, "_TEE_DIR", tmp_path)
        f = ToolOutputFilter()
        big = _huge(3_000_000)  # ~3 MB, matches no rule
        assert len(big) > _LIMIT

        result = f.filter("some_unknown_command --flag", big, exit_code=0)

        assert len(result) < _LIMIT + 500, "result must be bounded by the ceiling"
        assert "chars omitted" in result
        assert "full output saved" in result, "must point at the teed full copy"
        # The full copy was actually written to the tee dir.
        assert any(p.suffix == ".txt" for p in tmp_path.iterdir())

    def test_matched_rule_output_above_cap_is_also_capped(self, tmp_path, monkeypatch):
        """AC: cap applies *regardless of rule match* — a matched but near-passthrough
        rule that leaves output above the ceiling is still hard-capped."""
        monkeypatch.setattr(tof, "_TEE_DIR", tmp_path)
        f = ToolOutputFilter()
        # Inject a matching rule that only strips ANSI (passthrough for clean text).
        f._rules = [{"match_command": "^bigcmd", "strip_ansi": True}]
        big = _huge(3_000_000)

        result = f.filter("bigcmd run", big, exit_code=0)

        assert len(result) < _LIMIT + 500, "matched-rule output above cap must be capped too"
        assert "chars omitted" in result

    def test_output_below_cap_is_unchanged(self):
        """Existing behavior: unmatched output below the ceiling passes through as-is."""
        f = ToolOutputFilter()
        small = "just a little output\nnothing special"
        assert f.filter("some_unknown_command", small, exit_code=0) == small

    def test_cap_unmatched_output_function(self, tmp_path, monkeypatch):
        """Direct unit: cap_unmatched_output truncates and keeps head+tail."""
        monkeypatch.setattr(tof, "_TEE_DIR", tmp_path)
        big = "HEAD_MARKER\n" + _huge(_LIMIT * 3) + "\nTAIL_MARKER"

        capped = cap_unmatched_output("weird_cmd", big, 0)

        assert len(capped) < _LIMIT + 500
        assert capped.startswith("HEAD_MARKER")
        assert "TAIL_MARKER" in capped
        assert "chars omitted" in capped

    def test_cap_unmatched_output_noop_below_limit(self):
        """Below the ceiling, cap_unmatched_output returns the output unchanged."""
        small = "tiny"
        assert cap_unmatched_output("weird_cmd", small, 0) == small
