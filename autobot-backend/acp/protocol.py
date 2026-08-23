# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Client Protocol wire types (#14825).

ACP is the editor-to-agent standard from Zed Industries and JetBrains
(https://agentclientprotocol.com).  It is JSON-RPC 2.0, normally over stdio,
and it standardises the 1:1 conversation between one client and one agent:
initialize, create session, prompt, stream updates, call tools, ask permission.

This module holds only the vocabulary — method names, capability shapes, error
codes and the ``session/update`` constructors.  Transport lives in
``acp/transport.py`` and dispatch in ``acp/server.py``, so the protocol
definitions stay readable and independently testable.

Conventions ACP requires and this implementation honours:

* absolute file paths only;
* 1-based line numbers;
* ``camelCase`` property keys, with ``snake_case`` reserved for discriminators;
* Markdown as the default format for user-readable text.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

# The protocol revision this implementation speaks.  ACP negotiates at
# initialize: the client states what it supports and the agent answers with what
# it will use.
ACP_PROTOCOL_VERSION = 1


class AcpMethod(str, Enum):
    """Methods this agent serves, and those it calls back on the client."""

    # Client -> Agent (baseline)
    INITIALIZE = "initialize"
    AUTHENTICATE = "authenticate"
    SESSION_NEW = "session/new"
    SESSION_PROMPT = "session/prompt"

    # Client -> Agent (optional; advertised via capabilities)
    SESSION_LOAD = "session/load"
    SESSION_CANCEL = "session/cancel"  # notification

    # Agent -> Client
    SESSION_UPDATE = "session/update"  # notification
    SESSION_REQUEST_PERMISSION = "session/request_permission"


class StopReason(str, Enum):
    """Why a prompt turn ended.  Returned from ``session/prompt``."""

    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"
    REFUSAL = "refusal"
    CANCELLED = "cancelled"


class AcpErrorCode(int, Enum):
    """JSON-RPC error codes, standard range plus ACP usage."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    AUTH_REQUIRED = -32000


class AcpError(Exception):
    """An error that maps onto a JSON-RPC error object."""

    def __init__(self, code: AcpErrorCode, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        """Render as a JSON-RPC ``error`` member."""
        error: Dict[str, Any] = {"code": int(self.code), "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def agent_capabilities() -> Dict[str, Any]:
    """Declare what this agent actually implements.

    Deliberately conservative: a capability advertised but not implemented is
    worse than one omitted, because the client will call it.  ``loadSession`` is
    False until session replay is wired to the chat history store.
    """
    return {
        "loadSession": False,
        "promptCapabilities": {
            "image": False,
            "audio": False,
            "embeddedContext": True,
        },
    }


def text_block(text: str) -> Dict[str, Any]:
    """A ``text`` content block — ACP's default user-readable form."""
    return {"type": "text", "text": text}


def agent_message_chunk(session_id: str, text: str) -> Dict[str, Any]:
    """``session/update`` carrying a chunk of the agent's reply."""
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": text_block(text),
        },
    }


def agent_thought_chunk(session_id: str, text: str) -> Dict[str, Any]:
    """``session/update`` carrying a chunk of the agent's reasoning."""
    return {
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "agent_thought_chunk",
            "content": text_block(text),
        },
    }


def tool_call_update(
    session_id: str,
    tool_call_id: str,
    title: str,
    status: str,
    *,
    kind: str = "other",
    content: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """``session/update`` describing a tool call's lifecycle."""
    update: Dict[str, Any] = {
        "sessionUpdate": "tool_call",
        "toolCallId": tool_call_id,
        "title": title,
        "kind": kind,
        "status": status,
    }
    if content:
        update["content"] = content
    return {"sessionId": session_id, "update": update}


def plan_update(session_id: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """``session/update`` carrying the agent's plan for this turn."""
    return {
        "sessionId": session_id,
        "update": {"sessionUpdate": "plan", "entries": entries},
    }
