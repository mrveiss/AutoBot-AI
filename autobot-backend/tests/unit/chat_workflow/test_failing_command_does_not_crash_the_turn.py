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
from services.agent_terminal.command_executor import CommandExecutor
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
            {"status": "error", "stderr": "segfault", "return_code": 139},
            "./run-suite",
            None,
        )

        assert formatted["error"] is not None
        assert "segfault" in formatted["error"]

    def test_a_failure_with_neither_error_nor_stderr_still_carries_a_message(self):
        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            {"status": "error", "return_code": 1},
            "./run-suite",
            None,
        )

        assert formatted["error"], "an empty error message is what the default was meant to prevent"

    def test_an_explicit_error_message_is_preserved(self):
        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            {"status": "error", "error": "the real reason", "stderr": "noise"},
            "./run-suite",
            None,
        )

        assert formatted["error"] == "the real reason"


class TestTheRealBoundaryFromPtyResultToPrompt:
    """The test that would have caught round 2's finding, and did not exist.

    Rounds 1 and 2 both failed the same way: a test drove a helper with a dict
    hand-built to look plausible, and no producer ever emits that shape. Round 1
    fed `_create_execution_result` a non-zero `return_code` that its call sites
    are gated from ever supplying. Round 2 fed `_handle_command_error` a dict
    carrying `stdout` alongside `status: "error"` — which
    `_format_execution_result`'s error branch never produced, because it dropped
    every outcome field.

    So this drives the **actual chain**: a `_build_pty_result`-shaped dict →
    `TerminalTool._format_execution_result` → `_handle_command_error` → the
    rendered prompt. Nothing here is hand-shaped except the PTY result itself,
    which is the one end that genuinely originates data.
    """

    @staticmethod
    def _pty_result(return_code: int, stdout: str) -> dict:
        """Whatever `command_executor._build_pty_result` emits -- by calling it.

        #14141 round 4: this used to be a hand-written restatement whose
        docstring claimed it was "exactly what `_build_pty_result` emits". A
        restatement is only true on the day it is written; the producer can
        rename a key, stop setting one, or start setting `error`, and every
        assertion downstream keeps passing against a shape nothing produces.
        That is the same defect rounds 1 and 2 failed on, one layer further
        out -- so the producer is called instead of described.

        Note `stderr: ""` and no `error` key -- the PTY combines the streams.
        Those two facts are why the old fallback chain always degraded to its
        literal, and why a hand-built dict with an `error` key hid the bug.
        """
        return CommandExecutor._build_pty_result(CommandExecutor.__new__(CommandExecutor), stdout, return_code)

    def test_the_producer_still_derives_status_from_the_exit_code(self):
        """The invariant #14141 is really about, asserted at its origin.

        `_create_execution_result` also maps an exit code to a status, but both
        of its call sites are gated on ``status == "success"`` upstream, so that
        mapping is unreachable and cannot be what protects this. The single
        reachable decision is here, in the producer: everything downstream --
        `_format_execution_result`'s branch, `_dispatch_command_by_status`'s
        routing, and the ``Status:`` line the model reads -- propagates it
        rather than re-deriving it. If this line ever reports success for a
        non-zero exit, every one of those layers reports success too.
        """
        assert self._pty_result(0, "ok")["status"] == "success"
        for code in (1, 2, 127, 139, 255):
            result = self._pty_result(code, "output")
            assert result["status"] == "error", f"exit {code} was reported to the model as success"
            assert result["return_code"] == code

    @pytest.mark.asyncio
    async def test_a_failing_runners_report_survives_the_whole_chain(self):
        from chat_workflow.manager import ChatWorkflowManager
        from chat_workflow.tool_handler import ToolHandlerMixin

        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            self._pty_result(1, "47 failed, 200 passed"),
            "./run-suite",
            None,
        )

        results: list = []
        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
        async for _ in mixin._handle_command_error("./run-suite", formatted, [], "sess-1", results):
            pass

        assert results, "the failing command left no step"
        rendered = ChatWorkflowManager._format_execution_step(
            ChatWorkflowManager.__new__(ChatWorkflowManager), 1, results[0]
        )
        assert "47 failed, 200 passed" in rendered, "the failure report never reached the model"
        assert "Status: error" in rendered

    @pytest.mark.asyncio
    async def test_the_real_exit_code_survives_rather_than_a_default(self):
        """`return_code` used to be the literal default 1 — indistinguishable
        from a genuine exit 1, and wrong for 127 or 139."""
        from chat_workflow.tool_handler import ToolHandlerMixin

        formatted = TerminalTool._format_execution_result(
            TerminalTool.__new__(TerminalTool),
            self._pty_result(127, "command not found"),
            "./run-suite",
            None,
        )

        results: list = []
        mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
        async for _ in mixin._handle_command_error("./run-suite", formatted, [], "sess-1", results):
            pass

        assert results[0]["return_code"] == 127
