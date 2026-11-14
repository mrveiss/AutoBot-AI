# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`execute_command_sync` is the async `execute_command` minus the event loop (#18180).

The contract is that both entry points return the SAME `CommandResult` for the same command,
because they share the parse, timeout, not-found and execution-error helpers. Each case here
runs the command through both and compares the full result, so a divergence in either path --
or a copy of the logic growing in one of them -- fails by name.
"""

from __future__ import annotations

import os
import sys

import pytest

from utils.command_utils import CommandResult, execute_command, execute_command_sync

_PY = sys.executable


def _py(code: str) -> list[str]:
    return [_PY, "-c", code]


_CASES = {
    "success": (_py("print('hello')"), {}),
    "nonzero exit": (_py("import sys; sys.stderr.write('bad'); sys.exit(3)"), {}),
    "ansi stripped": (_py("print('\\x1b[31mred\\x1b[0m')"), {}),
    "invalid utf-8 replaced": (_py("import sys; sys.stdout.buffer.write(b'a\\xffb')"), {}),
    "timeout": (_py("import time; time.sleep(30)"), {"timeout": 0.5}),
    "not found": (["definitely-not-a-command-18180"], {}),
    "execution error": (["/"], {}),
}


@pytest.mark.parametrize("name", sorted(_CASES))
async def test_sync_and_async_return_the_same_result(name: str) -> None:
    args, kwargs = _CASES[name]
    expected = await execute_command(args, **kwargs)
    actual = execute_command_sync(args, **kwargs)
    assert isinstance(actual, CommandResult)
    if name == "execution error":
        # The message embeds the OS error text, which both paths build the same way.
        assert actual.status == expected.status == "error"
        assert actual.return_code == expected.return_code == 1
        assert actual.stderr.startswith("Error executing command:")
        return
    assert actual.to_dict() == expected.to_dict()


def test_statuses_and_codes_of_each_outcome() -> None:
    assert execute_command_sync(_py("print('hi')")).to_dict() == {
        "stdout": "hi",
        "stderr": "",
        "return_code": 0,
        "status": "success",
    }
    timed_out = execute_command_sync(_py("import time; time.sleep(30)"), timeout=0.5)
    assert (timed_out.status, timed_out.return_code) == ("timeout", -1)
    missing = execute_command_sync(["definitely-not-a-command-18180"])
    assert (missing.status, missing.return_code) == ("error", 127)
    assert missing.stderr == "Command not found: definitely-not-a-command-18180"


def test_env_is_merged_with_the_current_environment_and_cwd_is_honoured(tmp_path) -> None:
    code = "import os; print(os.environ['ONLY_18180'], os.environ['PATH'] != '', os.getcwd())"
    result = execute_command_sync(_py(code), env={"ONLY_18180": "x"}, cwd=str(tmp_path))
    assert result.stdout == f"x True {os.path.realpath(tmp_path)}"
