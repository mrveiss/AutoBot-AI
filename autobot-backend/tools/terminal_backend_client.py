# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend HTTP reads the terminal tool performs (#15110).

Four of ``TerminalTool``'s methods were not terminal logic at all: they built a
backend URL, issued one ``GET`` and shaped the response. None of them touched
``self``. They were the file's only users of ``aiohttp``, ``get_http_client``
and ``NetworkConstants``, and each rebuilt the same base URL by hand --

    f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"

-- three times verbatim, so a port or host change had three places to reach and
no test that would notice if it reached only two.

Splitting here was a precondition for #15110's real fix, not a tidy-up:
``tools/terminal_tool.py`` sat at 608 lines against a recorded ceiling of 608,
and the ratchet fails both above *and* below a recorded ceiling, so no line
could be added to it. This is the seam the file's own dependencies mark out --
every HTTP concern on one side, every session and PTY concern on the other.

These are module-level functions rather than a mixin because none of them reads
instance state; binding them to a class would only obscure that.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Seconds before a backend read is abandoned. Listing sessions and reading one
#: session's history are interactive lookups behind an agent's turn; the chat
#: transcript fetch is a bulk read and is allowed longer.
_LOOKUP_TIMEOUT_SECONDS = 5.0
_TRANSCRIPT_TIMEOUT_SECONDS = 10.0


def _backend_url() -> str:
    """The backend's base URL, built in one place.

    Imported inside the function because ``constants.network_constants`` reads
    the SSOT config at import time, which the callers of this module must not
    trigger merely by importing it.
    """
    from constants.network_constants import NetworkConstants

    return f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


def _timeout(seconds: float):
    import aiohttp

    return aiohttp.ClientTimeout(total=seconds)


async def list_terminal_sessions() -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Every terminal session the backend knows about.

    Returns ``(sessions, None)`` or ``([], error_dict)``.
    """
    http_client = get_http_client()
    async with await http_client.get(
        f"{_backend_url()}/api/terminal/sessions",
        timeout=_timeout(_LOOKUP_TIMEOUT_SECONDS),
    ) as response:
        if response.status != 200:
            return [], {"status": "error", "error": "Failed to list terminal sessions"}
        sessions_data = await response.json()
        return sessions_data.get("sessions", []), None


async def fetch_session_history(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """One session's command history.

    Returns ``(history, None)`` or ``(None, error_dict)``.
    """
    http_client = get_http_client()
    async with await http_client.get(
        f"{_backend_url()}/api/terminal/sessions/{session_id}/history",
        timeout=_timeout(_LOOKUP_TIMEOUT_SECONDS),
    ) as response:
        if response.status != 200:
            return None, {"status": "error", "error": "Failed to retrieve command history"}
        return await response.json(), None


async def query_agent_terminal_sessions(conversation_id: str) -> List[Dict[str, Any]]:
    """Agent terminal sessions linked to *conversation_id*; ``[]`` on any non-200.

    Deliberately ``/api/agent-terminal/sessions`` and not ``/api/terminal/sessions``:
    the two serve different session tables and the agent's session is only in
    the former.
    """
    http_client = get_http_client()
    async with await http_client.get(
        f"{_backend_url()}/api/agent-terminal/sessions",
        params={"conversation_id": conversation_id},
        timeout=_timeout(_LOOKUP_TIMEOUT_SECONDS),
    ) as response:
        if response.status == 200:
            data = await response.json()
            return data.get("sessions", [])
    return []


def _is_command_message(message: Dict[str, Any]) -> bool:
    """Whether a chat message records a command, by metadata or by its opening text."""
    if message.get("metadata", {}).get("type") == "command":
        return True
    return "command" in message.get("content", "").lower()[:50]


async def fetch_command_messages(conversation_id: str) -> List[Dict[str, Any]]:
    """Command-related messages from a conversation's transcript; ``[]`` on any non-200."""
    http_client = get_http_client()
    async with await http_client.get(
        f"{_backend_url()}/api/chats/{conversation_id}/messages",
        timeout=_timeout(_TRANSCRIPT_TIMEOUT_SECONDS),
    ) as response:
        if response.status != 200:
            logger.warning("Failed to fetch chat history for restoration: %s", response.status)
            return []
        data = await response.json()
        messages = data.get("messages", [])

    return [message for message in messages if _is_command_message(message)]
