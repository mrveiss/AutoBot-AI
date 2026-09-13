# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every request the TypeScript SDK (``@autobot/sdk``, ``libs/autobot-sdk-ts``)
makes must name a route the backend actually serves, with parameters the
route actually declares (#15528, #16495).

This is the same class of guard as ``sdk_request_url_test.py`` (the Python
SDK's equivalent), aimed at a package this checker cannot execute: there is
no Node runtime available here, and running code from the checkout locally
is out of scope regardless of language. So this file does not import or run
any TypeScript. Instead:

* ``TS_SDK_REQUESTS`` pins, per resource method, the exact HTTP call its
  source is expected to make -- verb, path template (FastAPI's own
  ``{param_name}`` placeholder style, backend naming), and the query
  parameter / body field names it sends.
* ``_method_body`` extracts that one method's source text from the real
  ``.ts`` file (brace-counted from the method signature, not a whole-file
  regex, so a sibling method's similar-looking call cannot satisfy a row it
  does not belong to), and ``_path_literal``/``_sent_names`` read the call it
  makes off that isolated text. This is a static scan of committed source --
  the same category as grep or AST parsing -- not an execution of it.
  A path's ``{placeholder}`` is compared to the source's own
  ``${camelCaseVar}`` interpolation by *position*, not by exact spelling
  (``_normalize_path`` blanks every placeholder to ``{}`` before comparing) --
  the two sides deliberately use different naming conventions.
* Both are then checked against ``route_query_params`` / ``route_request_bodies``
  (``repo_tests/conftest.py``) -- the same backend-derived oracle
  ``sdk_request_url_test.py`` uses for the Python SDK, built once from the
  backend's own OpenAPI schema and shared by any test module in this
  directory. It is language-agnostic: a wrong path or parameter name here
  fails against the same ground truth the Python guard checks, without a
  second oracle to maintain.

A completeness test (``test_every_resource_method_has_a_pinned_row``) reads
every method declared on each resource class (again by regex over the
source, not reflection) and fails if one has no row above -- the same
"a new method ships with no request pinned" gate the Python guard's
``inspect``-based completeness check gives that package. It would have
caught `agents.setModel`/`setEnabled` shipping in the Python SDK with no
TypeScript counterpart at all (#15528).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_REPO = repo_root()
_SDK_TS_SRC = _REPO / "libs" / "autobot-sdk-ts" / "src" / "resources"
_BACKEND_API_ROOT = "/api"

# Git-tracked, not `Path.glob` -- glob would also see an untracked scratch
# file sitting in the directory, and the whole point of this enumeration is
# to catch a resource file that ships with no row, not to trust whatever is
# on disk in this checkout right now.
_RESOURCE_FILES = sorted(Path(p).name for p in tracked_paths(_REPO, "libs/autobot-sdk-ts/src/resources/*.ts"))

_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")


def _normalize_path(path: str) -> str:
    """Blank every ``{...}`` placeholder so two paths naming the same route
    compare equal regardless of the parameter's spelling on either side
    (FastAPI's ``session_id`` vs. the TS source's ``sessionId``)."""
    return _PLACEHOLDER_RE.sub("{}", path)


@dataclass(frozen=True)
class TsRequest:
    """One expected request. ``path_template`` is FastAPI's own placeholder
    style (``{agent_id}``), WITHOUT the ``/api`` root -- that's added once
    when comparing against the oracle, matching how the TS client itself
    adds it exactly once (``client.ts``'s ``apiPath()``, #16495).

    ``check_oracle=False`` marks a row whose path is not a single concrete
    route (``setEnabled`` chooses its trailing segment at runtime, so its
    own source has two placeholders where the backend has two literal
    routes) -- covered by its own dedicated test instead of the generic
    per-row oracle lookup.
    """

    file: str
    method: str
    verb: str
    path_template: str
    query_params: frozenset[str] = frozenset()
    # None means "the route declares no field schema to check against" (a
    # bare-object body, the same carve-out sdk_request_body_test.py makes
    # for the Python SDK's identical add_text call).
    body_fields: frozenset[str] | None = frozenset()
    check_oracle: bool = True


TS_SDK_REQUESTS: tuple[TsRequest, ...] = (
    TsRequest("sessions.ts", "list", "GET", "/chat/sessions", query_params=frozenset({"scope", "team_id"})),
    TsRequest("sessions.ts", "get", "GET", "/chat/sessions/{session_id}", query_params=frozenset({"page", "per_page"})),
    TsRequest("sessions.ts", "create", "POST", "/chat/sessions", body_fields=frozenset({"title", "metadata"})),
    # `update`'s body is a caller-supplied free dict (`fields: Record<string, unknown>`) --
    # there is no fixed field set to pin, the same shape as the Python SDK's
    # `update(self, session_id, **fields)`.
    TsRequest("sessions.ts", "update", "PUT", "/chat/sessions/{session_id}", body_fields=None),
    TsRequest("sessions.ts", "delete", "DELETE", "/chat/sessions/{session_id}"),
    TsRequest("knowledge.ts", "stats", "GET", "/knowledge_base/stats"),
    # add_text's route takes `request: dict` -- a bare object with no declared
    # schema, so there is nothing for the oracle to check field names against
    # (see route_request_bodies's own docstring on this exact route).
    TsRequest("knowledge.ts", "addText", "POST", "/knowledge_base/add_text", body_fields=None),
    TsRequest("knowledge.ts", "search", "POST", "/knowledge_base/search", body_fields=frozenset({"query", "limit"})),
    TsRequest(
        "knowledge.ts",
        "getEntries",
        "GET",
        "/knowledge_base/entries",
        query_params=frozenset({"limit", "cursor", "category"}),
    ),
    TsRequest("analytics.ts", "usage", "GET", "/analytics/usage/statistics"),
    TsRequest("analytics.ts", "performance", "GET", "/analytics/performance/metrics"),
    TsRequest("agents.ts", "health", "GET", "/agent/health/detailed"),
    TsRequest("agents.ts", "getConfig", "GET", "/agent_config/agents/{agent_id}"),
    TsRequest(
        "agents.ts",
        "setModel",
        "POST",
        "/agent_config/agents/{agent_id}/model",
        body_fields=frozenset({"agent_id", "model", "provider"}),
    ),
    # See test_set_enabled_targets_real_enable_and_disable_routes: the real
    # backend has two literal routes (.../enable, .../disable), which this
    # one dynamic-segment source call can't be reduced to for the generic
    # per-row oracle lookup.
    TsRequest(
        "agents.ts", "setEnabled", "POST", "/agent_config/agents/{agent_id}/{enable_or_disable}", check_oracle=False
    ),
    TsRequest("agents.ts", "sendCommand", "POST", "/agent/execute_command", body_fields=frozenset({"command"})),
)


def _read(file: str) -> str:
    path = _SDK_TS_SRC / file
    assert path.is_file(), f"expected TS resource file not found: {path}"
    return path.read_text(encoding="utf-8")


def _method_body(source: str, method: str) -> str:
    """The source text of one class method, brace-counted from its signature
    to its matching close brace -- so a check below can only match a call
    that actually belongs to this method, not a sibling's."""
    # `methodName(` at the start of a method declaration (an optional leading
    # `async `), never a call site: a call is followed by `)` then `;`/`,`,
    # not by a parameter list ending in `: ReturnType {`.
    signature = re.search(rf"(?:^|\n)\s*(?:async\s+)?{re.escape(method)}\s*\([^)]*\)\s*:\s*[^{{]+\{{", source)
    assert signature, f"method `{method}` not found in TS source (expected a `{method}(...): ...{{` declaration)"
    start = signature.end() - 1  # position of the opening brace
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced braces scanning `{method}`'s body")  # pragma: no cover


def _sent_names(body_text: str) -> frozenset[str]:
    """Every field name the method's body sends, gathered from wherever it
    builds the outbound object: an object literal passed inline to
    `this.client.<verb>(...)`, one assigned to a local first
    (`const body = { ... }`, then passed by name -- `setModel`'s shape), and
    any conditional `body["key"] = ...` append (`addText`'s shape). A bare
    identifier shorthand (`{ scope }`) and an explicit `key: value` pair are
    both counted by the key name.

    Deliberately whole-body rather than anchored to the call's own argument
    list: the two building styles above put the field names somewhere else
    in the method, and this is a heuristic scan (repo_tests grep-based
    guard, not an AST), so it looks at every leaf object literal and bracket
    assignment in the method rather than modelling control flow."""
    names: set[str] = set()
    for literal in re.findall(r"\{([^{}]*)\}", body_text):
        names.update(re.findall(r"([A-Za-z_$][\w$]*)\s*(?::|,|$)", literal))
    names.update(re.findall(r"\w+\[[\"']([\w$]+)[\"']\]\s*=(?!=)", body_text))
    return frozenset(names)


def _path_literal(body_text: str) -> str | None:
    """The path string passed as the first argument of
    `this.client.<verb>(...)`, with any `${var}` interpolation replaced by
    `{}` so it lines up with `_normalize_path`'s output for the table side."""
    call = re.search(r"this\.client\.(?:get|post|put|delete)\(\s*[`\"]([^`\"]*)[`\"]", body_text)
    if not call:
        return None
    return re.sub(r"\$\{\w+\}", "{}", call.group(1))


@pytest.mark.parametrize("row", TS_SDK_REQUESTS, ids=lambda r: f"{r.file}::{r.method}:{r.path_template}")
def test_ts_sdk_request_matches_its_own_source(row: TsRequest) -> None:
    """The pinned row is not a guess: the method's actual source really does
    send this verb/path/params. Catches the table drifting from the code,
    the opposite failure mode from the oracle check below."""
    body = _method_body(_read(row.file), row.method)
    assert (
        f".{row.verb.lower()}(" in body.lower()
    ), f"{row.file}::{row.method} does not call this.client.{row.verb.lower()}(...)"
    literal_path = _path_literal(body)
    assert literal_path is not None, f"{row.file}::{row.method} makes no this.client.<verb>(...) call at all"
    assert literal_path == _normalize_path(row.path_template), (
        f"{row.file}::{row.method} sends path {literal_path!r}, " f"table says {_normalize_path(row.path_template)!r}"
    )
    if row.query_params or row.body_fields:
        expected = row.query_params or row.body_fields or frozenset()
        sent = _sent_names(body)
        missing = expected - sent
        assert not missing, f"{row.file}::{row.method} table claims {missing} that its source never sends"


@pytest.mark.parametrize(
    "row",
    [r for r in TS_SDK_REQUESTS if r.check_oracle],
    ids=lambda r: f"{r.file}::{r.method}:{r.path_template}",
)
def test_ts_sdk_request_matches_a_real_backend_route(row: TsRequest, route_query_params, route_request_bodies) -> None:
    """The pinned row also names a route the backend really serves, with
    parameter names it really declares -- the actual defect class #15528
    found (`sessions.list` sending `limit`/`offset` to a route with
    neither)."""
    full_path = f"{_BACKEND_API_ROOT}{row.path_template}"
    key = (row.verb, full_path)

    if row.verb in ("GET", "DELETE"):
        assert key in route_query_params, f"no backend route answers {key} -- {row.file}::{row.method}"
        if row.query_params:
            unknown = row.query_params - route_query_params[key]
            assert not unknown, f"{row.file}::{row.method} sends query params {unknown} the route does not declare"
    else:
        assert key in route_query_params, f"no backend route answers {key} -- {row.file}::{row.method}"
        if key in route_request_bodies:
            # `client.ts` sends `Content-Type: application/json` on every
            # POST/PUT, unconditionally -- the same class of gap #15527 fixed
            # on the route side (a Form field beside a dict body publishes as
            # x-www-form-urlencoded, which no JSON body can satisfy).
            media, declared, _required = route_request_bodies[key]
            assert media == "application/json", (
                f"{row.file}::{row.method} sends application/json to {row.verb} {full_path}, "
                f"which FastAPI publishes as {media!r}"
            )
            if row.body_fields is not None and declared is not None:
                unknown = row.body_fields - declared
                assert not unknown, f"{row.file}::{row.method} sends body fields {unknown} the route does not declare"


def test_set_enabled_targets_real_enable_and_disable_routes(route_query_params) -> None:
    """`setEnabled`'s trailing path segment (`enable`/`disable`) is a runtime
    choice in the TS source, but the backend has two separate literal
    routes -- both must be real, since the source call could resolve to
    either one."""
    for action in ("enable", "disable"):
        key = ("POST", f"{_BACKEND_API_ROOT}/agent_config/agents/{{agent_id}}/{action}")
        assert key in route_query_params, f"no backend route answers {key}"


_METHOD_DECL_RE = re.compile(r"(?:^|\n)\s*(?:async\s+)?([a-zA-Z_$][\w$]*)\s*\([^)]*\)\s*:\s*[^{]+\{")
# The one member on these classes that is not a request-making method.
_NOT_A_REQUEST_METHOD = frozenset({"constructor"})


@pytest.mark.parametrize("ts_file", _RESOURCE_FILES)
def test_every_resource_method_has_a_pinned_row(ts_file: str) -> None:
    """A new method shipping on one of these four classes with no row in
    TS_SDK_REQUESTS is exactly what let `agents.setModel`/`setEnabled` not
    exist on the TS side while the Python SDK had them (#15528) -- absence
    is invisible to a check that only walks pinned rows."""
    source = _read(ts_file)
    declared = {m for m in _METHOD_DECL_RE.findall(source) if m not in _NOT_A_REQUEST_METHOD}
    assert declared, f"{ts_file}: found zero method declarations -- the scan itself is broken"
    pinned = {row.method for row in TS_SDK_REQUESTS if row.file == ts_file}
    missing = declared - pinned
    assert not missing, f"{ts_file} declares {missing} with no row in TS_SDK_REQUESTS"


def test_the_table_covers_every_resource_file_that_exists() -> None:
    on_disk = set(_RESOURCE_FILES)
    pinned = {row.file for row in TS_SDK_REQUESTS}
    assert on_disk == pinned, (
        f"TS_SDK_REQUESTS and libs/autobot-sdk-ts/src/resources/ disagree: "
        f"on disk but unpinned {on_disk - pinned}, pinned but missing on disk {pinned - on_disk}"
    )
    assert len(TS_SDK_REQUESTS) >= 15, "the table shrank well below its filed size -- check nothing was dropped"


def test_a_mutation_the_oracle_should_catch_is_actually_caught(route_query_params) -> None:
    """Mutation proof (mirrors sdk_request_body_test.py's own): a row
    claiming a query parameter no real route declares must fail the
    oracle check, not pass it silently."""
    bogus = TsRequest("sessions.ts", "list", "GET", "/chat/sessions", query_params=frozenset({"not_a_real_param"}))
    key = (bogus.verb, f"{_BACKEND_API_ROOT}{bogus.path_template}")
    assert key in route_query_params
    unknown = bogus.query_params - route_query_params[key]
    assert unknown, "the mutation was supposed to name a parameter the route does not declare, but it does"


def test_a_mutation_the_source_check_should_catch_is_actually_caught() -> None:
    """Mutation proof for the source-side comparison: a row naming a path
    the method's real source does not send must fail, not pass."""
    body = _method_body(_read("analytics.ts"), "usage")
    literal_path = _path_literal(body)
    assert literal_path != _normalize_path(
        "/analytics/usage"
    ), "the mutation was supposed to name a path the method's source does not actually send, but it does"
