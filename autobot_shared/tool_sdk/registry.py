# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ToolSDKRegistry — central registry for unified-contract tools (#3018).

Provides registration, permission enforcement, input validation, and
OpenAPI spec generation for every BaseTool subclass registered with it.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Iterator, List, Type

from autobot_shared.coordination.run_progress import record_progress

from .base import (
    BaseTool,
    ToolInputError,
    ToolMetadata,
    ToolPermission,
    ToolResult,
    _timed_execute,
)

logger = logging.getLogger(__name__)

# The plugin whose code is registering tools right now; set by the plugin host (#19302).
_registering_plugin: ContextVar[str | None] = ContextVar("tool_registering_plugin", default=None)


@contextmanager
def registering_for_plugin(plugin_name: str) -> Iterator[None]:
    """Attribute every tool registered inside the block to *plugin_name* (#19302)."""
    token = _registering_plugin.set(plugin_name)
    try:
        yield
    finally:
        _registering_plugin.reset(token)


class PermissionDeniedError(Exception):
    """Raised when a caller's permission level does not satisfy a tool's requirement."""


class ToolNotFoundError(KeyError):
    """Raised when a requested tool name is not registered."""


class ToolSDKRegistry:
    """Central registry for BaseTool subclasses.

    Responsibilities
    ----------------
    * Register tool classes (not instances) so each call gets a fresh
      instance, avoiding shared mutable state between calls.
    * Enforce permission checks before execution.
    * Delegate input validation to the tool's own ``validate_input()``.
    * Collect wall-clock timing via ``_timed_execute()``.
    * Export a full OpenAPI-compatible spec via ``to_openapi_spec()``.

    Usage::

        registry = ToolSDKRegistry()
        registry.register(EchoTool)

        result = await registry.execute(
            "echo",
            {"text": "hello"},
            caller_permission=ToolPermission.PUBLIC,
        )
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Type[BaseTool]] = {}
        self._owners: Dict[str, str] = {}  # tool name -> owning plugin (#19302)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool_class: Type[BaseTool]) -> None:
        """Register a BaseTool subclass.

        The class must define ``metadata`` and ``input_schema`` at class
        level (enforced by ``BaseTool.__init_subclass__``).

        Args:
            tool_class: A concrete subclass of BaseTool.

        Raises:
            TypeError: If tool_class is not a BaseTool subclass.
            ValueError: If a tool with the same name is already registered.
        """
        if not (isinstance(tool_class, type) and issubclass(tool_class, BaseTool)):
            raise TypeError(f"Expected a BaseTool subclass, got {tool_class!r}")

        name = tool_class.metadata.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: '{name}'")

        self._tools[name] = tool_class
        owner = _registering_plugin.get()
        if owner:
            self._owners[name] = owner
        logger.info(
            "Registered tool '%s' v%s (permission=%s)",
            name,
            tool_class.metadata.version,
            tool_class.metadata.permission.value,
        )

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to remove.
        """
        if name in self._tools:
            del self._tools[name]
            self._owners.pop(name, None)
            logger.info("Unregistered tool '%s'", name)

    def unregister_plugin(self, plugin_name: str) -> int:
        """Remove every tool *plugin_name* registered; return how many (#19302).

        The host calls this on unload so cleanup never depends on the plugin's
        own ``shutdown()``.
        """
        names = [n for n, owner in self._owners.items() if owner == plugin_name]
        for name in names:
            self.unregister(name)
        return len(names)

    def _is_dispatchable(self, name: str) -> bool:
        """False when the owning plugin is known and disabled, unloaded or errored (#19302)."""
        owner = self._owners.get(name)
        if owner is None:
            return True
        from autobot_shared.plugin_sdk.hooks import (  # noqa: PLC0415  (plugin_sdk imports this package's peers)
            HookRegistry,
        )

        return not HookRegistry._plugin_is_inactive(owner)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        """Return a fresh instance of the named tool.

        Args:
            name: Registered tool name.

        Returns:
            New BaseTool instance.

        Raises:
            ToolNotFoundError: If the name is not registered.
        """
        tool_class = self._tools.get(name)
        if tool_class is None or not self._is_dispatchable(name):
            raise ToolNotFoundError(f"No tool registered with name '{name}'")
        return tool_class()

    def list_tools(
        self,
        permission_filter: ToolPermission | None = None,
    ) -> List[ToolMetadata]:
        """Return metadata for all registered tools.

        Args:
            permission_filter: When provided, only return tools whose required
                permission level is satisfied by *permission_filter*.  For
                example, passing ``ToolPermission.AUTHENTICATED`` returns all
                PUBLIC and AUTHENTICATED tools but excludes ADMIN and SYSTEM.

        Returns:
            List of ToolMetadata, sorted by tool name.
        """
        results = []
        for name, tool_class in self._tools.items():
            meta = tool_class.metadata
            if permission_filter is not None and not permission_filter.allows(meta.permission):
                continue
            if not self._is_dispatchable(name):
                continue
            results.append(meta)
        return sorted(results, key=lambda m: m.name)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        name: str,
        input_data: Dict,
        caller_permission: ToolPermission = ToolPermission.AUTHENTICATED,
    ) -> ToolResult:
        """Validate permission + input then execute the named tool.

        Steps
        -----
        1. Look up the tool class; raise ToolNotFoundError if absent.
        2. Check caller_permission >= tool.metadata.permission; raise
           PermissionDeniedError if not satisfied.
        3. Instantiate the tool and call validate_input(); return a failed
           ToolResult if validation fails.
        4. Execute the tool via _timed_execute() and return the ToolResult.

        Args:
            name: Registered tool name.
            input_data: Raw input dict to be validated by the tool.
            caller_permission: Permission level of the caller.

        Returns:
            ToolResult (may have success=False on validation or runtime error).

        Raises:
            ToolNotFoundError: When no tool with *name* is registered.
            PermissionDeniedError: When caller_permission is insufficient.
        """
        # Step 1: look up
        tool_class = self._tools.get(name)
        if tool_class is None or not self._is_dispatchable(name):
            raise ToolNotFoundError(f"No tool registered with name '{name}'")

        required = tool_class.metadata.permission

        # Step 2: permission check
        if not caller_permission.allows(required):
            logger.warning(
                "Permission denied: caller=%s required=%s tool='%s'",
                caller_permission.value,
                required.value,
                name,
            )
            raise PermissionDeniedError(
                f"Tool '{name}' requires {required.value} permission; " f"caller has {caller_permission.value}"
            )

        tool = tool_class()

        # Step 3: input validation
        try:
            validated = tool.validate_input(input_data)
        except ToolInputError as exc:
            logger.warning("Input validation failed for tool '%s': %s", name, exc)
            return ToolResult(success=False, error=str(exc))

        # Step 4: execute
        logger.debug(
            "Executing tool '%s' with caller_permission=%s",
            name,
            caller_permission.value,
        )
        try:
            return await _timed_execute(tool, validated)
        finally:
            # A finished tool call is progress for the claimed run it belongs to (#15950 AC4).
            record_progress()

    # ------------------------------------------------------------------
    # OpenAPI export
    # ------------------------------------------------------------------

    def to_openapi_spec(
        self,
        permission_filter: ToolPermission | None = None,
    ) -> Dict:
        """Generate an OpenAPI-compatible spec for all registered tools.

        The returned dict follows the structure used by LLM function-calling
        payloads and MCPDispatcher.get_tool_definitions(), making it a
        drop-in source for both.

        Args:
            permission_filter: When provided, exclude tools whose permission
                level exceeds the filter (same semantics as list_tools).

        Returns:
            Dict with a single key ``"tools"`` mapping to a list of tool
            definition dicts (name, description, version, permission, tags,
            parameters).
        """
        tools = []
        for tool_class in sorted(self._tools.values(), key=lambda c: c.metadata.name):
            meta = tool_class.metadata
            if permission_filter is not None and not permission_filter.allows(meta.permission):
                continue
            if not self._is_dispatchable(meta.name):
                continue
            instance = tool_class()
            tools.append(instance.to_openapi_schema())

        return {"tools": tools}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: ToolSDKRegistry | None = None


def get_tool_registry() -> ToolSDKRegistry:
    """Return the singleton ToolSDKRegistry (created on first call).

    Returns:
        Shared ToolSDKRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ToolSDKRegistry()
    return _registry
