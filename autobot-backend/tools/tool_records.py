# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one tool catalogue: every tool name, with where it runs (#22276).

Tool names came from five places: ``ToolRegistry``'s hardcoded list, ``ToolSDKRegistry``,
``BROWSER_TOOL_NAMES``, ``_INFRA_AND_SHELL_TOOLS`` and the YAML tool docs. The verdicts:

* ``ToolRegistry``'s list -> this module's ``REGISTRY_TOOLS`` (declared once, with location);
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

TOOL_RECORD_KIND = "tool"

#: Dispatched in the backend process.
LOCATION_BACKEND = SERVICE_DEFINITIONS["backend"].name
#: Dispatched to a worker node through ``ToolRegistry._execute_worker_task``.
LOCATION_WORKER = "worker-node"
#: Driven through ``browser_mcp`` against the browser service.
LOCATION_BROWSER = SERVICE_DEFINITIONS["playwright-vnc"].name

CATEGORY_WEB_RESEARCH = "web_research"

#: The read-only chat tool over the SLM self-model (#22278); the self-awareness block points at it.
SELF_MODEL_QUERY_TOOL_NAME = "query_self_model"

#: name -> (category, execution location, required Permission or None). The permission is the one every route
#: enforces for the tool (``mcp_tool_permissions`` agrees); None means no route declares a check (#22278).
#: Order is the order the model's prompt lists them.
REGISTRY_TOOLS: Dict[str, Tuple[str, str, Optional[Permission]]] = {
    "execute_system_command": ("system", LOCATION_WORKER, Permission.SHELL_EXECUTE),
    # These two fall back to the backend's SystemIntegration when no worker node is attached (#22267).
    "query_system_information": ("system", LOCATION_WORKER, Permission.MCP_METRICS_READ),
    "list_system_services": ("system", LOCATION_WORKER, Permission.MCP_METRICS_READ),
    "manage_service": ("system", LOCATION_WORKER, None),
    "get_process_info": ("system", LOCATION_WORKER, None),
    "terminate_process": ("system", LOCATION_WORKER, None),
    "web_fetch": ("web", LOCATION_WORKER, None),  # ToolRegistry._execute_worker_task
    "web_search": ("web", LOCATION_BACKEND, Permission.MCP_BROWSER_READ),
    "search_knowledge_base": ("knowledge", LOCATION_BACKEND, Permission.KNOWLEDGE_READ),
    "add_file_to_knowledge_base": ("knowledge", LOCATION_BACKEND, None),
    "store_fact": ("knowledge", LOCATION_BACKEND, None),
    "get_fact": ("knowledge", LOCATION_BACKEND, Permission.KNOWLEDGE_READ),
    SELF_MODEL_QUERY_TOOL_NAME: ("self_model", LOCATION_BACKEND, None),
    "type_text": ("gui", LOCATION_WORKER, None),
    "click_element": ("gui", LOCATION_WORKER, None),
    "bring_window_to_front": ("gui", LOCATION_WORKER, None),
    "read_text_from_region": ("gui", LOCATION_WORKER, None),  # #12070
    "move_mouse": ("gui", LOCATION_WORKER, None),
    "ask_user_for_manual": ("conversation", LOCATION_WORKER, None),
    "respond_conversationally": ("conversation", LOCATION_WORKER, None),
    "code_interpreter": ("code", LOCATION_BACKEND, None),
    "scrape_url": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND, Permission.KNOWLEDGE_READ),  # #7509
    "crawl_site": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND, Permission.KNOWLEDGE_WRITE),
    "map_site": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND, Permission.KNOWLEDGE_READ),
    "extract_structured_data": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND, Permission.KNOWLEDGE_READ),
    "content_reach": ("web", LOCATION_BACKEND, None),  # #10932
}

#: SDK ``ToolPermission`` level -> the canonical ``Permission`` a role must hold to see the tool.
#: ``role_has_permission`` knows only dot-style Permission values, so storing the bare level
#: would hide every SDK tool from every role.
_SDK_PERMISSIONS: Dict[ToolPermission, Optional[Permission]] = {
    ToolPermission.PUBLIC: None,
    ToolPermission.AUTHENTICATED: Permission.API_READ,
    ToolPermission.ADMIN: Permission.API_ADMIN,
    ToolPermission.SYSTEM: Permission.ADMIN_SYSTEM,
}

#: tool -> command names its handler needs on the node it runs on (#22298). Only what the code proves; a tool
#: absent here declares none. Linux-only paths are safe: ``unavailable_because`` fires only for a command a node's
#: inventory reported and later lost, never for one it never had.
TOOL_REQUIRES: Dict[str, Tuple[str, ...]] = {
    # tool_registry.py ``bring_window_to_front`` -> task_handlers/executor.py gui_bring_window_to_front ->
    # gui_controller.py ``bring_window_to_front`` runs ["/usr/bin/xdotool", ...].
    "bring_window_to_front": ("xdotool",),
    # tool_registry.py ``read_text_from_region`` -> executor.py gui_read_text_from_region ->
    # gui_controller.py ``read_text_from_region`` calls ``pytesseract.image_to_string``, which shells out to
    # the ``tesseract`` binary (media/document/ocr.py: "pytesseract reaches a system binary").
    "read_text_from_region": ("tesseract",),
    # system_read_tools.py ``list_system_services`` -> system_integration.py ``_list_linux_services`` runs systemctl.
    "list_system_services": ("systemctl",),
    # tool_registry.py ``manage_service`` -> system_handlers.py -> system_integration.py ``_manage_linux_service``.
    "manage_service": ("systemctl",),
}

#: Offered only while the tool-output spill flag is on (#13754, #13865).
SPILL_READ_TOOL = ("read_spilled_output", ("conversation", LOCATION_BACKEND, None))


#: The chat shell tool: dispatched by ``_dispatch_execute_command``, not offered through the registry prompt list.
#: The handler reads its permission from here, so the shell check has one definition (#22278).
CHAT_SHELL_TOOL = ("execute_command", ("system", LOCATION_BACKEND, Permission.SHELL_EXECUTE))

#: Tools outside the prompt list that still carry a catalogue entry.
_UNLISTED_TOOLS: Dict[str, Tuple[str, str, Optional[Permission]]] = dict([SPILL_READ_TOOL, CHAT_SHELL_TOOL])


def tool_names_in_category(category: str) -> List[str]:
    """Registry tool names of one category, in catalogue order."""
    return [name for name, (cat, _, _perm) in REGISTRY_TOOLS.items() if cat == category]


def required_permission_for(tool_name: str) -> Optional[Permission]:
    """The Permission the chat handler requires for registry tool *tool_name*; None when it declares no check."""
    return {**REGISTRY_TOOLS, **_UNLISTED_TOOLS}.get(tool_name, (None, None, None))[2]


def permission_value_for(tool_name: str) -> Optional[str]:
    """:func:`required_permission_for` as the dot-style value the BEFORE_TOOL_EXECUTE gate takes."""
    return _value(required_permission_for(tool_name))


def _spill_tools() -> Dict[str, Tuple[str, str, Optional[Permission]]]:
    """The spill read tool when its flag is on, else nothing (never breaks prompt building)."""
    # Guarded: importing the leaf pulls in the whole ``agent_loop`` package (#13754).
    try:
        from agent_loop.tool_output_spill import SPILL_ENABLED  # noqa: PLC0415

        return dict([SPILL_READ_TOOL]) if SPILL_ENABLED else {}
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

    return [*REGISTRY_TOOLS, *_spill_tools(), *sorted(BROWSER_TOOL_NAMES)]


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
        "fields": {"requires": list(TOOL_REQUIRES.get(name, ())), **fields},
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
        for n, (cat, loc, perm) in {**REGISTRY_TOOLS, **_spill_tools(), **dict([CHAT_SHELL_TOOL])}.items()
    ]
    browser = [
        _record(n, LOCATION_BROWSER, source="browser", category="browser", required_permission=_browser_permission(n))
        for n in BROWSER_TOOLS
    ]
    return [*registry, *browser, *_sdk_records()]
