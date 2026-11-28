# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a tool declares itself (#22276).

A tool's catalogue metadata is declared on the tool's own handler, with :func:`declares_tool`, not in
a separate dict: category, where it runs, the permission its route enforces, the commands it needs on
its node. ``tools.tool_records`` derives the one tool catalogue by collecting these declarations from
the registered handler classes. This module is a leaf (it imports no tool code), so a handler module
can import it without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from autobot_shared.auth.permissions import Permission
from autobot_shared.service_registry_core import SERVICE_DEFINITIONS

#: Dispatched in the backend process.
LOCATION_BACKEND = SERVICE_DEFINITIONS["backend"].name
#: Dispatched to a worker node through ``ToolRegistry._execute_worker_task``.
LOCATION_WORKER = "worker-node"
#: Driven through ``browser_mcp`` against the browser service.
LOCATION_BROWSER = SERVICE_DEFINITIONS["playwright-vnc"].name

CATEGORY_WEB_RESEARCH = "web_research"

#: The read-only chat tool over the SLM self-model (#22278); the self-awareness block points at it.
SELF_MODEL_QUERY_TOOL_NAME = "query_self_model"

_SPEC_ATTR = "__tool_spec__"
_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass(frozen=True)
class ToolSpec:
    """One tool's declared catalogue metadata."""

    name: str
    category: str
    location: str
    permission: Optional[Permission] = None
    requires: Tuple[str, ...] = ()
    listed: bool = True  # False: dispatched and catalogued, but not offered through the registry prompt list
    flag_gated: bool = False  # offered only while its feature flag is on


def declares_tool(
    category: str,
    location: str,
    permission: Optional[Permission] = None,
    *,
    name: Optional[str] = None,
    requires: Tuple[str, ...] = (),
    listed: bool = True,
    flag_gated: bool = False,
) -> Callable[[_F], _F]:
    """Declare the decorated handler as a catalogue tool; *name* defaults to the method name."""

    def mark(handler: _F) -> _F:
        spec = ToolSpec(name or handler.__name__, category, location, permission, requires, listed, flag_gated)
        setattr(handler, _SPEC_ATTR, spec)
        return handler

    return mark


def declared_tools(*classes: type) -> Dict[str, ToolSpec]:
    """Every tool declared on *classes* (methods, inherited ones included), in definition order per class."""
    found: Dict[str, ToolSpec] = {}
    for cls in classes:
        for klass in reversed(cls.__mro__):
            for member in vars(klass).values():
                spec = getattr(member, _SPEC_ATTR, None)
                if spec is not None:
                    found[spec.name] = spec
    return found
