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

The checks here only see a parameter a ``SDK_REQUESTS`` row actually passes; a
parameter defaulting to ``None`` that no row bothers to pass reaches neither
this file's ``observed`` set nor a route that might reject it (#15187). That
gap is closed in ``sdk_request_signature_params_test.py``, split out once this
file's own #15187 section pushed it past the 600-line cap
(``scripts/check_python_file_size.py``). ``SDK_REQUESTS``, the wire-capture
harness and the per-row comparison both files share live in
``sdk_request_shared.py``; ``route_query_params`` is a fixture in
``conftest.py``, visible to both without either importing it by name.

This lives in ``repo_tests`` rather than beside the SDK deliberately: ci.yml's
roots do not include ``libs``, and marker-tests.yml selects only
marker-carrying tests there, so an unmarked test under
``libs/autobot-sdk-python/tests/`` would run in neither workflow (#15051).
"""

from __future__ import annotations

import asyncio
import functools
import importlib.util
import inspect
import re
import sys
from pathlib import Path

import httpx
import pytest
from autobot_sdk import API_PREFIX, AutoBot, api_path, default_base_url, resources

from autobot_shared.api_routing import router_prefixes as routing
from autobot_shared.ssot_config import config
from repo_tests.sdk_request_shared import (
    _BACKEND,
    _BACKEND_API_ROOT,
    _REPO,
    _RESOURCE_ATTRS,
    SDK_REQUESTS,
    _assert_sent_params_are_accepted,
    _template_for,
)
from repo_tests.sdk_request_shared import _urls as _shared_urls

# Own mock base URL rather than importing one: sdk_request_shared.py cannot
# hold this literal (see its module docstring -- the hardcoded-value hook's
# test-file exemption is filename-matched, and that module's name does not
# qualify). Rebinding ``_urls`` to a partial keeps every ``_urls(call)`` call
# site below unchanged.
_BASE = "http://backend.test:9999"
_urls = functools.partial(_shared_urls, base=_BASE)


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

#: Every query-parameter name the SDK can put on the wire, across all of
#: ``SDK_REQUESTS``. Pinned rather than merely non-empty: a new parameter added to
#: a resource method without a row exercising it would otherwise be sent by
#: nothing here, and the subset assertion below would pass without ever seeing it.
#:
#: This is deliberately weaker than ``sdk_request_signature_params_test.py``'s
#: coverage -- it only sees what a row here happens to pass -- but stays as a
#: fast, no-oracle sanity check that a row was not simply deleted.
SENT_QUERY_PARAMS = frozenset({"scope", "team_id", "page", "per_page", "limit", "cursor", "category"})


def test_the_rows_above_exercise_every_query_parameter_the_sdk_can_send():
    """An unexercised parameter is one this file would never see on the wire."""
    observed = frozenset().union(*(_urls(row[1])[0][2] for row in SDK_REQUESTS))

    assert observed == SENT_QUERY_PARAMS, (
        f"the SDK_REQUESTS rows put {sorted(observed)} on the wire, but this file expects "
        f"{sorted(SENT_QUERY_PARAMS)}. A parameter a method can send but no row does is checked by nothing."
    )


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_every_sdk_request_path_is_in_the_query_oracle(name, call, method, expected, route_query_params):
    """Proves ``conftest.py``'s ``SERVING_MODULES`` is sufficient before anything
    is read out of the oracle it builds.
    """
    verb, wanted, _params = _urls(call)[0]
    template = _template_for(wanted, {path for _verb, path in route_query_params})

    assert template is not None, (
        f"{name} requests {wanted}, which the oracle's mounted modules do not serve. "
        f"Add the module serving it to conftest.py's SERVING_MODULES."
    )
    assert (verb, template) in route_query_params, f"{name} uses {verb} on {template}, which serves other verbs only"


@pytest.mark.parametrize("name,call,method,expected", SDK_REQUESTS, ids=[r[0] for r in SDK_REQUESTS])
def test_every_query_parameter_the_sdk_sends_exists_on_the_route(name, call, method, expected, route_query_params):
    """AC (#15119): a parameter the route does not declare is dropped, and nothing said so.

    ``limit``/``offset`` on ``/chat/sessions``, ``offset`` on
    ``/knowledge_base/entries`` and ``period`` on both analytics routes each
    failed this way -- sent on every call, ignored on every call. The
    ``None``-defaulted-and-unexercised half of this same shape is guarded in
    ``sdk_request_signature_params_test.py`` instead (#15187).
    """
    verb, wanted, sent = _urls(call)[0]
    _assert_sent_params_are_accepted(name, verb, wanted, sent, route_query_params)


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
