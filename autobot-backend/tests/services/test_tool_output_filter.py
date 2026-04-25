# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ToolOutputFilter pipeline stages."""
import os
import tempfile

import yaml

from services.tool_output_filter import ToolOutputFilter, _strip_ansi, _dedup_consecutive


def _make_filter(rules: dict) -> ToolOutputFilter:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fh:
        yaml.dump({"filters": rules}, fh)
        path = fh.name
    try:
        return ToolOutputFilter(config_path=path)
    finally:
        os.unlink(path)


def test_strip_ansi_removes_color_codes():
    assert _strip_ansi("\x1b[31mRED\x1b[0m") == "RED"


def test_strip_ansi_passthrough_clean():
    assert _strip_ansi("hello world") == "hello world"


def test_dedup_consecutive_collapses():
    assert _dedup_consecutive("a\na\na\nb\nb\nc") == "a [×3]\nb [×2]\nc"


def test_dedup_consecutive_no_repeats():
    assert _dedup_consecutive("a\nb\nc") == "a\nb\nc"


def test_passthrough_when_no_rule():
    f = _make_filter({})
    output = "some\noutput\nhere"
    assert f.filter("cat file.txt", output) == output


def test_strip_ansi_stage():
    f = _make_filter({"r": {"match_command": "^cmd", "strip_ansi": True}})
    assert f.filter("cmd arg", "\x1b[32mgreen\x1b[0m text") == "green text"


def test_match_output_short_circuit():
    f = _make_filter({
        "r": {"match_command": "^git", "match_output": [{"pattern": "Everything up-to-date", "message": "ok"}]},
    })
    assert f.filter("git push", "Everything up-to-date\nmore stuff") == "ok"


def test_match_output_no_match_continues():
    f = _make_filter({
        "r": {"match_command": "^git", "match_output": [{"pattern": "Everything up-to-date", "message": "ok"}], "max_lines": 5},
    })
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
    assert f.filter("cmd", "\n".join(str(i) for i in range(10))) == "7\n8\n9"


def test_on_empty_returned_when_filtered_result_empty():
    f = _make_filter({"r": {"match_command": "^pytest", "strip_lines_matching": [".*"], "on_empty": "All tests passed"}})
    assert f.filter("pytest tests/", "test_foo PASSED\ntest_bar PASSED") == "All tests passed"


def test_real_config_loads():
    f = ToolOutputFilter()
    assert isinstance(f._rules, list)


def test_real_config_git_rule_matches():
    f = ToolOutputFilter()
    assert "already up-to-date" in f.filter("git push origin main", "Everything up-to-date")


def test_real_config_passthrough_unknown_command():
    f = ToolOutputFilter()
    output = "hello\nworld"
    assert f.filter("my_custom_script.sh", output) == output
