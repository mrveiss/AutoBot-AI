# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed command must not be reported to the model as succeeded (#14141).

`_create_execution_result` hardcoded ``"status": "success"`` regardless of
``return_code``. That dict feeds `_format_execution_step`, which prints
``- Status: {status}`` straight into the continuation prompt — so a command that
exited non-zero was reported to the model as having worked, with stderr as the
only hint.

The sharp case is a test runner: it writes its failure report to **stdout** and
exits non-zero. The model saw a full-looking report under ``Status: success`` and
no signal at all that the suite had failed, which makes building on the result
the rational next step.

Same family as #14120 (``Status: success`` beside ``(no output)``) and the #13852
silent-failure umbrella. These tests assert against the **continuation prompt
text** as well as the entry dict, because #14120 shipped and stayed green
precisely because every existing test targeted only the dict.
"""

from typing import Any, Dict

import pytest

from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_handler import _create_execution_result


#: A command that matches **no** rule in ``config/tool_output_filters.yaml``.
#:
#: This test started out using ``pytest -q`` and failed for an instructive
#: reason: that file's ``^(python -m )?pytest`` rule has no separator after the
#: verb, so the filter's five-state test-runner parser fired and rewrote the
#: body to "All tests passed" — the status assertions passed, the *content*
#: assertions did not. Correct behaviour for a shell entry, and exactly the
#: latent hazard noted while reviewing #14120. Naming the command something
#: inert keeps this file about status derivation rather than about the filter.
_INERT_COMMAND = "./run-suite"


def _entry(return_code: Any, stdout: str = "", stderr: str = "") -> Dict[str, Any]:
    return _create_execution_result(
        _INERT_COMMAND,
        "localhost",
        {"stdout": stdout, "stderr": stderr, "return_code": return_code},
    )


def _prompt(entry: Dict[str, Any]) -> str:
    return ChatWorkflowManager._format_execution_step(ChatWorkflowManager.__new__(ChatWorkflowManager), 1, entry)


class TestTheStatusFollowsTheExitCode:
    def test_exit_zero_is_success(self):
        assert _entry(0)["status"] == "success"

    @pytest.mark.parametrize("code", [1, 2, 127, 130, 255])
    def test_a_non_zero_exit_is_not_success(self, code):
        assert _entry(code)["status"] == "error"

    def test_a_failing_test_runner_is_not_reported_as_success(self):
        """The motivating case: the report is on stdout, so stderr is empty and
        the only signal the model could have had is the status."""
        entry = _entry(1, stdout="5 failed, 12 passed", stderr="")

        assert entry["status"] == "error"
        assert "Status: error" in _prompt(entry)
        assert "5 failed" in _prompt(entry)

    def test_the_return_code_is_still_carried(self):
        """The formatter can only surface what the entry keeps."""
        assert _entry(127)["return_code"] == 127


class TestAnUnknownOutcomeIsNotSuccess:
    """`None` is what an execution path produces when it never captured an exit
    code. "We do not know whether that worked" is far closer to failure than to
    success for the next turn — and defaulting it to success is exactly the
    defect being removed."""

    def test_a_missing_return_code_is_not_reported_as_success(self):
        entry = _create_execution_result("ls", "localhost", {"stdout": "", "stderr": ""})
        # An absent key defaults to 0 — a genuine "nothing reported a failure".
        assert entry["status"] == "success"

    def test_an_explicit_none_return_code_is_not_success(self):
        assert _entry(None)["status"] == "error"

    def test_an_unparseable_return_code_is_not_success(self):
        assert _entry("not-a-number")["status"] == "error"

    def test_a_numeric_string_is_still_read_as_its_value(self):
        assert _entry("0")["status"] == "success"
        assert _entry("1")["status"] == "error"


class TestTheWorkingPathIsUnchanged:
    def test_a_successful_command_still_renders_success(self):
        entry = _entry(0, stdout="a.txt\nb.txt")

        assert "Status: success" in _prompt(entry)
        assert "a.txt" in _prompt(entry)

    def test_the_other_fields_are_untouched(self):
        entry = _entry(0, stdout="out", stderr="err")

        assert entry["command"] == _INERT_COMMAND
        assert entry["host"] == "localhost"
        assert entry["stdout"] == "out"
        assert entry["stderr"] == "err"
        assert entry["approved"] is False
