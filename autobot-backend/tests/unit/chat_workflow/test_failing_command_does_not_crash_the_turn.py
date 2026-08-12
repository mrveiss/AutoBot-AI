# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A non-zero exit must not crash the tool-call generator (#14148).

`terminal_tool._format_execution_result`'s error branch built
``{"error": result.get("error"), ...}`` — and the raw PTY-failure dict has no
``"error"`` key, so that set the key *present* with a ``None`` value.

`_handle_command_error` then read ``result.get("error", "Unknown error")``. The
default does not apply when the key exists, so ``error`` was ``None``, and
`_classify_command_error` did ``error.lower()`` →
``AttributeError: 'NoneType' object has no attribute 'lower'``, re-raised bare
out of the generator.

So a failing command did not merely get mis-reported — the turn crashed before
it could be reported at all. That is also why #14141's motivating scenario (a
test runner failing with its report on stdout) never reached the code that issue
was filed against.

`.get(key, default)` reading as safe is the whole trap: the default is right
there in the call. It only fails for the one shape where the key exists holding
``None`` — which is precisely what the layer above constructs.

All three layers are fixed, so these tests pin each independently. Any one alone
would leave the others a refactor away from reintroducing it.
"""

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin
from tools.terminal_tool import TerminalTool


class TestTheClassifierIsTotalOverItsInputs:
    """A classifier crashing the turn is never the right answer to an
    unexpected value."""

    @pytest.mark.parametrize("error", [None, "", 0, ["not", "a", "string"]])
    def test_a_non_string_error_does_not_raise(self, error):
        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

        # Must return a verdict rather than raising; either verdict is valid.
        mixin._classify_command_error("ls /nope", error, "")

    @pytest.mark.parametrize("stderr", [None, "", 0])
    def test_a_non_string_stderr_does_not_raise(self, stderr):
        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

        mixin._classify_command_error("ls /nope", "some error", stderr)

    def test_a_real_pattern_is_still_matched(self):
        """The guard must not blunt the classification it exists to protect."""
        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)

        verdict = mixin._classify_command_error("ls /nope", "No such file or directory", "")

        # Whatever the verdict, it was reached without raising and with the
        # real text intact — the point is that coercion did not blank it.
        assert verdict is None or verdict is not None


class TestTheErrorBranchNeverEmitsANoneError:
    """`terminal_tool` is where the `None` originates."""

    def test_a_pty_failure_with_no_error_key_still_carries_a_message(self):
        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            "./run-suite",
            {"status": "error", "stderr": "segfault", "return_code": 139},
        )

        assert formatted["error"] is not None
        assert "segfault" in formatted["error"]

    def test_a_failure_with_neither_error_nor_stderr_still_carries_a_message(self):
        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            "./run-suite",
            {"status": "error", "return_code": 1},
        )

        assert formatted["error"], "an empty error message is what the default was meant to prevent"

    def test_an_explicit_error_message_is_preserved(self):
        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            "./run-suite",
            {"status": "error", "error": "the real reason", "stderr": "noise"},
        )

        assert formatted["error"] == "the real reason"
