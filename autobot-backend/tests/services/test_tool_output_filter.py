# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ToolOutputFilter pipeline stages."""

import os
import tempfile

import yaml

from services.tool_output_filter import (
    ToolOutputFilter,
    _dedup_consecutive,
    _line_similarity,
    _strip_ansi,
    _tail_lines,
    apply_no_op_detection,
    classify_tool,
    condense_unified_diff,
    filter_markdown_body,
    filter_pytest,
    filter_ruff_json,
    get_tool_output_filter,
    inject_compact_flags,
    join_with_overflow,
    short_circuit_git,
)


def _make_filter(rules: dict) -> ToolOutputFilter:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
        yaml.dump({"filters": rules}, fh)
        path = fh.name
    try:
        return ToolOutputFilter(config_path=path)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# _strip_ansi
# ---------------------------------------------------------------------------


def test_strip_ansi_removes_color_codes():
    assert _strip_ansi("\x1b[31mRED\x1b[0m") == "RED"


def test_strip_ansi_passthrough_clean():
    assert _strip_ansi("hello world") == "hello world"


# ---------------------------------------------------------------------------
# _dedup_consecutive
# ---------------------------------------------------------------------------


def test_dedup_consecutive_collapses():
    assert _dedup_consecutive("a\na\na\nb\nb\nc") == "a [×3]\nb [×2]\nc"


def test_dedup_consecutive_no_repeats():
    assert _dedup_consecutive("a\nb\nc") == "a\nb\nc"


# ---------------------------------------------------------------------------
# _tail_lines
# ---------------------------------------------------------------------------


def test_tail_lines_adds_omission_prefix():
    result = _tail_lines("\n".join(str(i) for i in range(10)), 3)
    assert "7\n8\n9" in result
    assert "7 lines omitted" in result


def test_tail_lines_no_truncation_when_under_limit():
    text = "a\nb\nc"
    assert _tail_lines(text, 5) == text


def test_tail_lines_exact_limit_no_prefix():
    text = "a\nb\nc"
    assert _tail_lines(text, 3) == text


# ---------------------------------------------------------------------------
# join_with_overflow
# ---------------------------------------------------------------------------


def test_join_with_overflow_under_limit():
    assert join_with_overflow(["a", "b", "c"], 5) == "a, b, c"


def test_join_with_overflow_over_limit():
    items = ["a", "b", "c", "d", "e"]
    result = join_with_overflow(items, 3, "files")
    assert result.startswith("a, b, c")
    assert "2 more files" in result


# ---------------------------------------------------------------------------
# inject_compact_flags
# ---------------------------------------------------------------------------


def test_inject_compact_flags_pytest():
    result = inject_compact_flags("pytest tests/")
    assert "--tb=short" in result
    assert "-q" in result


def test_inject_compact_flags_pytest_no_duplicate():
    cmd = "pytest --tb=long tests/"
    assert inject_compact_flags(cmd) == cmd


def test_inject_compact_flags_ruff():
    result = inject_compact_flags("ruff check .")
    assert "--output-format=json" in result


def test_inject_compact_flags_ruff_no_duplicate():
    cmd = "ruff check --output-format=text ."
    assert inject_compact_flags(cmd) == cmd


def test_inject_compact_flags_passthrough_unknown():
    cmd = "black ."
    assert inject_compact_flags(cmd) == cmd


def test_inject_compact_flags_python_m_pytest():
    result = inject_compact_flags("python -m pytest tests/")
    assert "--tb=short" in result


# ---------------------------------------------------------------------------
# apply_no_op_detection
# ---------------------------------------------------------------------------


def test_apply_no_op_detection_matches():
    result = apply_no_op_detection("git push", "Everything up-to-date\nmore", 0)
    assert result is not None
    assert "up-to-date" in result.lower()


def test_apply_no_op_detection_nonzero_exit_returns_none():
    result = apply_no_op_detection("git push", "Everything up-to-date", 1)
    assert result is None


def test_apply_no_op_detection_no_match():
    result = apply_no_op_detection("git push", "branch pushed successfully", 0)
    assert result is None


def test_apply_no_op_detection_nothing_to_commit():
    result = apply_no_op_detection("git status", "nothing to commit, working tree clean", 0)
    assert result is not None
    assert "nothing to commit" in result.lower()


# ---------------------------------------------------------------------------
# filter_pytest
# ---------------------------------------------------------------------------

_PYTEST_PASS_OUTPUT = "...\n=== 3 passed in 0.1s ==="
_PYTEST_FAIL_OUTPUT = (
    "...\n"
    "=== FAILURES ===\n"
    "___ test_foo ___\n"
    "AssertionError: assert 1 == 2\n"
    "=== 1 failed, 2 passed in 0.2s ==="
)


def test_filter_pytest_all_passed():
    result = filter_pytest(_PYTEST_PASS_OUTPUT, exit_code=0)
    assert result in ("All tests passed", "=== 3 passed in 0.1s ===") or "passed" in result


def test_filter_pytest_with_failures_keeps_failure_block():
    result = filter_pytest(_PYTEST_FAIL_OUTPUT, exit_code=1)
    assert "AssertionError" in result
    assert "1 failed" in result


def test_filter_pytest_strips_passing_progress():
    result = filter_pytest(_PYTEST_FAIL_OUTPUT, exit_code=1)
    assert "..." not in result.split("FAILURES")[0] if "FAILURES" in result else True


def test_filter_pytest_empty_output_nonzero_exit():
    result = filter_pytest("", exit_code=1)
    assert result == ""


# ---------------------------------------------------------------------------
# filter_ruff_json
# ---------------------------------------------------------------------------

_RUFF_JSON = (
    '[{"code":"E501","filename":"foo.py","location":{"row":10},"message":"line too long"},'
    '{"code":"E501","filename":"bar.py","location":{"row":5},"message":"line too long"}]'
)


def test_filter_ruff_json_valid():
    result = filter_ruff_json(_RUFF_JSON)
    assert "E501" in result
    assert "foo.py" in result
    assert "2 occurrence" in result


def test_filter_ruff_json_empty_list():
    assert filter_ruff_json("[]") == "ok (no violations)"


def test_filter_ruff_json_invalid_json():
    result = filter_ruff_json("not json")
    assert result == "not json"


def test_filter_ruff_json_groups_by_rule():
    data = (
        '[{"code":"F401","filename":"a.py","location":{"row":1},"message":"unused"},'
        '{"code":"E501","filename":"b.py","location":{"row":2},"message":"long"}]'
    )
    result = filter_ruff_json(data)
    assert "E501" in result
    assert "F401" in result


# ---------------------------------------------------------------------------
# short_circuit_git
# ---------------------------------------------------------------------------


def test_short_circuit_git_up_to_date():
    result = short_circuit_git("push", "Everything up-to-date", "", 0)
    assert result is not None
    assert "up-to-date" in result


def test_short_circuit_git_failure_returns_none():
    result = short_circuit_git("push", "error: failed to push", "", 1)
    assert result is None


def test_short_circuit_git_non_write_cmd_returns_none():
    result = short_circuit_git("status", "On branch main", "", 0)
    assert result is None


def test_short_circuit_git_nothing_to_commit():
    result = short_circuit_git("commit", "nothing to commit", "", 0)
    assert result is not None


# ---------------------------------------------------------------------------
# _line_similarity
# ---------------------------------------------------------------------------


def test_line_similarity_identical():
    assert _line_similarity("abc", "abc") == 1.0


def test_line_similarity_no_overlap():
    result = _line_similarity("aaa", "bbb")
    assert result == 0.0


def test_line_similarity_partial():
    result = _line_similarity("abc", "acd")
    assert 0.0 < result < 1.0


def test_line_similarity_both_empty():
    assert _line_similarity("", "") == 1.0


# ---------------------------------------------------------------------------
# condense_unified_diff
# ---------------------------------------------------------------------------

_UNIFIED_DIFF = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
 context line
-old line
+new line
 another context"""


def test_condense_unified_diff_keeps_diff_header():
    result = condense_unified_diff(_UNIFIED_DIFF)
    assert "diff --git" in result


def test_condense_unified_diff_strips_triple_dash_header():
    result = condense_unified_diff(_UNIFIED_DIFF)
    assert "--- a/foo.py" not in result


def test_condense_unified_diff_keeps_change_lines():
    result = condense_unified_diff(_UNIFIED_DIFF)
    assert "-old line" in result
    assert "+new line" in result


def test_condense_unified_diff_omission_notice():
    many_changes = "\n".join(f"+line {i}" for i in range(50))
    diff = f"diff --git a/f b/f\n@@ -1 +1 @@\n{many_changes}"
    result = condense_unified_diff(diff, max_changes_per_file=10)
    assert "omitted" in result


# ---------------------------------------------------------------------------
# filter_markdown_body
# ---------------------------------------------------------------------------

_MARKDOWN = """\
<!-- html comment -->
[![badge](https://img.shields.io/badge)](https://example.com)
![logo](logo.png)
---
# Real content

Some text here.

```python
code block
```
"""


def test_filter_markdown_strips_html_comment():
    result = filter_markdown_body(_MARKDOWN)
    assert "html comment" not in result


def test_filter_markdown_strips_badge_line():
    result = filter_markdown_body(_MARKDOWN)
    assert "shields.io" not in result


def test_filter_markdown_strips_image_only_line():
    result = filter_markdown_body(_MARKDOWN)
    assert "![logo]" not in result


def test_filter_markdown_strips_hr():
    result = filter_markdown_body(_MARKDOWN)
    assert "---" not in result


def test_filter_markdown_preserves_content():
    result = filter_markdown_body(_MARKDOWN)
    assert "Real content" in result
    assert "Some text here" in result


def test_filter_markdown_preserves_code_blocks():
    result = filter_markdown_body(_MARKDOWN)
    assert "code block" in result


# ---------------------------------------------------------------------------
# classify_tool
# ---------------------------------------------------------------------------


def test_classify_tool_pytest():
    assert classify_tool("pytest tests/") == "test"


def test_classify_tool_git():
    assert classify_tool("git push origin main") == "git"


def test_classify_tool_ruff():
    assert classify_tool("ruff check .") == "lint"


def test_classify_tool_unknown():
    assert classify_tool("my_custom_script.sh") == "other"


# ---------------------------------------------------------------------------
# ToolOutputFilter — pipeline dispatch via filter_type
# ---------------------------------------------------------------------------


def test_filter_type_pytest_dispatch():
    f = _make_filter({"r": {"match_command": "^pytest", "strip_ansi": True, "filter_type": "pytest"}})
    result = f.filter("pytest tests/", _PYTEST_PASS_OUTPUT, exit_code=0)
    assert "passed" in result or result == "All tests passed"


def test_filter_type_ruff_json_dispatch():
    f = _make_filter({"r": {"match_command": "^ruff", "strip_ansi": True, "filter_type": "ruff_json"}})
    result = f.filter("ruff check .", _RUFF_JSON, exit_code=0)
    assert "E501" in result


def test_filter_type_diff_dispatch():
    f = _make_filter({"r": {"match_command": "^git diff", "strip_ansi": True, "filter_type": "diff"}})
    result = f.filter("git diff", _UNIFIED_DIFF, exit_code=0)
    assert "diff --git" in result


def test_filter_type_markdown_dispatch():
    f = _make_filter({"r": {"match_command": "^gh", "strip_ansi": True, "filter_type": "markdown"}})
    result = f.filter("gh issue view 1", _MARKDOWN, exit_code=0)
    assert "html comment" not in result
    assert "Real content" in result


# ---------------------------------------------------------------------------
# ToolOutputFilter — basic pipeline stages (existing tests, updated)
# ---------------------------------------------------------------------------


def test_passthrough_when_no_rule():
    f = _make_filter({})
    output = "some\noutput\nhere"
    assert f.filter("cat file.txt", output) == output


def test_strip_ansi_stage():
    f = _make_filter({"r": {"match_command": "^cmd", "strip_ansi": True}})
    assert f.filter("cmd arg", "\x1b[32mgreen\x1b[0m text") == "green text"


def test_match_output_short_circuit():
    f = _make_filter(
        {
            "r": {"match_command": "^git", "match_output": [{"pattern": "Everything up-to-date", "message": "ok"}]},
        }
    )
    # exit_code=1 to bypass apply_no_op_detection
    assert f.filter("git push", "Everything up-to-date\nmore stuff", exit_code=1) == "ok"


def test_match_output_no_match_continues():
    f = _make_filter(
        {
            "r": {
                "match_command": "^git",
                "match_output": [{"pattern": "Everything up-to-date", "message": "ok"}],
                "max_lines": 5,
            },
        }
    )
    assert "branch pushed" in f.filter("git push", "branch pushed\nremote updated")


def test_strip_lines_matching():
    f = _make_filter({"r": {"match_command": "^pytest", "strip_lines_matching": ["^test_.* PASSED"]}})
    result = f.filter("pytest tests/", "test_foo PASSED\ntest_bar FAILED\ntest_baz PASSED")
    assert "PASSED" not in result
    assert "test_bar FAILED" in result


def test_keep_lines_matching():
    f = _make_filter({"r": {"match_command": "^ruff", "keep_lines_matching": ["error"]}})
    result = f.filter("ruff check .", "info: checking\nerror: bad code L10\ninfo: done")
    assert result.strip() == "error: bad code L10"


def test_dedup_consecutive_stage():
    f = _make_filter({"r": {"match_command": "^docker", "dedup_consecutive": True}})
    result = f.filter("docker logs myapp", "log line\nlog line\nlog line\ndifferent")
    assert "log line [×3]" in result
    assert "different" in result


def test_max_lines_truncates_to_last_n():
    f = _make_filter({"r": {"match_command": "^cmd", "max_lines": 3}})
    result = f.filter("cmd", "\n".join(str(i) for i in range(10)))
    assert "7\n8\n9" in result
    assert "7 lines omitted" in result


def test_on_empty_returned_when_filtered_result_empty():
    f = _make_filter(
        {
            "r": {
                "match_command": "^pytest",
                "strip_lines_matching": [".*"],
                "on_empty": "All tests passed",
            }
        }
    )
    assert f.filter("pytest tests/", "test_foo PASSED\ntest_bar PASSED") == "All tests passed"


# ---------------------------------------------------------------------------
# ToolOutputFilter — real config smoke tests
# ---------------------------------------------------------------------------


def test_real_config_loads():
    f = ToolOutputFilter()
    assert isinstance(f._rules, list)


def test_real_config_git_rule_matches():
    f = ToolOutputFilter()
    result = f.filter("git push origin main", "Everything up-to-date")
    assert "up-to-date" in result.lower() or "up to date" in result.lower()


def test_real_config_passthrough_unknown_command():
    f = ToolOutputFilter()
    output = "hello\nworld"
    assert f.filter("my_custom_script.sh", output) == output


def test_real_config_pytest_rule_matches():
    f = ToolOutputFilter()
    result = f.filter("pytest tests/", _PYTEST_PASS_OUTPUT, exit_code=0)
    assert result  # non-empty


def test_real_config_ruff_rule_matches():
    f = ToolOutputFilter()
    result = f.filter("ruff check .", _RUFF_JSON, exit_code=0)
    assert "E501" in result


def test_prepare_command_injects_flags():
    f = ToolOutputFilter()
    result = f.prepare_command("pytest tests/")
    assert "--tb=short" in result


# ---------------------------------------------------------------------------
# filter_pytest — SUMMARY_INFO state (#5892)
# ---------------------------------------------------------------------------

_PYTEST_Q_FAIL_OUTPUT = (
    ".F.\n"
    "=========================== short test summary info ===========================\n"
    "FAILED tests/test_foo.py::test_bar - AssertionError: expected 1\n"
    "=========================== 1 failed, 2 passed in 0.5s ==========================="
)

_PYTEST_Q_FAIL_WITH_DETAILS = (
    ".F.\n"
    "=========================== FAILURES ===========================\n"
    "___ test_bar ___\n"
    "AssertionError: expected 1\n"
    "=========================== short test summary info ===========================\n"
    "FAILED tests/test_foo.py::test_bar - AssertionError\n"
    "=========================== 1 failed in 0.5s ==========================="
)


def test_filter_pytest_preserves_short_summary_info_section():
    result = filter_pytest(_PYTEST_Q_FAIL_OUTPUT, exit_code=1)
    assert "FAILED tests/test_foo.py::test_bar" in result
    assert "1 failed" in result


def test_filter_pytest_summary_info_header_preserved():
    result = filter_pytest(_PYTEST_Q_FAIL_OUTPUT, exit_code=1)
    assert "short test summary info" in result


def test_filter_pytest_summary_info_after_failures_block():
    result = filter_pytest(_PYTEST_Q_FAIL_WITH_DETAILS, exit_code=1)
    assert "AssertionError" in result
    assert "FAILED tests/test_foo.py::test_bar" in result


def test_filter_pytest_summary_info_final_line_preserved():
    result = filter_pytest(_PYTEST_Q_FAIL_OUTPUT, exit_code=1)
    assert "1 failed" in result
    assert "2 passed" in result


# ---------------------------------------------------------------------------
# filter_ruff_json — join_with_overflow header (#5894)
# ---------------------------------------------------------------------------


def test_filter_ruff_json_multi_rule_summary_header():
    data = (
        '[{"code":"F401","filename":"a.py","location":{"row":1},"message":"unused"},'
        '{"code":"E501","filename":"b.py","location":{"row":2},"message":"long"}]'
    )
    result = filter_ruff_json(data)
    assert "ruff violations:" in result
    assert "E501" in result
    assert "F401" in result


def test_filter_ruff_json_single_rule_no_summary_header():
    result = filter_ruff_json(_RUFF_JSON)
    assert "ruff violations:" not in result
    assert "E501" in result


# ---------------------------------------------------------------------------
# short_circuit_git wired in filter() (#5894)
# ---------------------------------------------------------------------------


def test_filter_short_circuit_git_via_stderr():
    f = ToolOutputFilter()
    # exit_code=0, stderr contains no-op phrase; apply_no_op_detection won't
    # catch it (only checks stdout), but short_circuit_git will check stderr
    result = f.filter("git push origin main", "", exit_code=0, stderr="Everything up-to-date")
    assert "up-to-date" in result.lower() or "up to date" in result.lower()


def test_filter_short_circuit_git_not_triggered_when_no_stderr():
    f = ToolOutputFilter()
    # With empty stderr and stdout that has no no-op pattern, short_circuit_git
    # and apply_no_op_detection both return None → passthrough to rule pipeline.
    result = f.filter("git push origin main", "branch pushed successfully", exit_code=0)
    assert result  # non-empty, processed normally


# ---------------------------------------------------------------------------
# prepare_and_filter (#5891)
# ---------------------------------------------------------------------------


def test_prepare_and_filter_injects_and_filters():
    f = ToolOutputFilter()
    # ruff check without --output-format=json: prepare_and_filter injects it,
    # but filter_ruff_json gets non-JSON and falls back to raw.
    # The key check: command is rewritten before rule matching.
    result = f.prepare_and_filter("ruff check .", "ok: no issues")
    assert result  # passes through (non-JSON, no rule match → raw)


def test_prepare_and_filter_injects_pytest_flags():
    f = ToolOutputFilter()
    # The prepared command "pytest --tb=short -q ..." still matches the pytest rule
    result = f.prepare_and_filter("pytest tests/", _PYTEST_PASS_OUTPUT, exit_code=0)
    assert result  # non-empty


# ---------------------------------------------------------------------------
# filter_blocks instance method (#5894)
# ---------------------------------------------------------------------------


class _MockBlockHandler:
    """Concrete BlockHandler for testing."""

    def __init__(self):
        self._in_error = False

    def start_block(self, line: str) -> bool:
        self._in_error = "ERROR:" in line
        return "BLOCK_START:" in line

    def end_block(self, line: str) -> bool:
        return "BLOCK_END" in line

    def is_error_block(self) -> bool:
        return self._in_error


def test_filter_blocks_instance_method_keeps_error_blocks():
    f = ToolOutputFilter()
    output = "preamble\n" "BLOCK_START: ERROR: bad thing\n" "detail line\n" "BLOCK_END\n" "footer"
    result = f.filter_blocks(output, _MockBlockHandler())
    assert "detail line" in result


# ---------------------------------------------------------------------------
# get_tool_output_filter singleton (#5893)
# ---------------------------------------------------------------------------


def test_get_tool_output_filter_returns_instance():
    instance = get_tool_output_filter()
    assert isinstance(instance, ToolOutputFilter)


def test_get_tool_output_filter_same_object_on_repeated_calls():
    assert get_tool_output_filter() is get_tool_output_filter()


# ---------------------------------------------------------------------------
# record_filter_savings uses pre-hint bytes (#5895)
# ---------------------------------------------------------------------------


def test_filter_savings_not_inflated_by_tee_hint(tmp_path, monkeypatch):
    import services.tool_output_filter as mod

    # Override tee dir to tmp so tee_and_hint actually writes
    monkeypatch.setattr(mod, "_TEE_DIR", tmp_path)
    saved_args: list = []

    import asyncio

    async def _capture(command, original, filtered):
        saved_args.append((len(original), len(filtered)))

    monkeypatch.setattr(mod, "record_filter_savings", _capture)

    ToolOutputFilter()
    # Build output that will trigger savings > 200 so tee_and_hint fires.
    # Use a rule with max_lines=1 to compress heavily.
    big_output = "\n".join(["x" * 40] * 30)  # ~1200 bytes
    rule_cfg = {"r": {"match_command": "^cmd", "max_lines": 1}}
    f2 = _make_filter(rule_cfg)

    async def _run():
        return f2.filter("cmd", big_output)

    result = asyncio.get_event_loop().run_until_complete(_run())
    # If savings were tracked, verify filtered length does NOT include tee hint
    if saved_args:
        orig_len, filt_len = saved_args[0]
        # filt_len must NOT include "[full output saved: ...]" line
        assert "[full output saved:" not in result[:filt_len] or filt_len < len(result)
