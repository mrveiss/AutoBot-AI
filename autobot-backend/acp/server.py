# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP agent server (#14825).

Implements the agent half of the Agent Client Protocol so any ACP client — Zed,
JetBrains IDEs, Neovim, Emacs — can drive an AutoBot agent without a bespoke
integration.

Lifecycle:

    initialize -> session/new -> session/prompt (repeat) [-> session/cancel]

While a prompt turn runs the agent streams ``session/update`` notifications and
may call back for ``session/request_permission`` before executing a tool.

The turn itself is delegated to a *runner* — an async callable yielding update
dicts.  Keeping that a seam means the protocol layer is testable without an LLM,
and AutoBot's chat workflow stays free of ACP vocabulary.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

from acp.protocol import (
    ACP_PROTOCOL_VERSION,
    AcpError,
    AcpErrorCode,
    AcpMethod,
    StopReason,
    agent_capabilities,
)
from acp.transport import StdioTransport
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# A runner receives (session_id, prompt_text, cwd) and yields ``session/update``
# payloads.  ``acp/runner.py`` supplies the AutoBot-backed implementation.
TurnRunner = Callable[[str, str, str], AsyncIterator[Dict[str, Any]]]


class AcpSession:
    """One ACP conversation."""

    def __init__(self, session_id: str, cwd: str):
        self.session_id = session_id
        self.cwd = cwd
        self.cancelled = False
        self.task: Optional[asyncio.Task] = None


class AcpServer:
    """JSON-RPC dispatch for the ACP agent surface."""

    def __init__(self, runner: TurnRunner, transport: StdioTransport | None = None):
        self._runner = runner
        self._transport = transport or StdioTransport()
        self._sessions: Dict[str, AcpSession] = {}
        self._initialized = False
        self._pending_client_calls: Dict[str, asyncio.Future] = {}
        self._next_call_id = 0

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Serve until stdin closes."""
        async for message in self._transport.messages():
            await self._dispatch(message)

    async def _dispatch(self, message: Dict[str, Any]) -> None:
        """Route one inbound JSON-RPC message."""
        # A response to something *we* asked the client (permission, fs read).
        if "method" not in message and "id" in message:
            self._resolve_client_call(message)
            return

        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        try:
            result = await self._handle(method, params)
        except AcpError as exc:
            if request_id is not None:
                await self._send_error(request_id, exc)
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unhandled ACP error in %s", method)
            if request_id is not None:
                await self._send_error(
                    request_id,
                    AcpError(AcpErrorCode.INTERNAL_ERROR, str(exc)),
                )
            return

        # Notifications carry no id and MUST NOT be answered.
        if request_id is not None:
            await self._transport.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def _handle(self, method: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch one method, enforcing the lifecycle order."""
        if method == AcpMethod.INITIALIZE:
            return self._initialize(params)

        # Everything else requires a completed handshake — otherwise a client
        # could create sessions against un-negotiated capabilities.
        if not self._initialized:
            raise AcpError(AcpErrorCode.INVALID_REQUEST, "initialize must be called first")

        if method == AcpMethod.SESSION_NEW:
            return await self._session_new(params)
        if method == AcpMethod.SESSION_PROMPT:
            return await self._session_prompt(params)
        if method == AcpMethod.SESSION_CANCEL:
            return await self._session_cancel(params)
        if method == AcpMethod.AUTHENTICATE:
            # No auth method is advertised at initialize, so a client should
            # never reach here; answering emptily is friendlier than an error.
            return {}

        raise AcpError(AcpErrorCode.METHOD_NOT_FOUND, f"Unknown method: {method}")

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Negotiate the protocol version and advertise capabilities."""
        requested = params.get("protocolVersion", ACP_PROTOCOL_VERSION)
        # Answer with the highest version both sides speak: never claim a
        # version above our own just because the client asked for it.
        negotiated = min(int(requested), ACP_PROTOCOL_VERSION) if isinstance(requested, int) else ACP_PROTOCOL_VERSION
        self._initialized = True
        return {
            "protocolVersion": negotiated,
            "agentCapabilities": agent_capabilities(),
            # Empty: this surface inherits the host's own authentication rather
            # than defining a second credential path.
            "authMethods": [],
        }

    async def _session_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a session rooted at an absolute working directory."""
        cwd = params.get("cwd")
        if not cwd or not str(cwd).startswith("/"):
            raise AcpError(AcpErrorCode.INVALID_PARAMS, "cwd must be an absolute path")
        session_id = f"acp-{uuid.uuid4()}"
        self._sessions[session_id] = AcpSession(session_id, str(cwd))
        logger.info("ACP session created: %s", session_id)
        return {"sessionId": session_id}

    async def _session_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run one prompt turn, streaming updates until it ends."""
        session = self._require_session(params.get("sessionId"))
        text = self._prompt_text(params.get("prompt"))
        session.cancelled = False

        try:
            async for update in self._runner(session.session_id, text, session.cwd):
                if session.cancelled:
                    return {"stopReason": StopReason.CANCELLED.value}
                await self._notify(AcpMethod.SESSION_UPDATE.value, update)
        except asyncio.CancelledError:
            return {"stopReason": StopReason.CANCELLED.value}
        except Exception as exc:
            logger.exception("ACP turn failed for %s", session.session_id)
            raise AcpError(AcpErrorCode.INTERNAL_ERROR, f"Turn failed: {exc}")

        if session.cancelled:
            return {"stopReason": StopReason.CANCELLED.value}
        return {"stopReason": StopReason.END_TURN.value}

    async def _session_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mark the session cancelled; the running turn observes the flag."""
        session_id = params.get("sessionId")
        session = self._sessions.get(str(session_id))
        if session is not None:
            session.cancelled = True
            if session.task is not None:
                session.task.cancel()
        return {}

    # ------------------------------------------------------------------
    # Client callbacks
    # ------------------------------------------------------------------

    async def request_permission(
        self,
        session_id: str,
        tool_call_id: str,
        title: str,
        options: list[Dict[str, Any]] | None = None,
    ) -> bool:
        """Ask the client to approve a tool call; True only on explicit allow.

        Fails closed: a malformed answer, an unknown option id, or a transport
        error all deny.  Treating an unreadable response as approval is the
        failure mode this gate exists to prevent.
        """
        options = options or [
            {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
            {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
        ]
        try:
            response = await self._call_client(
                AcpMethod.SESSION_REQUEST_PERMISSION.value,
                {
                    "sessionId": session_id,
                    "toolCall": {"toolCallId": tool_call_id, "title": title},
                    "options": options,
                },
            )
        except Exception as exc:
            logger.warning("Permission request failed, denying: %s", exc)
            return False

        outcome = (response or {}).get("outcome") or {}
        if outcome.get("outcome") != "selected":
            return False
        return str(outcome.get("optionId", "")).startswith("allow")

    async def _call_client(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Issue a JSON-RPC request to the client and await its response."""
        self._next_call_id += 1
        call_id = f"agent-{self._next_call_id}"
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_client_calls[call_id] = future
        await self._transport.send({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params})
        try:
            return await future
        finally:
            self._pending_client_calls.pop(call_id, None)

    def _resolve_client_call(self, message: Dict[str, Any]) -> None:
        """Complete the future awaiting this response."""
        call_id = str(message.get("id"))
        future = self._pending_client_calls.get(call_id)
        if future is None or future.done():
            return
        if "error" in message:
            future.set_exception(RuntimeError(str(message["error"])))
        else:
            future.set_result(message.get("result") or {})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _notify(self, method: str, params: Dict[str, Any]) -> None:
        """Send a notification (no id, no response expected)."""
        await self._transport.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send_error(self, request_id: Any, error: AcpError) -> None:
        await self._transport.send({"jsonrpc": "2.0", "id": request_id, "error": error.to_dict()})

    def _require_session(self, session_id: Any) -> AcpSession:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise AcpError(AcpErrorCode.INVALID_PARAMS, f"Unknown session: {session_id}")
        return session

    @staticmethod
    def _prompt_text(prompt: Any) -> str:
        """Flatten ACP prompt content blocks into plain text.

        Non-text blocks are skipped rather than stringified — image and audio
        input are not advertised in ``agent_capabilities``, so a client should
        not be sending them, and rendering their raw payload into the prompt
        would be worse than ignoring them.
        """
        if isinstance(prompt, str):
            return prompt
        if not isinstance(prompt, list):
            return ""
        parts = [block.get("text", "") for block in prompt if isinstance(block, dict) and block.get("type") == "text"]
        return "\n".join(part for part in parts if part)
