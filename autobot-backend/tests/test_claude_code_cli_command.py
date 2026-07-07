# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""claude_code CLI command builder + forbidden-tool enforcement (GH#11186).

Proves the external CLI backend enforces a governed agent's disallowed tools via
``--disallowedTools`` and keeps its option-injection guards.
"""

from services.execution.base_backend import ExecutionTask
from services.execution.claude_code_backend import ClaudeCodeBackend


def _task(**metadata) -> ExecutionTask:
    return ExecutionTask(task_id="t1", code="do the thing", metadata=metadata)


def _build(task) -> list[str]:
    return ClaudeCodeBackend._build_cli_command(task, "claude", "/tmp/mcp.json")


def test_base_command_has_no_disallowed_flag():
    cmd = _build(_task())
    assert "--disallowedTools" not in cmd
    # prompt is positional, after the `--` option terminator
    assert cmd[-2] == "--"
    assert cmd[-1] == "do the thing"


def test_disallowed_tools_flag_added():
    cmd = _build(_task(disallowed_tools=["Bash", "Edit"]))
    i = cmd.index("--disallowedTools")
    assert cmd[i + 1] == "Bash,Edit"
    # governance flag must precede the `--` terminator (still an option)
    assert i < cmd.index("--")


def test_empty_disallowed_tools_omits_flag():
    assert "--disallowedTools" not in _build(_task(disallowed_tools=[]))


def test_disallowed_tools_injection_guarded():
    # A value that could be parsed as a flag is dropped; safe ones remain.
    cmd = _build(_task(disallowed_tools=["Bash", "--dangerously-skip-permissions", "Write"]))
    i = cmd.index("--disallowedTools")
    assert cmd[i + 1] == "Bash,Write"


def test_model_injection_guard_preserved():
    cmd = _build(_task(model="--evil"))
    assert "--model" not in cmd
    cmd2 = _build(_task(model="opus"))
    assert cmd2[cmd2.index("--model") + 1] == "opus"
