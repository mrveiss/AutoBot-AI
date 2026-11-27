# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The model reads command manuals on request and before it tries a command the task names (#22253)."""

from unittest.mock import patch

import pytest

from autobot_shared.tool_catalogue import ToolEffect, has_effect
from chat_workflow import manual_lookup
from chat_workflow.manual_lookup import handle_command_manual, manuals_for_prompt, with_command_manuals

_STORED = {"ping", "nmap", "arp", "ls"}


@pytest.fixture(autouse=True)
def _manual_store():
    """A store holding ``_STORED``; the synopsis is the name so the prompt text is checkable."""
    with (
        patch.object(manual_lookup, "has_manual", lambda name: name in _STORED),
        patch.object(manual_lookup, "manual_synopsis", lambda name: f"- `{name}`: SYNOPSIS-{name}"),
    ):
        yield


def test_the_tool_is_read_only_and_registered_with_a_schema():
    from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS, _UNIFORM_BUILTIN_TOOLS

    assert has_effect("command_manual", ToolEffect.READ) and not has_effect("command_manual", ToolEffect.WRITE)
    assert "command_manual" in _UNIFORM_BUILTIN_TOOLS
    assert _BUILTIN_TOOL_SCHEMAS["command_manual"]["required"] == ["command"]


@pytest.mark.asyncio
async def test_the_tool_returns_the_synopsis():
    results = []
    messages = [m async for m in handle_command_manual({"params": {"command": "ping"}}, results)]
    assert [m.content for m in messages] == ["- `ping`: SYNOPSIS-ping"]
    assert results == [{"tool": "command_manual", "status": "success", "output": "- `ping`: SYNOPSIS-ping"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "rm -rf /", "../etc/passwd", "ping; ls"])
async def test_the_tool_refuses_anything_but_a_program_name(bad):
    results = []
    messages = [m async for m in handle_command_manual({"params": {"command": bad}}, results)]
    assert messages[0].type == "error" and results[0]["status"] == "error"


def test_commands_named_in_the_user_message_get_their_manual():
    block = manuals_for_prompt("scan the subnet with nmap, then ping the gateway", "", [])
    assert "SYNOPSIS-nmap" in block and "SYNOPSIS-ping" in block


def test_commands_named_in_the_current_plan_step_get_their_manual():
    block = manuals_for_prompt("find out who is on the network", "Step 2: run arp -a", [])
    assert "SYNOPSIS-arp" in block


def test_a_command_that_already_worked_in_the_session_is_left_out():
    history = [{"command": "ping -c1 host", "return_code": 0}, {"command": "nmap -x", "return_code": 1}]
    block = manuals_for_prompt("ping and nmap the host", "", history)
    assert "SYNOPSIS-ping" not in block and "SYNOPSIS-nmap" in block


def test_a_task_naming_no_stored_command_adds_nothing():
    assert manuals_for_prompt("what is the weather in Riga", "", []) is None


def test_the_preload_is_bounded():
    block = manuals_for_prompt("ping nmap arp ls", "", [])
    assert block.count("SYNOPSIS-") == manual_lookup.PRELOAD_MANUAL_LIMIT


def test_the_prompt_carries_the_block_from_graph_state():
    state = {"user_message": "ping it", "plan_progress": {"block": ""}}
    assert with_command_manuals("BASE", state).startswith("BASE\n\n**Manuals for the commands this task names:**")
    assert with_command_manuals("BASE", {"user_message": "hello"}) == "BASE"
