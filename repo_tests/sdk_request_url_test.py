# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every URL ``autobot_sdk`` constructs must name a route the backend serves (#15053).

The SDK shipped asking for ``/chat/sessions``, ``/health/detailed`` and thirteen
more paths that exist at no prefix. Its only test dialled a live backend, carried
``pytest.mark.integration``, and — until #15048 — was named by no workflow, so
nothing had ever observed a single one of its request URLs.

Two things make this guard different from the test that let that ship:

* it asserts the **actual URL** each resource method puts on the wire, captured
  from an ``httpx`` transport, not that a mock was called;
* it checks those URLs against the route table **derived from backend source**
  by the same resolver the blocking ``api-wiring`` gate uses, so a route that
  moves fails here rather than at a 404 in someone's integration.

Scope: URL and HTTP method only. The payloads several of these routes want differ
from what the SDK sends, and some responses are not ``DataResponse`` envelopes at all
— tracked in #15057, deliberately not asserted here.

This lives in ``repo_tests`` rather than beside the SDK deliberately: ci.yml's
roots do not include ``libs``, and marker-tests.yml selects only
marker-carrying tests there, so an unmarked test under
``libs/autobot-sdk-python/tests/`` would run in neither workflow (#15051).
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from pathlib import Path

import httpx
import pytest
from autobot_sdk import API_PREFIX, AutoBot, api_path, default_base_url

from autobot_shared.api_routing import router_prefixes as routing
from autobot_shared.ssot_config import config

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"
_BASE = "http://backend.test:9999"

# The BACKEND's API root, stated here independently of the SDK. If the oracle
# below read ``autobot_sdk.API_PREFIX`` instead, dropping the prefix from the
# SDK would move the route table with it and every assertion would still pass
# — the mutation would have deleted its own detector.
# ``test_the_api_root_is_the_one_the_application_factory_mounts`` anchors this
# constant to app_factory.py, and ``test_the_sdk_uses_the_backend_api_root``
# anchors the SDK to it.
_BACKEND_API_ROOT = "/api"


def _route_decorator_re():
    """The decorator grammar the blocking ``api-wiring`` gate already parses.

    The ``sys.modules`` entry exists only so ``exec_module`` can resolve the
    script's own self-references; it is removed again immediately. Leaving it
    installed trips the session-finish leak guard (#13361) -- which fails the
    run *after* pytest reports every test passed, so the job log carries no
    failing test to find. Restore the previous value rather than popping
    unconditionally: another module may legitimately own the name.
    """
    script = _REPO / "scripts" / "audit_api_wiring.py"
    spec = importlib.util.spec_from_file_location("audit_api_wiring", script)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get("audit_api_wiring")
    sys.modules["audit_api_wiring"] = module
    try:
        spec.loader.exec_module(module)
        return module.ROUTE_DECORATOR_RE
    finally:
        if previous is None:
            sys.modules.pop("audit_api_wiring", None)
        else:
            sys.modules["audit_api_wiring"] = previous


@pytest.fixture(scope="module")
def served_routes() -> set[str]:
    """The backend's route table, composed the way ``app_factory`` composes it.

    ``/api`` + the registry-configured mount prefix + the module's own
    ``APIRouter(prefix=...)`` + the decorator path. Deliberately NOT
    ``audit_api_wiring.backend_paths_static``: that one is a loose
    over-approximation — it crosses every mount prefix with every module and
    drops the ``/api`` root entirely, so ``/chat/sessions`` (the broken path
    this issue is about) is in it too. An oracle that contains the bug cannot
    detect the bug.
    """
    decorator_re = _route_decorator_re()
    entries = routing.registry_entries(_BACKEND / "initialization" / "router_registry")
    routes: set[str] = set()
    for path, mount in routing.resolve_registry_targets(_BACKEND, entries).items():
        source = Path(path).read_text(encoding="utf-8", errors="ignore")
        own = routing.file_router_prefix(source)
        for _method, route in decorator_re.findall(source):
            routes.add(f"{_BACKEND_API_ROOT}{mount}{own}{route}".rstrip("/") or _BACKEND_API_ROOT)

    assert "/api/chat/sessions" in routes, "the route resolver did not find the backend's own chat-sessions route"
    assert "/chat/sessions" not in routes, "the resolver dropped the /api root — it would accept the unprefixed bug"
    return routes


def _matches_a_route(concrete: str, routes: set[str]) -> bool:
    """Does a concrete request path fill in one of the table's templates?"""
    for route in routes:
        pattern = "/".join("[^/]+" if seg.startswith("{") else re.escape(seg) for seg in route.split("/"))
        if re.fullmatch(pattern, concrete):
            return True
    return False


async def _record(call) -> list[tuple[str, str]]:
    """Run one SDK call against a transport that answers without dialling."""
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"success": True, "data": None, "status": "healthy"})

    async with AutoBot(base_url=_BASE, token="t") as bot:
        # Swap the transport in place so the real client construction, the real
        # base-URL merge and the real resource paths are all exercised.
        bot._client._transport = httpx.MockTransport(handler)
        await call(bot)
    return seen


def _urls(call) -> list[tuple[str, str]]:
    return asyncio.run(_record(call))


# ``(name, coroutine, expected METHOD, expected full path)`` — one row per
# request the SDK can make. Adding a resource method without a row here fails
# ``test_every_sdk_request_is_covered`` below.
SDK_REQUESTS = [
    ("sessions.list", lambda b: b.sessions.list(limit=5), "GET", "/api/chat/sessions"),
    ("sessions.get", lambda b: b.sessions.get("s1"), "GET", "/api/chat/sessions/s1"),
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
    ("knowledge.get_entries", lambda b: b.knowledge.get_entries(), "GET", "/api/knowledge_base/entries"),
    ("analytics.usage", lambda b: b.analytics.usage(), "GET", "/api/analytics/usage/statistics"),
    ("analytics.performance", lambda b: b.analytics.performance(), "GET", "/api/analytics/performance/metrics"),
]


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_the_sdk_puts_the_expected_url_on_the_wire(name, call, method, expected):
    """Pin the exact method and path, not that some mock was called."""
    seen = _urls(call)

    assert seen == [(method, expected)], f"{name} put {seen} on the wire, expected [('{method}', '{expected}')]"


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_the_url_the_sdk_builds_names_a_route_the_backend_serves(name, call, method, expected, served_routes):
    """The other half: the pinned path must exist in the real route table."""
    wanted = _urls(call)[0][1]

    assert _matches_a_route(wanted, served_routes), (
        f"{name} requests {wanted}, which the backend serves at no prefix. "
        f"This is the #15053 shape: a request URL nothing ever checked."
    )


_RESOURCE_ATTRS = {
    "AgentsResource": "agents",
    "AnalyticsResource": "analytics",
    "KnowledgeResource": "knowledge",
    "SessionsResource": "sessions",
}


def test_every_sdk_request_is_covered():
    """A new resource method must arrive with a URL row above, or this fails."""
    import inspect

    from autobot_sdk import resources

    declared = {
        f"{_RESOURCE_ATTRS[cls.__name__]}.{name}"
        for cls in (
            resources.AgentsResource,
            resources.AnalyticsResource,
            resources.KnowledgeResource,
            resources.SessionsResource,
        )
        for name, _fn in inspect.getmembers(cls, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }
    covered = {row[0].split("(")[0] for row in SDK_REQUESTS}
    covered |= {"agents.set_enabled"}

    assert declared, "no async resource methods found — the introspection broke, not the SDK"
    uncovered = declared - covered
    assert not uncovered, f"resource methods with no URL row in SDK_REQUESTS: {sorted(uncovered)}"


def test_the_api_root_is_the_one_the_application_factory_mounts():
    """``/api`` is not a guess — app_factory prefixes every registered router with it."""
    factory = (_BACKEND / "app_factory.py").read_text(encoding="utf-8")

    assert f'prefix=f"{_BACKEND_API_ROOT}{{prefix}}"' in factory, (
        f"app_factory.py no longer mounts registered routers under {_BACKEND_API_ROOT!r}; "
        "this file's route table and autobot_sdk.API_PREFIX must both follow it."
    )


def test_the_sdk_uses_the_backend_api_root():
    """The SDK's prefix and the backend's root are two facts, checked against each other."""
    assert API_PREFIX == _BACKEND_API_ROOT


def test_the_api_root_is_applied_once_and_is_idempotent():
    assert api_path("/chat/sessions") == "/api/chat/sessions"
    assert api_path("chat/sessions") == "/api/chat/sessions"
    assert api_path("/api/chat/sessions") == "/api/chat/sessions"


def test_the_default_base_url_names_the_backend_port_not_the_slm(monkeypatch):
    """8000 is the Service Lifecycle Manager; the backend is ssot_config's backend port.

    Compared against the *declared field default*, not ``config.port.backend``:
    the live value follows whatever ``AUTOBOT_BACKEND_PORT`` a runner exports,
    and the two sides would then agree or disagree for reasons that have
    nothing to do with the SDK.
    """
    monkeypatch.delenv("AUTOBOT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTOBOT_BACKEND_HOST", raising=False)
    monkeypatch.delenv("AUTOBOT_BACKEND_PORT", raising=False)
    ports = type(config.port).model_fields
    backend_port, slm_port = ports["backend"].default, ports["slm"].default

    assert backend_port != slm_port, "backend and SLM port defaults collapsed; this guard proves nothing"
    assert httpx.URL(default_base_url()).port == backend_port, (
        f"the SDK defaults to port {httpx.URL(default_base_url()).port}, ssot_config declares "
        f"{backend_port} for the backend ({slm_port} is the SLM). The SDK ships as a standalone "
        "wheel and cannot import ssot_config, so this assertion is the only thing holding them together."
    )


def test_the_backend_host_and_port_env_vars_are_honoured(monkeypatch):
    """The aliases are the SDK's link to a deployment's configuration, not decoration."""
    monkeypatch.delenv("AUTOBOT_BASE_URL", raising=False)
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "backend.example")
    monkeypatch.setenv("AUTOBOT_BACKEND_PORT", "9443")

    assert default_base_url() == "http://backend.example:9443"


def test_an_explicit_base_url_env_var_still_wins(monkeypatch):
    monkeypatch.setenv("AUTOBOT_BASE_URL", "http://elsewhere.test:1234")

    assert default_base_url() == "http://elsewhere.test:1234"
