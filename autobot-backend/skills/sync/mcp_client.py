# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Transport-agnostic MCP client (Issue #2133).

Supports the full MCP spec: tool discovery, tool invocation, resource
listing, resource subscriptions, and prompt templates — over any transport
(stdio, SSE, or HTTP).

Usage::

    from skills.sync.mcp_client import MCPClient
from autobot_shared.logging_manager import get_logger

    async with MCPClient("stdio://npx -y @modelcontextprotocol/server-fs /tmp") as client:
        tools = await client.discover_tools()
        result = await client.call_tool("read_file", {"path": "/tmp/hello.txt"})
"""

import asyncio
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from security.content_firewall import ContentSource, get_content_firewall
from skills.sync.mcp_transport import MCPTransport, create_transport
from type_defs.mcp import (
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPToolDefinition,
)

logger = get_logger(__name__)

# Incrementing per-client request counter start
_INIT_REQ_ID = 1


class MCPClient:
    """Transport-agnostic MCP client.

    Pass a server URI and the correct transport is selected automatically.
    All public methods are safe to call concurrently — a per-client lock
    serialises send/receive pairs on transports that are not natively
    multiplexed (stdio and HTTP).
    """

    def __init__(self, server_uri: str, timeout: float = 30.0) -> None:
        """Create a client for the given server URI.

        Args:
            server_uri: ``stdio://``, ``sse://``, ``http://`` or ``https://``
            timeout:    seconds to wait for each response
        """
        self._transport: MCPTransport = create_transport(server_uri, timeout=timeout)
        self._timeout = timeout
        self._req_id = _INIT_REQ_ID
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Context-manager interface
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MCPClient":
        await self._transport.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._transport.close()

    # ------------------------------------------------------------------
    # Low-level RPC
    # ------------------------------------------------------------------

    async def _call(self, method: str, params: Dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and return the ``result`` value.

        Raises :class:`MCPError` if the server returns an ``error`` field.
        """
        async with self._lock:
            req_id = self._req_id
            self._req_id += 1
            payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
            if params is not None:
                payload["params"] = params
            await self._transport.send(payload)
            response = await self._transport.receive()

        if "error" in response:
            err = response["error"]
            raise MCPError(
                code=err.get("code", -1),
                message=err.get("message", "unknown error"),
                data=err.get("data"),
            )
        return response.get("result")

    # ------------------------------------------------------------------
    # Tool operations
    # ------------------------------------------------------------------

    async def discover_tools(self) -> List[MCPToolDefinition]:
        """List all tools advertised by the MCP server.

        Returns:
            List of :class:`~type_defs.mcp.MCPToolDefinition` objects.
        """
        result = await self._call("tools/list", {})
        raw_tools: List[Dict[str, Any]] = (result or {}).get("tools", [])
        tools = []
        for raw in raw_tools:
            try:
                tools.append(MCPToolDefinition.model_validate(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCPClient: could not parse tool %s: %s", raw.get("name"), exc)
        logger.info("MCPClient: discovered %d tools", len(tools))
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any] | None = None) -> Any:
        """Invoke a named tool on the MCP server.

        Args:
            name:      Tool name as returned by :meth:`discover_tools`.
            arguments: Key/value arguments matching the tool's ``inputSchema``.

        Returns:
            The firewall-inspected ``result`` value from the server's JSON-RPC response.
        """
        params: Dict[str, Any] = {"name": name, "arguments": arguments or {}}
        result = await self._call("tools/call", params)
        logger.debug("MCPClient: tool %s returned %s", name, type(result).__name__)
        # #10552: inspect MCP tool output through the content firewall
        if result is not None:
            raw_str = result if isinstance(result, str) else str(result)
            verdict = await get_content_firewall().inspect(
                raw_str, source=ContentSource.MCP, context_label=name
            )
            if verdict.blocked:
                raise MCPError(code=-32603, message=f"MCP tool output blocked by content firewall (risk={verdict.risk.value})")
            result = verdict.content if isinstance(result, str) else result
        return result

    # ------------------------------------------------------------------
    # Resource operations
    # ------------------------------------------------------------------

    async def list_resources(self) -> List[MCPResourceDefinition]:
        """List all resources exposed by the MCP server.

        Returns:
            List of :class:`~type_defs.mcp.MCPResourceDefinition` objects.
        """
        result = await self._call("resources/list", {})
        raw_resources: List[Dict[str, Any]] = (result or {}).get("resources", [])
        resources = []
        for raw in raw_resources:
            try:
                resources.append(MCPResourceDefinition.model_validate(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCPClient: could not parse resource %s: %s", raw.get("uri"), exc)
        logger.info("MCPClient: found %d resources", len(resources))
        return resources

    async def subscribe_resource(self, uri: str) -> "ResourceSubscription":
        """Subscribe to change notifications for a resource URI.

        Sends ``resources/subscribe`` and returns an async context manager
        that yields notification payloads as they arrive.

        Args:
            uri: Resource URI as returned by :meth:`list_resources`.

        Returns:
            A :class:`ResourceSubscription` context manager.
        """
        await self._call("resources/subscribe", {"uri": uri})
        logger.info("MCPClient: subscribed to resource %s", uri)
        return ResourceSubscription(uri=uri, transport=self._transport, timeout=self._timeout)

    async def read_resource(self, uri: str) -> Any:
        """Read the current content of a resource.

        Args:
            uri: Resource URI.

        Returns:
            The firewall-inspected resource content from the server response.
        """
        result = await self._call("resources/read", {"uri": uri})
        logger.debug("MCPClient: read resource %s", uri)
        # #10552: inspect MCP resource content through the content firewall
        if result is not None:
            raw_str = result if isinstance(result, str) else str(result)
            verdict = await get_content_firewall().inspect(
                raw_str, source=ContentSource.MCP, context_label=f"resource:{uri}"
            )
            if verdict.blocked:
                raise MCPError(code=-32603, message=f"MCP resource blocked by content firewall (risk={verdict.risk.value})")
            result = verdict.content if isinstance(result, str) else result
        return result

    # ------------------------------------------------------------------
    # Prompt operations
    # ------------------------------------------------------------------

    async def list_prompts(self) -> List[MCPPromptDefinition]:
        """List all prompt templates available on the MCP server.

        Returns:
            List of :class:`~type_defs.mcp.MCPPromptDefinition` objects.
        """
        result = await self._call("prompts/list", {})
        raw_prompts: List[Dict[str, Any]] = (result or {}).get("prompts", [])
        prompts = []
        for raw in raw_prompts:
            try:
                prompts.append(MCPPromptDefinition.model_validate(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCPClient: could not parse prompt %s: %s", raw.get("name"), exc)
        logger.info("MCPClient: found %d prompts", len(prompts))
        return prompts

    async def get_prompt(self, name: str, arguments: Dict[str, str] | None = None) -> Any:
        """Retrieve a rendered prompt template.

        Args:
            name:      Prompt name as returned by :meth:`list_prompts`.
            arguments: Template argument values.

        Returns:
            The raw prompt result from the server.
        """
        params: Dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._call("prompts/get", params)


# ---------------------------------------------------------------------------
# Resource subscription helper
# ---------------------------------------------------------------------------


class ResourceSubscription:
    """Async context manager that yields resource-change notifications.

    Receives raw JSON-RPC notifications pushed by the server after a
    ``resources/subscribe`` call.  The caller iterates with ``async for``::

        async with await client.subscribe_resource("file:///tmp/data.json") as sub:
            async for notification in sub:
                process(notification)
    """

    def __init__(self, uri: str, transport: MCPTransport, timeout: float) -> None:
        self._uri = uri
        self._transport = transport
        self._timeout = timeout

    async def __aenter__(self) -> "ResourceSubscription":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    def __aiter__(self) -> AsyncIterator[Dict[str, Any]]:
        return self._notification_stream()

    async def _notification_stream(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield server-push notifications for the subscribed resource."""
        while True:
            try:
                msg = await asyncio.wait_for(self._transport.receive(), timeout=self._timeout)
            except (asyncio.TimeoutError, TimeoutError):
                logger.debug(
                    "ResourceSubscription: timeout waiting for %s notification",
                    self._uri,
                )
                return
            except EOFError:
                logger.info("ResourceSubscription: transport closed for %s", self._uri)
                return
            # MCP resource notifications arrive as method="notifications/resources/updated"
            if msg.get("method") in (
                "notifications/resources/updated",
                "resources/updated",
            ):
                yield msg
            else:
                logger.debug(
                    "ResourceSubscription: ignored unrelated message method=%s",
                    msg.get("method"),
                )


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Raised when the MCP server returns a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.data = data
