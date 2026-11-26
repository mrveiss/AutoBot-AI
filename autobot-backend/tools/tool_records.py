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

from typing import Any, Dict, List, Tuple

from autobot_shared.service_registry_core import SERVICE_DEFINITIONS
from autobot_shared.tool_catalogue import BROWSER_TOOLS

TOOL_RECORD_KIND = "tool"

#: Dispatched in the backend process.
LOCATION_BACKEND = SERVICE_DEFINITIONS["backend"].name
#: Dispatched to a worker node through ``ToolRegistry._execute_worker_task``.
LOCATION_WORKER = "worker-node"
#: Driven through ``browser_mcp`` against the browser service.
LOCATION_BROWSER = SERVICE_DEFINITIONS["playwright-vnc"].name

CATEGORY_WEB_RESEARCH = "web_research"

#: name -> (category, execution location). Order is the order the model's prompt lists them.
REGISTRY_TOOLS: Dict[str, Tuple[str, str]] = {
    "execute_system_command": ("system", LOCATION_WORKER),
    # These two fall back to the backend's SystemIntegration when no worker node is attached (#22267).
    "query_system_information": ("system", LOCATION_WORKER),
    "list_system_services": ("system", LOCATION_WORKER),
    "manage_service": ("system", LOCATION_WORKER),
    "get_process_info": ("system", LOCATION_WORKER),
    "terminate_process": ("system", LOCATION_WORKER),
    "web_fetch": ("web", LOCATION_BACKEND),
    "web_search": ("web", LOCATION_BACKEND),
    "search_knowledge_base": ("knowledge", LOCATION_BACKEND),
    "add_file_to_knowledge_base": ("knowledge", LOCATION_BACKEND),
    "store_fact": ("knowledge", LOCATION_BACKEND),
    "get_fact": ("knowledge", LOCATION_BACKEND),
    "type_text": ("gui", LOCATION_WORKER),
    "click_element": ("gui", LOCATION_WORKER),
    "bring_window_to_front": ("gui", LOCATION_WORKER),
    "read_text_from_region": ("gui", LOCATION_WORKER),  # #12070
    "move_mouse": ("gui", LOCATION_WORKER),
    "ask_user_for_manual": ("conversation", LOCATION_BACKEND),
    "respond_conversationally": ("conversation", LOCATION_BACKEND),
    "code_interpreter": ("code", LOCATION_BACKEND),
    "scrape_url": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND),  # #7509
    "crawl_site": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND),
    "map_site": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND),
    "extract_structured_data": (CATEGORY_WEB_RESEARCH, LOCATION_BACKEND),
    "content_reach": ("web", LOCATION_BACKEND),  # #10932
}

#: Offered only while the tool-output spill flag is on (#13754, #13865).
SPILL_READ_TOOL = ("read_spilled_output", ("conversation", LOCATION_BACKEND))


def tool_names_in_category(category: str) -> List[str]:
    """Registry tool names of one category, in catalogue order."""
    return [name for name, (cat, _) in REGISTRY_TOOLS.items() if cat == category]


def _spill_tools() -> Dict[str, Tuple[str, str]]:
    """The spill read tool when its flag is on, else nothing (never breaks prompt building)."""
    # Guarded: importing the leaf pulls in the whole ``agent_loop`` package (#13754).
    try:
        from agent_loop.tool_output_spill import SPILL_ENABLED  # noqa: PLC0415

        return dict([SPILL_READ_TOOL]) if SPILL_ENABLED else {}
    except Exception:  # pragma: no cover - never break prompt building
        from autobot_shared.logging_manager import get_logger  # noqa: PLC0415

        get_logger(__name__).warning("Could not resolve the tool-output spill flag; omitting its read tool", exc_info=True)
        return {}


def prompt_tool_names() -> List[str]:
    """Names offered to the model: registry tools, then the browser tools, sorted (#2609)."""
    # Lazy: chat_workflow -> tool_handler -> tools -> tool_registry -> chat_workflow (#4557).
    from chat_workflow.tool_handler import BROWSER_TOOL_NAMES  # noqa: PLC0415

    return [*REGISTRY_TOOLS, *_spill_tools(), *sorted(BROWSER_TOOL_NAMES)]


def _record(name: str, location: str, **fields: Any) -> Dict[str, Any]:
    """One tool as a plain record."""
    return {"kind": TOOL_RECORD_KIND, "name": name, "serving_service": location, "fields": fields}


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
            tags=list(m.tags),
        )
        for m in get_tool_registry().list_tools()
    ]


def tool_records() -> List[Dict[str, Any]]:
    """Every tool as a plain record (kind, stable name, serving service, declared fields)."""
    registry = [
        _record(n, loc, source="tool_registry", category=cat)
        for n, (cat, loc) in {**REGISTRY_TOOLS, **_spill_tools()}.items()
    ]
    browser = [_record(n, LOCATION_BROWSER, source="browser", category="browser") for n in BROWSER_TOOLS]
    return [*registry, *browser, *_sdk_records()]
