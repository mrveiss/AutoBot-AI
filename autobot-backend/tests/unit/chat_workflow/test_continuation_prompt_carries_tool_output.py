# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The continuation prompt must carry what the tool actually produced (#14120).

`_format_execution_step` builds the text that tells the model what its last tool
call returned. It read `command`/`stdout` only — the shape shell execution
records. Five other producers record `tool`/`output` instead:

    tool_handler.py:2328  browser success
    tool_handler.py:2523  web_search
    tool_handler.py:2579  web research
    tool_handler.py:2609  web research (second path)
    tool_handler.py:2747  extract_content

plus `read_spilled_output` (#13919). Every one of those rendered as::

    **Step 1:** `unknown`
    - Status: success
    - Output:
    ```
    (no output)
    ```

The model was not told the result was unavailable — it was told the tool ran
fine and returned nothing, which makes answering from parametric memory the
rational next move. That is very likely the mechanism behind #12508 ("wrong
specific facts in answers despite correct web_search results").

These tests assert against the **continuation prompt text**, not against the
`execution_results` entry. Every pre-existing test targeted the entry dict, which
is exactly why this shipped and stayed green.
"""

from typing import Any, Dict

import pytest

from chat_workflow.manager import ChatWorkflowManager


def _format(result: Dict[str, Any], step: int = 1) -> str:
    """Call the real formatter on a real instance shell.

    `__new__` rather than `object()` so this keeps working the day the method
    starts touching `self` — an unbound call with a foreign object would fail
    then for a reason that has nothing to do with what is being tested.
    """
    return ChatWorkflowManager._format_execution_step(ChatWorkflowManager.__new__(ChatWorkflowManager), step, result)


class TestAToolResultReachesTheModel:
    def test_a_web_search_result_appears_in_the_prompt(self):
        text = _format(
            {
                "tool": "web_search",
                "status": "success",
                "output": "1. Riga is the capital of Latvia, population 605,802 (2024).",
            }
        )

        assert "605,802" in text, "the search result never reached the model"
        assert "(no output)" not in text

    def test_the_step_is_named_by_its_tool_when_there_is_no_command(self):
        """`unknown` told the model nothing about which call it was reading."""
        text = _format({"tool": "extract_content", "status": "success", "output": "page body"})

        assert "extract_content" in text
        assert "`unknown`" not in text

    @pytest.mark.parametrize(
        "tool",
        ["web_search", "extract_content", "read_spilled_output", "browser_navigate"],
    )
    def test_every_output_producing_tool_family_is_carried(self, tool):
        text = _format({"tool": tool, "status": "success", "output": f"payload from {tool}"})

        assert f"payload from {tool}" in text

    def test_a_non_string_output_is_rendered_rather_than_raising(self):
        """`web_search` records a list; a bare `.strip()` raised on it."""
        text = _format({"tool": "web_search", "status": "success", "output": ["first hit", "second hit"]})

        assert "first hit" in text
        assert "second hit" in text


class TestTheFilterDoesNotEatToolContent:
    """The blocker found in review: fixing the drop at one layer re-opened it
    one layer down.

    `prepare_and_filter` runs `apply_no_op_detection`, which matches on the
    **output**, not the command, against `_NO_OP_PATTERNS` — `Already up to
    date`, `nothing to commit`, `working tree clean`. Before this change tool
    entries always arrived as the literal `"(no output)"`, so it was
    unreachable for them. Carrying real content made it live: a `web_search`
    result about a git question would be replaced wholesale by a short no-op
    string, under `Status: success`. Identical to #12508's shape.

    Shell entries keep the full pipeline; everything else gets only the shared
    hard cap.
    """

    @pytest.mark.parametrize(
        "phrase",
        ["Already up to date", "nothing to commit", "working tree clean", "Everything up-to-date"],
    )
    def test_a_tool_result_containing_a_no_op_phrase_survives(self, phrase):
        text = _format(
            {
                "tool": "web_search",
                "status": "success",
                "output": f"Stack Overflow: git says '{phrase}' but the commits are missing because of a shallow clone.",
            }
        )

        assert "shallow clone" in text, f"the no-op detector ate a tool result containing {phrase!r}"

    def test_a_shell_result_still_gets_the_no_op_treatment(self):
        """The guard must not disable the filter for the path it was built for."""
        text = _format({"command": "git pull", "status": "success", "stdout": "Already up to date.", "stderr": ""})

        assert "Status: success" in text

    def test_a_tool_named_like_a_lint_rule_is_not_parsed_as_one(self):
        """MCP tool names are bridge-supplied and unconstrained. Two rules in
        `tool_output_filters.yaml` have no separator after the verb
        (`^(eslint|flake8|mypy|black)`, `^(python -m )?pytest`), so an MCP tool
        called `pytest` would have its output run through a test-runner parser."""
        text = _format({"tool": "pytest", "status": "success", "result": "the bridge returned this verbatim"})

        assert "the bridge returned this verbatim" in text


class TestTheOtherFieldVocabularies:
    """`output` was not the whole gap — `result` covers the entire MCP bridge,
    and `error`/`reason` cover every failure and approval hold."""

    def test_an_mcp_result_reaches_the_model(self):
        text = _format({"tool": "some_mcp_tool", "status": "success", "result": "the bridge payload"})

        assert "the bridge payload" in text

    def test_an_error_says_why_and_not_only_that(self):
        text = _format({"tool": "web_search", "status": "error", "error": "provider returned 429"})

        assert "429" in text, "the model was told it failed but never why"

    def test_a_miss_reason_reaches_the_model(self):
        """`read_spilled_output`'s advice is written for the model to act on."""
        text = _format({"tool": "read_spilled_output", "status": "unknown", "reason": "retrying once is reasonable"})

        assert "retrying once is reasonable" in text

    def test_a_dict_output_renders_as_json_not_a_python_repr(self):
        """The LLC handler records a dict — the non-string shape that actually
        occurs. A Python repr would put single quotes in the model's context."""
        text = _format({"tool": "llc_create_task", "status": "success", "output": {"entity_type": "task", "id": 12}})

        assert '"entity_type": "task"' in text
        assert "'entity_type'" not in text


class TestTheShellPathIsUnchanged:
    """The regression guard. `command`/`stdout` producers must render exactly as
    before — a fix that carried `output` at the cost of `stdout` would trade one
    silent gap for another."""

    def test_stdout_still_renders(self):
        text = _format({"command": "ls -1", "status": "success", "stdout": "a.txt\nb.txt", "stderr": ""})

        assert "a.txt" in text and "b.txt" in text
        assert "`ls -1`" in text

    def test_stdout_wins_over_output_when_both_are_present(self):
        """`output` fills a gap; it never overrides a real stdout."""
        text = _format(
            {"command": "ls", "status": "success", "stdout": "the real stdout", "output": "should not appear"}
        )

        assert "the real stdout" in text
        assert "should not appear" not in text

    def test_stderr_is_still_appended(self):
        text = _format({"command": "ls /nope", "status": "error", "stdout": "", "stderr": "No such file"})

        assert "No such file" in text


class TestEmptyStillReadsAsEmpty:
    """The fix must not make "produced nothing" and "was dropped" look alike in
    the other direction — a step that genuinely produced no output must still
    say so."""

    def test_a_genuinely_silent_command_reports_no_output(self):
        text = _format({"command": "true", "status": "success", "stdout": "", "stderr": ""})

        assert "(no output)" in text

    def test_an_absent_output_key_reports_no_output(self):
        text = _format({"tool": "some_tool", "status": "success"})

        assert "(no output)" in text
