# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent-facing description of the terminal tool (#15110).

Three of ``TerminalTool``'s methods returned nothing but literals: a static
description of the tool's own surface, handed to an agent so it knows what it
may call. They read no instance state and no module state, and they are the
only part of the file that changes when the *documentation* changes rather
than when the *behaviour* does.

Kept out of ``terminal_tool.py`` so that editing prose cannot push a module of
executable logic back over its size ceiling -- the condition that blocked
#15110's fix in #15073 until the file was split.

``TerminalTool.get_tool_description`` still delegates here, so the tool's
public surface is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict

#: What each public method does, in the shape an agent's tool schema expects.
METHOD_DESCRIPTIONS: Dict[str, Any] = {
    "create_session": {
        "description": "Create a new terminal session for this conversation",
        "parameters": {
            "agent_id": "Unique identifier for the agent",
            "conversation_id": "Chat conversation ID",
            "agent_role": "Role (chat_agent, automation_agent, system_agent, admin_agent)",
            "host": "Target host (main, frontend, npu-worker, redis, ai-stack, browser)",
        },
        "returns": "Session creation result",
    },
    "execute_command": {
        "description": "Execute a command in the terminal session",
        "parameters": {
            "conversation_id": "Chat conversation ID",
            "command": "Command to execute",
            "description": "Optional description of command purpose",
        },
        "returns": "Execution result, pending approval, or a post-execution failure carrying the output",
    },
    "get_session_info": {
        "description": "Get information about the terminal session",
        "parameters": {"conversation_id": "Chat conversation ID"},
        "returns": "Session information",
    },
    "close_session": {
        "description": "Close the terminal session",
        "parameters": {"conversation_id": "Chat conversation ID"},
        "returns": "Close result",
    },
}

#: The guarantees the tool makes about every command it runs.
SECURITY_FEATURES: Dict[str, str] = {
    "risk_assessment": "All commands assessed for security risk",
    "approval_workflow": "MODERATE+ risk commands require user approval",
    "user_control": "Users can interrupt and take control at any time",
    "audit_logging": "All commands logged with security metadata",
}


def tool_description() -> Dict[str, Any]:
    """The whole tool schema, as handed to an agent."""
    return {
        "name": "terminal_tool",
        "description": "Secure terminal access for command execution with approval workflow",
        "methods": METHOD_DESCRIPTIONS,
        "security_features": SECURITY_FEATURES,
        "usage_example": {
            "step1": "create_session(agent_id='chat_agent_1', conversation_id='abc123')",
            "step2": "execute_command(conversation_id='abc123', command='ls -la')",
            "step3": "close_session(conversation_id='abc123')",
        },
    }
