# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one tool catalogue: every tool name, with where it runs (#22276).

Tool names came from five places: ``ToolRegistry``'s hardcoded list, ``ToolSDKRegistry``,
``BROWSER_TOOL_NAMES``, ``_INFRA_AND_SHELL_TOOLS`` and the YAML tool docs. The verdicts:

* ``ToolRegistry``'s list -> declared on each handler with ``declares_tool`` (category, location, permission,
  requires); ``REGISTRY_TOOLS`` here is derived from those declarations;
  ``ToolRegistry.get_available_tools`` and ``WEB_RESEARCH_TOOL_NAMES`` derive from it.
* ``ToolSDKRegistry`` -> the registered ``BaseTool`` classes; read live by ``tool_records``.
* ``BROWSER_TOOL_NAMES`` -> already derived from ``autobot_shared.tool_catalogue.BROWSER_TOOLS``;
  read here, never restated.
* ``_INFRA_AND_SHELL_TOOLS`` -> a governance *denylist* of patterns (``docker``, ``helm`` are
  not tools the model is offered), derived from ``autobot_shared.tool_catalogue``; not a
  catalogue entry, so not listed here.
* the YAML tool docs (``resources/knowledge/tools``) document command-line binaries for the
  knowledge base, not tools the model may call; they are content, not a second name list.

``tool_records()`` is the accessor the self-model ingests: plain dicts
(kind, stable name, serving service, declared fields). Adding a tool name elsewhere as a
literal list fails ``test_no_second_tool_list`` in ``tool_registry_test.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.auth.mcp_tool_permissions import required_permission as _mcp_required_permission
from autobot_shared.auth.permissions import Permission
from autobot_shared.service_registry_core import SERVICE_DEFINITIONS
from autobot_shared.tool_catalogue import BROWSER_TOOLS
from autobot_shared.tool_sdk.base import ToolPermission
from autobot_shared.tool_spec import (  # noqa: F401 - re-exported: callers import these names from here
    CATEGORY_WEB_RESEARCH,
    LOCATION_BACKEND,
    LOCATION_BROWSER,
    LOCATION_WORKER,
    SELF_MODEL_QUERY_TOOL_NAME,
    ToolSpec,
    declared_tools,
)

TOOL_RECORD_KIND = "tool"

ToolEntry = Tuple[str, str, Optional[Permission]]  # (category, execution location, required Permission)

#: Names derived from the handlers' declarations on first access (module ``__getattr__``): the handlers import
#: this package's leaf, so the catalogue cannot be built while they are still importing.
_DERIVED = ("REGISTRY_TOOLS", "TOOL_REQUIRES", "_UNLISTED_TOOLS", "SPILL_READ_TOOL", "CHAT_SHELL_TOOL")
_cache: Dict[str, Any] = {}

#: SDK ``ToolPermission`` level -> the canonical ``Permission`` a role must hold to see the tool.
#: ``role_has_permission`` knows only dot-style Permission values, so storing the bare level
#: would hide every SDK tool from every role.
_SDK_PERMISSIONS: Dict[ToolPermission, Optional[Permission]] = {
    ToolPermission.PUBLIC: None,
    ToolPermission.AUTHENTICATED: Permission.API_READ,
    ToolPermission.ADMIN: Permission.API_ADMIN,
    ToolPermission.SYSTEM: Permission.ADMIN_SYSTEM,
}


def _entry(spec: ToolSpec) -> ToolEntry:
    return (spec.category, spec.location, spec.permission)


def _all_specs() -> Dict[str, ToolSpec]:
    """Every declared tool: the ``ToolRegistry`` handlers, then the chat handlers (web search, the shell)."""
    from chat_workflow.tool_handler import ToolHandlerMixin  # noqa: PLC0415 - tool_handler imports this module
    from tools.tool_registry import ToolRegistry  # noqa: PLC0415 - ToolRegistry imports this module's leaf

    return declared_tools(ToolRegistry, ToolHandlerMixin)


def _build() -> None:
    """Fill the derived views once from the declarations."""
    specs = _all_specs()
    gated = [s for s in specs.values() if s.flag_gated]
    _cache["REGISTRY_TOOLS"] = {n: _entry(s) for n, s in specs.items() if s.listed and not s.flag_gated}
    _cache["TOOL_REQUIRES"] = {n: s.requires for n, s in specs.items() if s.requires}
    _cache["SPILL_READ_TOOL"] = (gated[0].name, _entry(gated[0]))
    _cache["CHAT_SHELL_TOOL"] = ("execute_command", _entry(specs["execute_command"]))
    _cache["_UNLISTED_TOOLS"] = dict([_cache["SPILL_READ_TOOL"], _cache["CHAT_SHELL_TOOL"]])


def __getattr__(name: str) -> Any:
    """Serve the derived catalogue views (PEP 562)."""
    if name not in _DERIVED:
        raise AttributeError(name)
    if not _cache:
        _build()
    return _cache[name]


def _view(name: str) -> Any:
    """A derived view, honouring a module-level override (the tests replace one)."""
    return globals()[name] if name in globals() else __getattr__(name)


def tool_names_in_category(category: str) -> List[str]:
    """Registry tool names of one category, in catalogue order.

    Reads the ``ToolRegistry`` declarations only: ``chat_workflow.tool_handler`` calls this while it is itself
    importing, so the chat handlers' declarations are not yet available (none is in a category looked up here).
    """
    from tools.tool_registry import ToolRegistry  # noqa: PLC0415

    return [n for n, s in declared_tools(ToolRegistry).items() if s.listed and s.category == category]


def required_permission_for(tool_name: str) -> Optional[Permission]:
    """The Permission the chat handler requires for registry tool *tool_name*; None when it declares no check."""
    return {**_view("REGISTRY_TOOLS"), **_view("_UNLISTED_TOOLS")}.get(tool_name, (None, None, None))[2]


def permission_value_for(tool_name: str) -> Optional[str]:
    """:func:`required_permission_for` as the dot-style value the BEFORE_TOOL_EXECUTE gate takes."""
    return _value(required_permission_for(tool_name))


def _spill_tools() -> Dict[str, ToolEntry]:
    """The spill read tool when its flag is on, else nothing (never breaks prompt building)."""
    # Guarded: importing the leaf pulls in the whole ``agent_loop`` package (#13754).
    try:
        from agent_loop.tool_output_spill import SPILL_ENABLED  # noqa: PLC0415

        return dict([_view("SPILL_READ_TOOL")]) if SPILL_ENABLED else {}
    except Exception:  # pragma: no cover - never break prompt building
        from autobot_shared.logging_manager import get_logger  # noqa: PLC0415

        get_logger(__name__).warning(
            "Could not resolve the tool-output spill flag; omitting its read tool", exc_info=True
        )
        return {}


def prompt_tool_names() -> List[str]:
    """Names offered to the model: registry tools, then the browser tools, sorted (#2609)."""
    # Lazy: chat_workflow -> tool_handler -> tools -> tool_registry -> chat_workflow (#4557).
    from chat_workflow.tool_handler import BROWSER_TOOL_NAMES  # noqa: PLC0415

    return [*_view("REGISTRY_TOOLS"), *_spill_tools(), *sorted(BROWSER_TOOL_NAMES)]


def _value(permission: Optional[Permission]) -> Optional[str]:
    """A Permission's dot-style value, or None."""
    return permission.value if permission else None


def _browser_permission(name: str) -> Optional[str]:
    """The browser tool's declared permission: the one the browser handler enforces (#14469)."""
    return _value(_mcp_required_permission(name))


#: location -> the service whose process really runs its code, where that is not the location's own service.
#: ``ToolRegistry._execute_worker_task`` calls ``WorkerNode.execute_task`` in-process (it never publishes to Redis),
#: and the task handlers drive ``worker.system_integration`` / ``gui_controller`` in that same process; the
#: ``SystemReadToolsMixin`` fallback is ``SystemIntegration`` in the backend as well. So worker tasks run on the
#: backend's host (#22298).
_EXECUTING_SERVICE: Dict[str, str] = {LOCATION_WORKER: LOCATION_BACKEND}


def location_host(location: str) -> Optional[str]:
    """The SSOT host that runs *location*'s code; None where the placement is not known from code."""
    executing = _EXECUTING_SERVICE.get(location, location)
    return next((d.host for d in SERVICE_DEFINITIONS.values() if d.name == executing), None)


def _record(name: str, location: str, **fields: Any) -> Dict[str, Any]:
    """One tool as a plain record; ``node_id`` is its serving service's SSOT host (None when not placed)."""
    return {
        "kind": TOOL_RECORD_KIND,
        "name": name,
        "serving_service": location,
        "node_id": location_host(location),
        "fields": {"requires": list(_view("TOOL_REQUIRES").get(name, ())), **fields},
    }


def _sdk_required_permission(level: ToolPermission) -> Optional[str]:
    """The canonical dot-style Permission value an SDK ``ToolPermission`` level stands for; None: no check."""
    permission = _SDK_PERMISSIONS[level]
    return _value(permission)


def _sdk_records() -> List[Dict[str, Any]]:
    """Tools registered as ``BaseTool`` classes in the SDK registry (run in the registering process)."""
    from autobot_shared.tool_sdk.registry import get_tool_registry  # noqa: PLC0415

    return [
        _record(
            m.name,
            LOCATION_BACKEND,
            source="tool_sdk",
            category="sdk",
            description=m.description,
            version=m.version,
            permission=m.permission.value,
            required_permission=_sdk_required_permission(m.permission),
            tags=list(m.tags),
        )
        for m in get_tool_registry().list_tools()
    ]


def tool_records() -> List[Dict[str, Any]]:
    """Every tool as a plain record (kind, stable name, serving service, declared fields)."""
    registry = [
        _record(n, loc, source="tool_registry", category=cat, required_permission=_value(perm))
        for n, (cat, loc, perm) in {
            **_view("REGISTRY_TOOLS"),
            **_spill_tools(),
            **dict([_view("CHAT_SHELL_TOOL")]),
        }.items()
    ]
    browser = [
        _record(n, LOCATION_BROWSER, source="browser", category="browser", required_permission=_browser_permission(n))
        for n in BROWSER_TOOLS
    ]
    return [*registry, *browser, *_sdk_records()]
