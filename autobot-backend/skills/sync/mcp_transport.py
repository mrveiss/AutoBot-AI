# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""MCP transport layer — stdio, SSE, and HTTP transports (Issue #2133).

Each transport implements connect/send/receive/close so the MCPClient
is fully transport-agnostic.  Auto-detection maps URI schemes:

    stdio://<command>  →  StdioTransport
    sse://<host>/path  →  SSETransport   (https:// with Accept: text/event-stream)
    http(s)://<host>   →  HTTPTransport  (JSON-RPC POST to /rpc)
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# JSON-RPC version used by MCP
_JSONRPC = "2.0"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class MCPTransport(ABC):
    """Abstract MCP transport.  Implementations handle connection lifetime."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the underlying channel."""

    @abstractmethod
    async def send(self, request: Dict[str, Any]) -> None:
        """Send a JSON-RPC request object."""

    @abstractmethod
    async def receive(self) -> Dict[str, Any]:
        """Receive and return the next JSON-RPC response object."""

    @abstractmethod
    async def close(self) -> None:
        """Tear down the underlying channel."""

    async def request(self, method: str, params: Dict[str, Any] | None = None, req_id: int = 1) -> Dict[str, Any]:
        """Send a request and return its response (convenience wrapper)."""
        payload: Dict[str, Any] = {"jsonrpc": _JSONRPC, "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        await self.send(payload)
        return await self.receive()

    # Context-manager support so callers can use ``async with transport:``
    async def __aenter__(self) -> "MCPTransport":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------------------


class StdioTransport(MCPTransport):
    """Spawn a local MCP server as a subprocess and communicate over stdin/stdout.

    The command string is split on whitespace.  Each JSON-RPC message is
    sent as a single line terminated with ``\\n``.  Responses are read
    line-by-line.  This matches the reference MCP stdio framing spec.
    """

    def __init__(self, command: str, timeout: float = 30.0) -> None:
        """Initialise with a shell command string, e.g. ``"npx -y @modelcontextprotocol/server-filesystem /tmp"``."""
        self._command = command
        self._timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._recv_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Spawn the subprocess."""
        parts = self._command.split()
        logger.info("StdioTransport: spawning %s", parts)
        self._proc = await asyncio.create_subprocess_exec(
            *parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.debug("StdioTransport: pid=%s", self._proc.pid)

    async def send(self, request: Dict[str, Any]) -> None:
        """Write one JSON line to the subprocess stdin."""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("StdioTransport not connected")
        line = json.dumps(request) + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()
        logger.debug("StdioTransport: sent method=%s", request.get("method"))

    async def receive(self) -> Dict[str, Any]:
        """Read one JSON line from the subprocess stdout."""
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("StdioTransport not connected")
        async with self._recv_lock:
            try:
                raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=self._timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"StdioTransport: no response within {self._timeout}s")
        if not raw:
            raise EOFError("StdioTransport: subprocess closed stdout")
        return json.loads(raw.decode("utf-8"))

    async def close(self) -> None:
        """Terminate the subprocess gracefully."""
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            self._proc.kill()
        logger.debug("StdioTransport: closed pid=%s", self._proc.pid)
        self._proc = None


# ---------------------------------------------------------------------------
# SSE transport
# ---------------------------------------------------------------------------


class SSETransport(MCPTransport):
    """Connect to a remote MCP server using Server-Sent Events.

    The transport POSTs requests to ``<base_url>/message`` and reads
    responses from ``<base_url>/sse`` (the standard MCP SSE layout).
    Incoming SSE ``data:`` lines are parsed as JSON-RPC objects and queued
    internally so ``receive()`` can yield them in order.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Initialise with the base URL of the SSE-capable MCP server."""
        # Normalise sse:// → https://
        self._base_url = base_url.replace("sse://", "https://", 1)
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._sse_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Open HTTP session and start background SSE reader task.

        #12979 RAW carve-out (long-lived + streaming category): this session
        is held open for the transport's full lifetime — the background
        ``_read_sse`` task streams an SSE response with ``timeout=None`` for
        as long as the transport is connected, and ``send()`` reuses the same
        session for every outgoing POST. It is explicitly torn down in
        ``close()``. Not a per-request construction, so not a pooling
        candidate.
        """
        self._session = aiohttp.ClientSession()
        self._sse_task = asyncio.create_task(self._read_sse())
        logger.info("SSETransport: connected to %s", self._base_url)

    async def _read_sse(self) -> None:
        """Background task: stream SSE events into the internal queue."""
        assert self._session is not None
        url = f"{self._base_url}/sse"
        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
        try:
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                if resp.status != 200:
                    logger.error("SSETransport: GET %s returned %s", url, resp.status)
                    return
                async for line in _iter_sse_lines(resp.content):
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload and payload != "[DONE]":
                            try:
                                await self._queue.put(json.loads(payload))
                            except json.JSONDecodeError:
                                logger.warning(
                                    "SSETransport: invalid JSON in SSE data: %s",
                                    payload,
                                )
        except aiohttp.ClientError as exc:
            logger.error("SSETransport: SSE stream error: %s", exc)

    async def send(self, request: Dict[str, Any]) -> None:
        """POST a JSON-RPC request to the /message endpoint."""
        if self._session is None:
            raise RuntimeError("SSETransport not connected")
        url = f"{self._base_url}/message"
        async with self._session.post(url, json=request, timeout=aiohttp.ClientTimeout(total=self._timeout)) as resp:
            if resp.status not in (200, 202):
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
        logger.debug("SSETransport: sent method=%s", request.get("method"))

    async def receive(self) -> Dict[str, Any]:
        """Return the next response from the SSE queue."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=self._timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"SSETransport: no response within {self._timeout}s")

    async def close(self) -> None:
        """Cancel the SSE reader and close the HTTP session."""
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
            self._session = None
        logger.debug("SSETransport: closed")


async def _iter_sse_lines(stream: aiohttp.StreamReader) -> AsyncIterator[str]:
    """Yield decoded lines from an aiohttp StreamReader for SSE parsing."""
    async for raw in stream:
        yield raw.decode("utf-8").rstrip("\r\n")


# ---------------------------------------------------------------------------
# HTTP transport  (refactored from mcp_sync.py)
# ---------------------------------------------------------------------------


class HTTPTransport(MCPTransport):
    """Stateless HTTP JSON-RPC transport.

    Each request opens a new HTTP session so this transport is safe to use
    from multiple coroutines without shared session state.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        """Initialise with the base URL of the MCP HTTP server."""
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Pending response stored between send() and receive()
        self._pending: Dict[str, Any] | None = None

    async def connect(self) -> None:
        """HTTP is connectionless — nothing to open."""

    async def send(self, request: Dict[str, Any]) -> None:
        """POST the JSON-RPC request and buffer the response for receive()."""
        async with get_http_client().tracked_request(
            "POST",
            f"{self._base_url}/rpc",
            json=request,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as resp:
            if resp.status != 200:
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
            self._pending = await resp.json()
        logger.debug("HTTPTransport: sent method=%s", request.get("method"))

    async def receive(self) -> Dict[str, Any]:
        """Return the buffered response from the last send() call."""
        if self._pending is None:
            raise RuntimeError("HTTPTransport: receive() called before send()")
        result, self._pending = self._pending, None
        return result

    async def close(self) -> None:
        """HTTP is connectionless — nothing to close."""


class StreamableHTTPTransport(MCPTransport):
    """MCP "Streamable HTTP" transport (spec 2025-03-26+) — the successor to the
    two-endpoint SSE transport, and the transport most current third-party MCP
    servers speak (#11542).

    A single POST to the server's own endpoint URL carries each JSON-RPC
    request. The response is either a plain JSON body or a ``text/event-stream``
    body whose first ``data:`` frame is the JSON-RPC response — either way this
    is a synchronous request/response exchange, matching how MCPClient uses it.
    A server that returns an ``Mcp-Session-Id`` response header (typically on
    the ``initialize`` response) gets that id echoed back on every later
    request; ``close()`` best-effort DELETEs the session.

    Server-initiated push (the transport's optional GET+SSE stream) is not
    implemented — resource-update notifications continue to go through
    :class:`SSETransport` for servers that need them.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Initialise with the literal MCP endpoint URL (no path is appended)."""
        self._base_url = base_url
        self._timeout = timeout
        self._session_id: str | None = None
        self._pending: Dict[str, Any] | None = None

    async def connect(self) -> None:
        """HTTP is connectionless — nothing to open."""

    async def send(self, request: Dict[str, Any]) -> None:
        """POST the JSON-RPC request; buffer its JSON or SSE-framed response for receive()."""
        headers = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        async with get_http_client().tracked_request(
            "POST",
            self._base_url,
            json=request,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as resp:
            if resp.status == 202:
                self._pending = None
                return
            if resp.status != 200:
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)

            session_id = resp.headers.get("Mcp-Session-Id")
            if session_id:
                self._session_id = session_id

            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                self._pending = await self._first_sse_event(resp.content)
            else:
                self._pending = await resp.json()
        logger.debug("StreamableHTTPTransport: sent method=%s", request.get("method"))

    @staticmethod
    async def _first_sse_event(stream: aiohttp.StreamReader) -> Dict[str, Any]:
        """Return the first SSE ``data:`` frame from *stream*, parsed as JSON."""
        async for line in _iter_sse_lines(stream):
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
        raise EOFError("StreamableHTTPTransport: SSE response closed with no data frame")

    async def receive(self) -> Dict[str, Any]:
        """Return the buffered response from the last send() call."""
        if self._pending is None:
            raise RuntimeError("StreamableHTTPTransport: receive() called before send()")
        result, self._pending = self._pending, None
        return result

    async def close(self) -> None:
        """Best-effort DELETE to terminate the session, if the server issued one."""
        if not self._session_id:
            return
        try:
            async with get_http_client().tracked_request(
                "DELETE",
                self._base_url,
                headers={"Mcp-Session-Id": self._session_id},
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ):
                pass
        except aiohttp.ClientError as exc:
            # Session termination is a courtesy — a server that does not
            # support it (405) or is already gone is not an error to us.
            logger.debug("StreamableHTTPTransport: session termination DELETE failed: %s", exc)
        self._session_id = None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_transport(server_uri: str, timeout: float = 30.0) -> MCPTransport:
    """Return the correct MCPTransport for *server_uri*.

    Scheme detection:

    * ``stdio://``            → :class:`StdioTransport`          — remainder is the shell command
    * ``sse://``              → :class:`SSETransport`             — rewritten to ``https://``
    * ``streamable-http://``  → :class:`StreamableHTTPTransport`  — rewritten to ``http://``
    * ``streamable-https://`` → :class:`StreamableHTTPTransport`  — rewritten to ``https://``
    * anything else (``http://``, ``https://``) → :class:`HTTPTransport` (legacy ``/rpc`` JSON-RPC)
    """
    if server_uri.startswith("stdio://"):
        command = server_uri[len("stdio://") :]
        return StdioTransport(command, timeout=timeout)
    if server_uri.startswith("sse://"):
        return SSETransport(server_uri, timeout=timeout)
    if server_uri.startswith("streamable-http://"):
        return StreamableHTTPTransport("http://" + server_uri[len("streamable-http://") :], timeout=timeout)
    if server_uri.startswith("streamable-https://"):
        return StreamableHTTPTransport("https://" + server_uri[len("streamable-https://") :], timeout=timeout)
    return HTTPTransport(server_uri, timeout=timeout)
