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

Scope: the request. URL, HTTP method, and — since #15119 — every **query
parameter** the SDK puts on the wire, which must be one the target route declares.
``AutoBotClient.get()`` drops ``None`` values and passes everything else through,
so a parameter the route does not declare is sent, ignored by FastAPI, and the
caller's intent silently does not apply: ``knowledge.get_entries`` sent ``offset``
to a cursor-paginated route, ``sessions.list`` sent ``limit``/``offset`` to one
that is not paginated, and both analytics methods sent a ``period`` neither route
takes. Response *shapes* are asserted next door in
``sdk_response_model_contract_test.py`` and ``sdk_response_parsing_test.py``.

The #15119 checks above only see a parameter a ``SDK_REQUESTS`` row actually
passes; ``AutoBotClient.get()`` drops ``None`` values, so a parameter
defaulting to ``None`` that no row bothers to pass reaches neither this
file's ``observed`` set nor a route that might reject it -- the common shape,
since most optional parameters default to ``None`` (#15187). The
"Signature-derived coverage" section forces every parameter, named straight
off each resource method's own signature, so that gap does not depend on a
row remembering it.

This lives in ``repo_tests`` rather than beside the SDK deliberately: ci.yml's
roots do not include ``libs``, and marker-tests.yml selects only
marker-carrying tests there, so an unmarked test under
``libs/autobot-sdk-python/tests/`` would run in neither workflow (#15051).
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import re
import sys
import types
import typing
from pathlib import Path
from typing import Any

import httpx
import pytest
from autobot_sdk import API_PREFIX, AutoBot, api_path, default_base_url, resources
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

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
# ``test_every_sdk_request_is_covered`` below.
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


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_the_sdk_puts_the_expected_url_on_the_wire(name, call, method, expected):
    """Pin the exact method and path, not that some mock was called."""
    seen = [(verb, path) for verb, path, _params in _urls(call)]

    assert seen == [(method, expected)], f"{name} put {seen} on the wire, expected [('{method}', '{expected}')]"


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_the_url_the_sdk_builds_names_a_route_the_backend_serves(name, call, method, expected, served_routes):
    """The other half: the pinned path must exist in the real route table."""
    wanted = _urls(call)[0][1]

    assert _matches_a_route(wanted, served_routes), (
        f"{name} requests {wanted}, which the backend serves at no prefix. "
        f"This is the #15053 shape: a request URL nothing ever checked."
    )


# --------------------------------------------------------------------------
# Query parameters (#15119)
# --------------------------------------------------------------------------

#: Backend modules serving the paths above. Only these are imported, so the
#: oracle costs one small app rather than the whole backend.
#:
#: This list cannot go stale unnoticed: the app built from it is asked for every
#: path in ``SDK_REQUESTS``, so a module missing here shows up as a path the spec
#: does not contain, and ``test_every_sdk_request_path_is_in_the_query_oracle``
#: fails naming it.
SERVING_MODULES: tuple[str, ...] = (
    "api.agent",
    "api.agent_config",
    "api.analytics",
    "api.chat_sessions",
    "api.knowledge",
    "api.knowledge_search",
)

#: Every query-parameter name the SDK can put on the wire, across all of
#: ``SDK_REQUESTS``. Pinned rather than merely non-empty: a new parameter added to
#: a resource method without a row exercising it would otherwise be sent by
#: nothing here, and the subset assertion below would pass without ever seeing it.
SENT_QUERY_PARAMS = frozenset({"scope", "team_id", "page", "per_page", "limit", "cursor", "category"})


@pytest.fixture(scope="module")
def route_query_params() -> dict[tuple[str, str], frozenset[str]]:
    """``(METHOD, path template) -> declared query parameter names``.

    Built through ``fastapi.openapi.utils.get_openapi`` on an app that mounts the
    modules above exactly as ``app_factory`` mounts them -- ``/api`` + the prefix
    ``initialization/router_registry`` gives that module. Deliberately **not** a
    walk over ``router.routes``: from ``fastapi>=0.139`` ``include_router`` records
    an opaque wrapper instead of copying the child's routes onto the parent, so a
    flat walk finds almost nothing and every assertion over it passes vacuously.
    CI pins 0.141.1 and a development checkout may resolve below 0.139, so a local
    pass would prove nothing about the runner (#15091, #15093). ``get_openapi`` is
    the view FastAPI itself serves ``/openapi.json`` from and answers the same on
    both shapes.

    The mount prefixes are read from the registry rather than written here, so a
    router that moves is followed rather than silently mismatched.
    """
    registry = dict(routing.registry_entries(_BACKEND / "initialization" / "router_registry"))
    assert registry, "the router registry parsed no entries -- the oracle below would have nothing to mount"

    app = FastAPI()
    for module_path in SERVING_MODULES:
        assert module_path in registry, f"{module_path} is not mounted by initialization/router_registry"
        app.include_router(
            importlib.import_module(module_path).router, prefix=f"{_BACKEND_API_ROOT}{registry[module_path]}"
        )

    spec = get_openapi(title="sdk-request-oracle", version="1", routes=app.routes)
    declared: dict[tuple[str, str], frozenset[str]] = {}
    for path, operations in spec.get("paths", {}).items():
        for verb, operation in operations.items():
            names = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
            declared[(verb.upper(), path)] = frozenset(names)

    assert declared, "the oracle enumerated no routes at all; every assertion below would pass vacuously"
    assert any(names for names in declared.values()), (
        "no route in the oracle declares a single query parameter. Either the mounted set is wrong or "
        "the parameter extraction is -- an oracle where everything accepts nothing cannot detect a wrong name."
    )
    return declared


def _template_for(concrete: str, templates) -> str | None:
    """The route template *concrete* fills in, or ``None``."""
    for template in templates:
        pattern = "/".join("[^/]+" if seg.startswith("{") else re.escape(seg) for seg in template.split("/"))
        if re.fullmatch(pattern, concrete):
            return template
    return None


def test_the_rows_above_exercise_every_query_parameter_the_sdk_can_send():
    """An unexercised parameter is one this file would never see on the wire."""
    observed = frozenset().union(*(_urls(row[1])[0][2] for row in SDK_REQUESTS))

    assert observed == SENT_QUERY_PARAMS, (
        f"the SDK_REQUESTS rows put {sorted(observed)} on the wire, but this file expects "
        f"{sorted(SENT_QUERY_PARAMS)}. A parameter a method can send but no row does is checked by nothing."
    )


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_every_sdk_request_path_is_in_the_query_oracle(name, call, method, expected, route_query_params):
    """Proves SERVING_MODULES is sufficient before anything is read out of the oracle."""
    verb, wanted, _params = _urls(call)[0]
    template = _template_for(wanted, {path for _verb, path in route_query_params})

    assert template is not None, (
        f"{name} requests {wanted}, which the oracle's mounted modules do not serve. "
        f"Add the module serving it to SERVING_MODULES."
    )
    assert (verb, template) in route_query_params, f"{name} uses {verb} on {template}, which serves other verbs only"


def _assert_sent_params_are_accepted(name: str, verb: str, path: str, sent: frozenset[str], route_query_params) -> None:
    """The comparison every guard in this section runs: a name the SDK puts on
    the wire must be one the target route's own signature declares.

    Factored out so ``test_the_guard_flags_a_none_defaulted_parameter_the_route_does_not_accept``
    below exercises the exact logic the real guards run, rather than a
    re-implementation of it that could drift out of step (#15187).
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


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_every_query_parameter_the_sdk_sends_exists_on_the_route(name, call, method, expected, route_query_params):
    """AC (#15119): a parameter the route does not declare is dropped, and nothing said so.

    ``limit``/``offset`` on ``/chat/sessions``, ``offset`` on
    ``/knowledge_base/entries`` and ``period`` on both analytics routes each
    failed this way -- sent on every call, ignored on every call.
    """
    verb, wanted, sent = _urls(call)[0]
    _assert_sent_params_are_accepted(name, verb, wanted, sent, route_query_params)


# --------------------------------------------------------------------------
# Signature-derived coverage (#15187)
#
# The guard above only sees what a hand-written SDK_REQUESTS row happens to
# pass. ``AutoBotClient.get()`` drops ``None`` values, so a query parameter
# defaulting to ``None`` that no row bothers to pass is never on the wire this
# file observes -- ``test_the_rows_above_exercise_every_query_parameter_the_sdk_can_send``
# would not even notice it exists. Most optional parameters default to
# ``None``, so that is the common shape, not an edge case.
#
# The tests below force every parameter -- named straight off each resource
# method's own signature, independent of what any row does -- to a concrete
# value, so it reaches the wire and gets checked whether or not a row
# remembers it. A row is still required per parameter: an unexercised one is
# itself a failure below, so deriving the set from signatures does not trade
# one hole (a parameter no test sees) for another (a parameter this file
# claims coverage for but never actually calls through a public API surface).
#
# This does NOT close #15186's class of defect -- a parameter that *does*
# exist on the route signature but the handler never applies (``page`` on
# ``/chat/sessions/{id}``). That is a behavioural gap, not a naming one: the
# parameter passes every check here because it is declared, so only a test
# that asserts two different values produce two different responses (as
# ``test_pagination_advances_when_the_cursor_from_one_page_is_passed_to_the_next``
# does for the cursor) can catch it. Recorded here so nobody assumes this
# section's coverage extends to that shape.
# --------------------------------------------------------------------------


def _dummy_value(annotation: Any) -> Any:
    """A concrete, non-``None`` stand-in for *annotation*.

    Every optional parameter is forced to one of these rather than left at its
    declared default, so a ``None``-defaulted parameter reaches the wire
    exactly as it would for a caller who actually passes it. Only ``Optional``
    (``X | None``) is unwrapped -- recursing into every generic's type args
    would misread ``dict[str, Any]`` as a two-member union and hand back a
    string where a dict was wanted.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        for arg in typing.get_args(annotation):
            if arg is not type(None):
                return _dummy_value(arg)
        return "x"
    if annotation is bool:
        return True
    if annotation is int:
        return 7
    if annotation is float:
        return 1.5
    if annotation is dict or origin is dict:
        return {}
    return "x"


def _forced_call(resource_attr: str, fn):
    """A call to unbound method *fn*, bound to ``bot.<resource_attr>``, with
    every parameter set to a concrete value.

    ``inspect.signature`` names every parameter regardless of its default, so
    this reaches parameters no ``SDK_REQUESTS`` row is obliged to pass.
    ``**kwargs`` parameters are skipped: none in this SDK carry a query
    parameter (every one forwards into a JSON body -- see the resource
    docstrings), so there is no fixed name to force in the first place.
    """
    hints = typing.get_type_hints(fn)
    kwargs: dict[str, Any] = {}
    for pname, param in inspect.signature(fn).parameters.items():
        if pname == "self" or param.kind is inspect.Parameter.VAR_KEYWORD:
            continue
        kwargs[pname] = _dummy_value(hints.get(pname, str))

    async def call(bot):
        resource = getattr(bot, resource_attr)
        await fn(resource, **kwargs)

    return call


@pytest.fixture(scope="module")
def signature_forced_requests() -> dict[str, tuple[str, str, frozenset[str]]]:
    """``name -> (verb, path, query-parameter names)``, every optional
    parameter forced to a value, derived from each resource method's own
    signature rather than from what ``SDK_REQUESTS`` happens to exercise.
    """
    result: dict[str, tuple[str, str, frozenset[str]]] = {}
    for cls in (
        resources.AgentsResource,
        resources.AnalyticsResource,
        resources.KnowledgeResource,
        resources.SessionsResource,
    ):
        attr = _RESOURCE_ATTRS[cls.__name__]
        for method_name, fn in inspect.getmembers(cls, inspect.iscoroutinefunction):
            if method_name.startswith("_"):
                continue
            verb, path, sent = _urls(_forced_call(attr, fn))[0]
            result[f"{attr}.{method_name}"] = (verb, path, sent)
    assert result, "no resource methods were probed -- the introspection broke, not the SDK"
    return result


def test_every_signature_forced_parameter_exists_on_the_route(signature_forced_requests, route_query_params):
    """AC (#15187): does not depend on SDK_REQUESTS passing the parameter at
    all -- forcing every optional argument reaches a ``None``-defaulted one
    the pinned rows never exercise.
    """
    for name, (verb, path, sent) in signature_forced_requests.items():
        if sent:
            _assert_sent_params_are_accepted(name, verb, path, sent, route_query_params)


#: SDK_REQUESTS row names that do not match their underlying method name 1:1
#: -- two rows exercise the same ``set_enabled`` method with different args.
_ROW_METHOD_ALIASES = {"set_enabled_on": "set_enabled", "set_enabled_off": "set_enabled"}


def test_every_signature_derived_parameter_is_exercised_by_a_pinned_row(signature_forced_requests):
    """AC (#15187): a parameter the signature can send but no row exercises is
    a hole in coverage, not a pass -- deriving the set from signatures must
    not excuse SDK_REQUESTS from exercising every name in it.
    """
    pinned: dict[str, frozenset[str]] = {}
    for row_name, call, _method, _expected in SDK_REQUESTS:
        attr, _, method = row_name.partition(".")
        method = _ROW_METHOD_ALIASES.get(method, method)
        _, _, sent = _urls(call)[0]
        pinned[f"{attr}.{method}"] = pinned.get(f"{attr}.{method}", frozenset()) | sent

    for name, (_verb, _path, forced) in signature_forced_requests.items():
        missing = forced - pinned.get(name, frozenset())
        assert not missing, (
            f"{name} can send {sorted(missing)} once every optional parameter is forced, but no row in "
            f"SDK_REQUESTS exercises it -- add one, or the route contract for it is checked by nothing (#15187)."
        )


def test_the_guard_flags_a_none_defaulted_parameter_the_route_does_not_accept(route_query_params):
    """AC (#15187) contrast mutation: a ``None``-defaulted query parameter the
    route does not accept, exercised by no row, must fail this guard; removing
    it must pass again.

    A synthetic method stands in for a resource file so the mutation does not
    touch real source, but it is driven through the exact ``_forced_call`` /
    ``_assert_sent_params_are_accepted`` pipeline the real guards above use --
    this proves the mechanism catches the shape #15119's AC4 named, not a
    re-implementation of it.
    """

    class _Buggy:
        async def get_entries(self, category: str | None = None, secret_offset: str | None = None) -> None:
            await self._c.get("/knowledge_base/entries", category=category, secret_offset=secret_offset)

    class _Fixed:
        async def get_entries(self, category: str | None = None) -> None:
            await self._c.get("/knowledge_base/entries", category=category)

    verb, path, sent = _urls(_forced_call("knowledge", _Buggy.get_entries))[0]
    with pytest.raises(AssertionError, match="secret_offset"):
        _assert_sent_params_are_accepted("knowledge.get_entries", verb, path, sent, route_query_params)

    verb, path, sent = _urls(_forced_call("knowledge", _Fixed.get_entries))[0]
    _assert_sent_params_are_accepted("knowledge.get_entries", verb, path, sent, route_query_params)


def test_pagination_advances_when_the_cursor_from_one_page_is_passed_to_the_next():
    """AC (#15119): a second call with the first page's cursor returns different rows.

    Asserted against a stub of the route's own contract -- cursor in, the next
    slice plus the next cursor out -- rather than by reading the SDK back to
    itself. With ``offset`` the stub would answer from cursor ``"0"`` both times
    and the two pages would be identical, which is exactly what the route did.
    """
    pages = {
        "0": {"entries": [{"key": "k1"}], "next_cursor": "17", "count": 1, "has_more": True},
        "17": {"entries": [{"key": "k2"}], "next_cursor": "0", "count": 1, "has_more": False},
    }
    seen_cursors: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor", "0")
        seen_cursors.append(cursor)
        return httpx.Response(200, json=pages[cursor])

    async def run():
        async with AutoBot(base_url=_BASE, token="t") as bot:
            bot._client._transport = httpx.MockTransport(handler)
            first = await bot.knowledge.get_entries()
            return first, await bot.knowledge.get_entries(cursor=first.next_cursor)

    first, second = asyncio.run(run())

    assert seen_cursors == ["0", "17"], f"the route saw cursors {seen_cursors}; the second page did not advance"
    assert first.next_cursor == "17"
    assert [e.key for e in first.entries] == ["k1"]
    assert [e.key for e in second.entries] == ["k2"], "the second page returned the first page's rows"
    assert second.has_more is False


_RESOURCE_ATTRS = {
    "AgentsResource": "agents",
    "AnalyticsResource": "analytics",
    "KnowledgeResource": "knowledge",
    "SessionsResource": "sessions",
}


def test_every_sdk_request_is_covered():
    """A new resource method must arrive with a URL row above, or this fails."""
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
