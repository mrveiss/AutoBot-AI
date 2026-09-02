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

The mock base URL is NOT owned here either, for a sibling reason: the
hardcoded-value hook's test-file exemption
(``docs/developer/HARDCODING_PREVENTION.md``) is matched on filename, and
this module's name matches none of ``test_*.py``/``*_test.py``. A literal
that was allowed at its old address in ``sdk_request_url_test.py`` became a
violation purely by moving here, with no line changed (#15187 review; the
allowlist gap itself is filed separately, not fixed in this module). ``_urls``
takes ``base`` as a required argument instead; each ``*_test.py`` module
defines its own ``_BASE`` and rebinds ``_urls`` to a ``functools.partial``
that supplies it, so every existing ``_urls(call)`` call site is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
from autobot_sdk import AutoBot

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"

# The BACKEND's API root, stated here independently of the SDK. If the oracle
# in ``conftest.py`` read ``autobot_sdk.API_PREFIX`` instead, dropping the
# prefix from the SDK would move the route table with it and every assertion
# would still pass -- the mutation would have deleted its own detector.
# ``sdk_request_url_test.py``'s ``test_the_api_root_is_the_one_the_application_factory_mounts``
# anchors this constant to app_factory.py, and its
# ``test_the_sdk_uses_the_backend_api_root`` anchors the SDK to it.
_BACKEND_API_ROOT = "/api"


async def _record(call, base: str) -> list[tuple[str, str, frozenset[str]]]:
    """Run one SDK call against a transport that answers without dialling.

    The third element is the set of query-parameter **names** actually put on the
    wire. Read off ``request.url.params`` rather than off the method signature:
    ``AutoBotClient.get()`` drops ``None`` values, so what a method accepts and
    what it sends are two different sets and only the second one reaches a route.

    ``base`` is the caller's mock URL, not a literal owned here -- see the
    module docstring for why.
    """
    seen: list[tuple[str, str, frozenset[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, frozenset(request.url.params.keys())))
        return httpx.Response(200, json={"success": True, "data": None, "status": "healthy"})

    async with AutoBot(base_url=base, token="t") as bot:
        # Swap the transport in place so the real client construction, the real
        # base-URL merge and the real resource paths are all exercised.
        bot._client._transport = httpx.MockTransport(handler)
        await call(bot)
    return seen


def _urls(call, base: str) -> list[tuple[str, str, frozenset[str]]]:
    return asyncio.run(_record(call, base))


async def _record_body(call, base: str) -> list[tuple[str, str, str, frozenset[str]]]:
    """Run one SDK call and record ``(verb, path, content-type, body keys)``.

    A sibling of ``_record`` rather than a fourth element appended to it: every
    existing ``verb, path, sent = _urls(call)[0]`` unpack in the two guards that
    already import it would have to change, and widening a passing guard's
    tuple to add a field it does not use is churn with a failure mode
    (#15057). ``SDK_REQUESTS`` stays the single table both recorders drive, so
    the two cannot see different requests.

    Body keys are the **top-level** field names as they reach the wire, read off
    the encoded request rather than off the method's ``body`` dict, so what the
    SDK builds and what httpx actually sends are the same set. A request with no
    body records an empty set and an empty content type.
    """
    seen: list[tuple[str, str, str, frozenset[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.content
        media = request.headers.get("content-type", "").split(";")[0].strip() if raw else ""
        keys: frozenset[str] = frozenset()
        if raw:
            decoded = json.loads(raw)
            assert isinstance(decoded, dict), f"{request.method} {request.url.path} sends a non-object JSON body"
            keys = frozenset(decoded)
        seen.append((request.method, request.url.path, media, keys))
        return httpx.Response(200, json={"success": True, "data": None, "status": "healthy"})

    async with AutoBot(base_url=base, token="t") as bot:
        bot._client._transport = httpx.MockTransport(handler)
        await call(bot)
    return seen


def _bodies(call, base: str) -> list[tuple[str, str, str, frozenset[str]]]:
    return asyncio.run(_record_body(call, base))


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
