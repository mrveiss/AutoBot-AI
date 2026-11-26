# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for ToolRegistry's KB-search tools (#13027).

``get_tool_registry = lazy_singleton(ToolRegistry)`` is called with no args
by every production call site (``services/llm_service.py``,
``api/image_generation.py``), so the constructor-injected ``knowledge_base``
was permanently ``None`` -- ``search_knowledge_base()`` and ``get_fact()``
always hit their ``if not self.knowledge_base:`` guard and reported
"Knowledge base is not available", making the LLM tool-calling KB-search
tool permanently non-functional.

Fix: ``_resolve_knowledge_base()`` lazily resolves the KB via the shared
``knowledge_factory.get_knowledge_base_async()`` singleton on first use,
regardless of constructor args. Also discovered along the way (#13024-class
bug, same file): ``search_knowledge_base`` itself called
``self.knowledge_base.search(query, n_results=n_results)`` -- a kwarg the
canonical ``search()`` doesn't accept -- which would have just traded one
silent failure ("KB unavailable") for another (caught ``TypeError``) once
the KB was actually wired in. Fixed in the same change since #13027 isn't
fully delivered without it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from knowledge.ownership import KnowledgeOwnership
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge_base import KnowledgeBase
from tools.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_search_knowledge_base_resolves_kb_and_returns_real_content():
    """No knowledge_base injected at construction -- matches every production caller."""
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [
        {"content": "AutoBot uses Redis for caching.", "metadata": {"owner_id": "alice", "visibility": "private"}}
    ]
    mock_kb.ownership_manager = KnowledgeOwnership(None)  # #16665: the real visibility decision

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=mock_kb)):
        result = await registry.search_knowledge_base("redis", n_results=5, user_id="alice")

    assert result["status"] == "success"
    assert "AutoBot uses Redis" in result["result"]
    mock_kb.search.assert_called_once_with("redis", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_search_knowledge_base_no_kb_available_reports_unavailable():
    registry = ToolRegistry()

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=None)):
        result = await registry.search_knowledge_base("redis")

    assert result["status"] == "error"
    assert result["result"] == "Knowledge base is not available"


@pytest.mark.asyncio
async def test_get_fact_by_query_resolves_kb_and_returns_real_content():
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [
        {
            "id": "f1",
            "content": "Redis caches KB embeddings.",
            "metadata": {"owner_id": "alice", "visibility": "private"},
        }
    ]
    mock_kb.ownership_manager = KnowledgeOwnership(None)

    with patch("knowledge_factory.get_knowledge_base_async", AsyncMock(return_value=mock_kb)):
        result = await registry.get_fact(query="redis", user_id="alice")

    assert result["status"] == "success"
    assert "Redis caches KB embeddings." in result["result"]
    mock_kb.search.assert_called_once_with("redis", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


@pytest.mark.asyncio
async def test_resolve_knowledge_base_caches_after_first_resolution():
    """The lazily-resolved KB is cached on the instance, not re-resolved every call."""
    registry = ToolRegistry()
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = []
    resolver = AsyncMock(return_value=mock_kb)

    with patch("knowledge_factory.get_knowledge_base_async", resolver):
        await registry.search_knowledge_base("q1")
        await registry.get_fact(query="q2")

    assert resolver.call_count == 1
    assert registry.knowledge_base is mock_kb


@pytest.mark.asyncio
async def test_search_knowledge_base_injected_at_construction_is_used_directly():
    """Constructor-injected knowledge_base (test/legacy callers) skips lazy resolution."""
    mock_kb = create_autospec(KnowledgeBase, instance=True)
    mock_kb.search.return_value = [
        {"content": "injected KB result", "metadata": {"owner_id": "alice", "visibility": "private"}}
    ]
    mock_kb.ownership_manager = KnowledgeOwnership(None)
    registry = ToolRegistry(knowledge_base=mock_kb)

    result = await registry.search_knowledge_base("q", user_id="alice")

    assert "injected KB result" in result["result"]
    mock_kb.search.assert_called_once_with("q", top_k=5, filters=RESEARCH_QUARANTINE_FILTER)


def _kb_with_alices_private_fact():
    kb = create_autospec(KnowledgeBase, instance=True)
    fact = {"id": "f1", "content": "alice only", "metadata": {"owner_id": "alice", "visibility": "private"}}
    kb.search.return_value = [fact]
    kb.get_fact.return_value = {
        "fact_id": "f1",
        "content": "alice only",
        "metadata": {"owner_id": "alice", "visibility": "private"},
    }
    kb.ownership_manager = KnowledgeOwnership(None)
    return kb


@pytest.mark.asyncio
@pytest.mark.parametrize("call", ["search", "get_fact_query", "get_fact_id", "execute_tool"])
async def test_agent_kb_tools_never_return_another_users_private_fact(call):
    """#16665: an agent reads as the user it runs for -- B sees nothing of A's, A does, no user sees nothing."""

    async def run(user_id):
        registry = ToolRegistry(knowledge_base=_kb_with_alices_private_fact())
        if call == "search":
            return await registry.search_knowledge_base("q", user_id=user_id)
        if call == "get_fact_query":
            return await registry.get_fact(query="q", user_id=user_id)
        if call == "get_fact_id":
            return await registry.get_fact(fact_id=1, user_id=user_id)
        return await registry.execute_tool("search_knowledge_base", {"query": "q"}, user_id=user_id)

    assert "alice only" not in repr(await run("bob"))
    assert "alice only" not in repr(await run(None))
    assert "alice only" in repr(await run("alice"))


@pytest.mark.asyncio
async def test_system_read_tools_work_through_get_tool_registry_without_worker_node(monkeypatch):
    """#22267: the system-info tool returns real data from the production singleton (service list: unit test below)."""
    from tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    assert registry.worker_node is None
    monkeypatch.setattr(registry, "_system_integration", None)  # undo restores None: no real instance stays cached

    info = await registry.query_system_information()

    assert info["status"] == "success"
    assert "os_type" in info["result"]


@pytest.mark.asyncio
async def test_list_system_services_returns_the_services_or_the_error_message(monkeypatch):
    """#22280: unit test, no real systemctl; a failure's message reaches the caller."""
    from unittest.mock import create_autospec

    from system_integration import SystemIntegration
    from tools.tool_registry import ToolRegistry

    registry = ToolRegistry()
    fake = create_autospec(SystemIntegration, instance=True)
    monkeypatch.setattr(registry, "_system_integration", fake)

    services = [{"Name": "ssh", "Status": "active"}]
    fake.list_services.return_value = {"status": "success", "services": services}
    assert (await registry.list_system_services())["result"] == services

    fake.list_services.return_value = {"status": "success", "services": []}
    assert (await registry.list_system_services())["result"] == []

    fake.list_services.return_value = {"status": "error", "message": "systemctl unavailable", "output": ""}
    assert (await registry.list_system_services())["result"] == "systemctl unavailable"


# ---------------------------------------------------------------------------
# One tool catalogue, each tool recording where it runs (#22276)
# ---------------------------------------------------------------------------


def test_available_tools_derive_from_the_catalogue():
    """#22276: ``get_available_tools`` is the catalogue's prompt list, not a literal."""
    from tools.tool_records import REGISTRY_TOOLS, prompt_tool_names
    from tools.tool_registry import ToolRegistry

    names = ToolRegistry().get_available_tools()
    assert names == prompt_tool_names()
    assert set(REGISTRY_TOOLS) <= set(names)


def test_every_tool_record_names_where_it_runs():
    from tools.tool_records import tool_records

    records = tool_records()
    assert records and all(r["kind"] == "tool" and r["serving_service"] for r in records)
    assert {r["fields"]["source"] for r in records} >= {"tool_registry", "browser"}


def test_no_second_tool_list():
    """#22276: a list/set literal restating five or more catalogue tool names is a second list."""
    import ast
    import pathlib

    from autobot_shared.testfile_names import is_test_filename
    from tools.tool_records import REGISTRY_TOOLS

    root = pathlib.Path(__file__).resolve().parents[1]
    names = set(REGISTRY_TOOLS)
    offenders = []
    for path in root.rglob("*.py"):
        skip = {"tests", "venv", "node_modules"} & set(path.parts)
        if skip or is_test_filename(path.name) or path.name == "tool_records.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                hits = sum(1 for e in node.elts if isinstance(e, ast.Constant) and e.value in names)
                if hits >= 5:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, f"#22276: second tool-name list in {offenders}; derive from tools.tool_records"


# ---------------------------------------------------------------------------
# One definition of each tool's required permission (#22278)
# ---------------------------------------------------------------------------


def test_every_registry_tool_declares_its_required_permission():
    from autobot_shared.auth.permissions import Permission
    from tools.tool_records import CHAT_SHELL_TOOL, REGISTRY_TOOLS, SPILL_READ_TOOL

    for name, entry in {**REGISTRY_TOOLS, **dict([SPILL_READ_TOOL, CHAT_SHELL_TOOL])}.items():
        assert len(entry) == 3, f"{name} must declare (category, location, required permission or None)"
        assert entry[2] is None or isinstance(entry[2], Permission), name


def test_catalogue_permissions_agree_with_the_mcp_permission_table():
    from autobot_shared.auth.mcp_tool_permissions import TOOL_PERMISSIONS
    from tools.tool_records import REGISTRY_TOOLS, required_permission_for

    for name in set(REGISTRY_TOOLS) & set(TOOL_PERMISSIONS):
        assert required_permission_for(name) == TOOL_PERMISSIONS[name], name


def test_catalogue_declares_the_checks_the_handler_enforced():
    from autobot_shared.auth.permissions import Permission
    from tools.tool_records import required_permission_for

    assert required_permission_for("web_search") == Permission.MCP_BROWSER_READ
    assert required_permission_for("crawl_site") == Permission.KNOWLEDGE_WRITE
    assert required_permission_for("scrape_url") == Permission.KNOWLEDGE_READ
    assert required_permission_for("execute_system_command") == Permission.SHELL_EXECUTE
    assert required_permission_for("execute_command") == Permission.SHELL_EXECUTE
    assert required_permission_for("search_knowledge_base") == Permission.KNOWLEDGE_READ
    assert required_permission_for("get_fact") == Permission.KNOWLEDGE_READ


def test_the_chat_shell_tool_is_a_record_with_its_permission_and_the_host_it_is_served_from():
    from tools.tool_records import LOCATION_BACKEND, tool_records

    shell = next(r for r in tool_records() if r["name"] == "execute_command")
    assert shell["fields"]["required_permission"] == "allow_shell_execute"
    assert shell["node_id"] and shell["serving_service"] == LOCATION_BACKEND


def test_a_tool_served_from_a_placed_service_carries_its_host_and_one_not_placed_carries_none():
    from tools.tool_records import LOCATION_WORKER, tool_records

    by_name = {r["name"]: r for r in tool_records()}
    assert by_name["web_search"]["node_id"]
    assert by_name["type_text"]["serving_service"] == LOCATION_WORKER and by_name["type_text"]["node_id"] is None


@pytest.mark.asyncio
async def test_execute_command_takes_its_permission_from_the_catalogue(monkeypatch):
    from autobot_shared.auth.permissions import Permission
    from chat_workflow import tool_handler
    from tools import tool_records

    seen = []

    async def record(name, params, session_id, tool_permission=None, user_role=None):
        seen.append(tool_permission)
        return False

    monkeypatch.setattr(tool_handler, "_emit_before_tool_execute", record)
    monkeypatch.setattr(
        tool_records, "_UNLISTED_TOOLS", {"execute_command": ("system", "x", Permission.WORKFLOW_CREATE)}
    )
    handler = tool_handler.ToolHandlerMixin()
    gen = handler._dispatch_execute_command({"params": {"command": "ls"}}, "s", "t", "e", "m", [], [], role="user")
    async for _ in gen:
        pass
    assert seen == [Permission.WORKFLOW_CREATE.value]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["scrape_url", "crawl_site"])
async def test_handler_gate_takes_the_permission_from_the_catalogue(monkeypatch, tool):
    from autobot_shared.auth.permissions import Permission
    from chat_workflow import tool_handler
    from tools import tool_records

    gate = []

    async def deny(name, params, session_id, permission, role, results):
        gate.append(permission)
        return object()

    monkeypatch.setattr(tool_handler, "permission_denial", deny)
    entry = tool_records.REGISTRY_TOOLS[tool]
    monkeypatch.setitem(tool_records.REGISTRY_TOOLS, tool, (*entry[:2], Permission.WORKFLOW_CREATE))
    handler = tool_handler.ToolHandlerMixin()
    async for _ in handler._handle_web_research_tool(tool, {"params": {}}, [], "s", "user"):
        pass
    assert gate == [Permission.WORKFLOW_CREATE.value]


def test_worker_dispatched_tools_are_recorded_at_the_worker_not_the_backend():
    """#22280: web_fetch, ask_user_for_manual and respond_conversationally go through _execute_worker_task."""
    from tools.tool_records import LOCATION_WORKER, tool_records

    by_name = {r["name"]: r for r in tool_records()}
    for name in ("web_fetch", "ask_user_for_manual", "respond_conversationally"):
        assert by_name[name]["serving_service"] == LOCATION_WORKER, name


def test_requires_is_declared_only_for_known_tools_and_sent_in_every_record():
    """#22298: ``requires`` names commands for catalogue tools only; every record carries the field."""
    from tools.tool_records import TOOL_REQUIRES, tool_records

    records = {r["name"]: r for r in tool_records()}
    assert set(TOOL_REQUIRES) <= set(records)
    assert all("requires" in r["fields"] for r in records.values())
    assert records["bring_window_to_front"]["fields"]["requires"] == ["xdotool"]
    assert records["web_fetch"]["fields"]["requires"] == []
