# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pinned SDK request table and wire-capture harness shared by
``sdk_request_url_test.py`` and ``sdk_request_signature_params_test.py``.

Split out of ``sdk_request_url_test.py`` (#15187) once the signature-derived
query-parameter guard pushed that file past the 600-line cap
(``scripts/check_python_file_size.py``). ``SDK_REQUESTS`` is the single
pinned list of every request the SDK can make; both files assert against it,
and duplicating it would let the two copies drift -- exactly the failure
mode #15119's guard exists to prevent. ``route_query_params`` stays in
``conftest.py`` rather than here: it is a fixture, and the local
``autoflake`` pre-commit hook (``.pre-commit-config.yaml``, unscoped to
``repo_tests/``) strips an import it cannot see referenced as an expression,
which is exactly how a fixture *reused* across test files (rather than
defined by ``@pytest.fixture`` where pytest finds it) would be imported.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
from autobot_sdk import AutoBot

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_BASE = "http://backend.test:9999"

# The BACKEND's API root, stated here independently of the SDK. If the oracle
# in ``conftest.py`` read ``autobot_sdk.API_PREFIX`` instead, dropping the
# prefix from the SDK would move the route table with it and every assertion
# would still pass -- the mutation would have deleted its own detector.
# ``sdk_request_url_test.py``'s ``test_the_api_root_is_the_one_the_application_factory_mounts``
# anchors this constant to app_factory.py, and its
# ``test_the_sdk_uses_the_backend_api_root`` anchors the SDK to it.
_BACKEND_API_ROOT = "/api"


async def _record(call) -> list[tuple[str, str, frozenset[str]]]:
    """Run one SDK call against a transport that answers without dialling.

    The third element is the set of query-parameter **names** actually put on the
    wire. Read off ``request.url.params`` rather than off the method signature:
    ``AutoBotClient.get()`` drops ``None`` values, so what a method accepts and
    what it sends are two different sets and only the second one reaches a route.
    """
    seen: list[tuple[str, str, frozenset[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, frozenset(request.url.params.keys())))
        return httpx.Response(200, json={"success": True, "data": None, "status": "healthy"})

    async with AutoBot(base_url=_BASE, token="t") as bot:
        # Swap the transport in place so the real client construction, the real
        # base-URL merge and the real resource paths are all exercised.
        bot._client._transport = httpx.MockTransport(handler)
        await call(bot)
    return seen


def _urls(call) -> list[tuple[str, str, frozenset[str]]]:
    return asyncio.run(_record(call))


# ``(name, coroutine, expected METHOD, expected full path)`` — one row per
# request the SDK can make. Adding a resource method without a row here fails
# ``test_every_sdk_request_is_covered`` in ``sdk_request_url_test.py``.
SDK_REQUESTS = [
    ("sessions.list", lambda b: b.sessions.list(scope="team", team_id="t1"), "GET", "/api/chat/sessions"),
    ("sessions.get", lambda b: b.sessions.get("s1", page=2, per_page=10), "GET", "/api/chat/sessions/s1"),
    ("sessions.create", lambda b: b.sessions.create(title="t"), "POST", "/api/chat/sessions"),
    ("sessions.update", lambda b: b.sessions.update("s1", title="t"), "PUT", "/api/chat/sessions/s1"),
    ("sessions.delete", lambda b: b.sessions.delete("s1"), "DELETE", "/api/chat/sessions/s1"),
    ("agents.health", lambda b: b.agents.health(), "GET", "/api/agent/health/detailed"),
    ("agents.get_config", lambda b: b.agents.get_config("a1"), "GET", "/api/agent_config/agents/a1"),
    ("agents.set_model", lambda b: b.agents.set_model("a1", "m"), "POST", "/api/agent_config/agents/a1/model"),
    ("agents.set_enabled_on", lambda b: b.agents.set_enabled("a1", True), "POST", "/api/agent_config/agents/a1/enable"),
    (
        "agents.set_enabled_off",
        lambda b: b.agents.set_enabled("a1", False),
        "POST",
        "/api/agent_config/agents/a1/disable",
    ),
    ("agents.send_command", lambda b: b.agents.send_command("ls"), "POST", "/api/agent/execute_command"),
    ("knowledge.stats", lambda b: b.knowledge.stats(), "GET", "/api/knowledge_base/stats"),
    ("knowledge.add_text", lambda b: b.knowledge.add_text("x"), "POST", "/api/knowledge_base/add_text"),
    ("knowledge.search", lambda b: b.knowledge.search("q"), "POST", "/api/knowledge_base/search"),
    (
        "knowledge.get_entries",
        lambda b: b.knowledge.get_entries(limit=5, cursor="7", category="ops"),
        "GET",
        "/api/knowledge_base/entries",
    ),
    ("analytics.usage", lambda b: b.analytics.usage(), "GET", "/api/analytics/usage/statistics"),
    ("analytics.performance", lambda b: b.analytics.performance(), "GET", "/api/analytics/performance/metrics"),
]


def _template_for(concrete: str, templates) -> str | None:
    """The route template *concrete* fills in, or ``None``."""
    for template in templates:
        pattern = "/".join("[^/]+" if seg.startswith("{") else re.escape(seg) for seg in template.split("/"))
        if re.fullmatch(pattern, concrete):
            return template
    return None


def _assert_sent_params_are_accepted(name: str, verb: str, path: str, sent: frozenset[str], route_query_params) -> None:
    """The comparison every query-parameter guard runs: a name the SDK puts on
    the wire must be one the target route's own signature declares.

    Factored out so ``sdk_request_signature_params_test.py``'s contrast
    mutation exercises the exact logic the real per-row guard runs, rather
    than a re-implementation of it that could drift out of step (#15187).
    """
    template = _template_for(path, {p for _verb, p in route_query_params})
    assert template is not None, f"{name} requests {path}, which the oracle's mounted modules do not serve."
    accepted = route_query_params[(verb, template)]

    unknown = sent - accepted
    assert not unknown, (
        f"{name} sends {sorted(unknown)} to {verb} {template}, which declares "
        f"{sorted(accepted) or 'no query parameters at all'}. FastAPI drops an undeclared parameter "
        "without an error, so the caller's intent silently does not apply."
    )


#: Attribute each resource class hangs off ``AutoBot`` under -- ``bot.agents``,
#: ``bot.knowledge`` and so on. Shared because both the coverage check in
#: ``sdk_request_url_test.py`` and the signature probe in
#: ``sdk_request_signature_params_test.py`` need to turn a resource class into
#: the name a request row or a forced call addresses it by.
_RESOURCE_ATTRS = {
    "AgentsResource": "agents",
    "AnalyticsResource": "analytics",
    "KnowledgeResource": "knowledge",
    "SessionsResource": "sessions",
}
