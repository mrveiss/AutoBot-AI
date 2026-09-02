# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every API path in ``docs/sdk/*.md`` names a route the backend serves (#15141).

``repo_tests/sdk_request_url_test.py`` does this for the URLs the SDK itself
builds. The guides that introduce the SDK had nothing checking them at all, so
they drifted from both the SDK and the API: the Python guide told a reader the
package was unpublished and then to install it eight lines later, and both
guides sent a ``?limit=`` to a route that declares no query parameters.

Two deliberate properties, because a guard over documentation fails in ways a
guard over code does not:

* **Only fenced code blocks are read.** Prose that merely names a route, a
  symbol or a package must not fail this guard -- documentation is allowed to
  discuss a thing without calling it. ``test_prose_naming_a_route_is_not_a
  _finding`` pins that.
* **The extraction has a floor.** A regex that stops matching is the failure
  mode this guard exists to prevent: it would go green over an empty set while
  every path in the guides rotted. The floor is asserted before any path is
  compared, and names itself when it trips.

The oracle is the same static route table shape the api-wiring gate uses --
registry mount prefix + the module's own ``APIRouter`` prefix + the path on each
``@router.<verb>`` decorator -- built from
``autobot_shared.api_routing.router_prefixes``, which owns both grammars so this
file and that gate cannot disagree about which routes exist. It is validated
against ``SDK_REQUESTS``: every URL the SDK is pinned to build must appear in it,
so an oracle that has stopped resolving routes fails here rather than passing
everything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from autobot_shared.api_routing import router_prefixes as routing
from repo_tests.sdk_request_shared import _BACKEND, _BACKEND_API_ROOT, SDK_REQUESTS, _template_for

_DOCS = Path(__file__).resolve().parents[1] / "docs" / "sdk"

#: A path literal inside a code fence: preceded by a quote, a backtick, or the
#: ``}`` that closes an f-string / template interpolation (``f"{BASE_URL}/auth/login"``).
#: The query string is captured separately so ``?limit=`` is checked rather than
#: quietly trimmed off the path.
_PATH_RE = re.compile(r"""(?<=["'`}])(/(?:api/)?[a-z_][A-Za-z0-9_/{}$().:-]*)(\?[^"'`\s]*)?""")
_FENCE_RE = re.compile(r"^\s*```")
_PARAM_RE = re.compile(r"\$?\{[^}]*\}")
_QUERY_NAME_RE = re.compile(r"[?&]([A-Za-z_][A-Za-z0-9_]*)=")

#: Floors, asserted before any comparison. Measured today: 24 distinct paths
#: across the three guides, and 2160 routes in the oracle. Set well below both
#: so ordinary editing does not trip them, and far above zero so a collapsed
#: sweep cannot pass.
_MIN_DOC_PATHS = 15
_MIN_ROUTES = 500


def _normalise(path: str) -> str:
    """``/chat/sessions/${sessionId}`` and ``/chat/sessions/{session_id}`` alike
    become ``/chat/sessions/{}``, so a documented path is compared to a route
    template by shape rather than by the name a doc gave the parameter.
    """
    under_api = path if path.startswith(f"{_BACKEND_API_ROOT}/") else f"{_BACKEND_API_ROOT}{path}"
    return _PARAM_RE.sub("{}", under_api).rstrip("/") or "/"


def _documented_paths() -> list[tuple[str, int, str, tuple[str, ...]]]:
    """``(file name, line, normalised path, query parameter names)`` per literal
    inside a fenced code block in ``docs/sdk/*.md``.
    """
    found: list[tuple[str, int, str, tuple[str, ...]]] = []
    for doc in sorted(_DOCS.glob("*.md")):
        in_fence = False
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            for match in _PATH_RE.finditer(line):
                query = tuple(_QUERY_NAME_RE.findall(match.group(2) or ""))
                found.append((doc.name, number, _normalise(match.group(1)), query))
    return found


def _route_table() -> set[str]:
    """Normalised paths the backend serves, from the router registry outwards."""
    entries = routing.registry_entries(_BACKEND / "initialization" / "router_registry")
    assert entries, "the router registry parsed no entries -- the oracle would be empty"
    table: set[str] = set()
    for file, mount in routing.resolve_registry_targets(_BACKEND, entries).items():
        source = file.read_text(encoding="utf-8", errors="ignore")
        own = routing.file_router_prefix(source)
        for _verb, path in routing.ROUTE_DECORATOR_RE.findall(source):
            table.add(_normalise(f"{_BACKEND_API_ROOT}{mount}{own}{path}"))
    return table


@pytest.fixture(scope="module")
def documented_paths() -> list[tuple[str, int, str, tuple[str, ...]]]:
    return _documented_paths()


@pytest.fixture(scope="module")
def route_table() -> set[str]:
    return _route_table()


def test_the_sweep_still_extracts_the_paths_it_claims_to_check(documented_paths):
    """Evaluated before every comparison below: a regex that stopped matching
    would otherwise take this whole file green over an empty set (#15087).
    """
    assert len(documented_paths) >= _MIN_DOC_PATHS, (
        f"FIX THE SWEEP: only {len(documented_paths)} API paths were extracted from "
        f"{_DOCS.name}/*.md, below the floor of {_MIN_DOC_PATHS}. Either the guides lost their "
        "examples or the extraction broke; either way nothing below is being checked."
    )


def test_the_route_oracle_still_resolves_routes(route_table):
    """The oracle's own floor. A registry that stops parsing, or a decorator
    grammar that stops matching, must fail by name rather than declare every
    documented path missing (or, with the comparison inverted, present).
    """
    assert len(route_table) >= _MIN_ROUTES, (
        f"FIX THE SWEEP: the route oracle resolved {len(route_table)} routes, below the floor of "
        f"{_MIN_ROUTES}. The registry or the decorator grammar stopped working."
    )


def test_the_oracle_serves_every_url_the_sdk_is_pinned_to_build(route_table):
    """Anchors the oracle to a table that is independently checked. If a route
    the SDK provably reaches is absent here, this file's verdict on the guides
    is worthless, and that shows up as this failing rather than as a documented
    path being called imaginary.
    """
    assert route_table, "FIX THE SWEEP: the route oracle is empty"
    # SDK_REQUESTS pins concrete URLs (``/api/chat/sessions/s1``); the oracle
    # holds templates. ``_template_for`` is the same resolver the URL guard uses.
    missing = sorted({path for _name, _call, _verb, path in SDK_REQUESTS if _template_for(path, route_table) is None})
    assert not missing, (
        f"the oracle does not serve {missing}, which sdk_request_url_test.py pins the SDK to request. "
        "The oracle is wrong, not the docs."
    )


def test_every_documented_path_names_a_route_the_backend_serves(documented_paths, route_table):
    """AC (#15141): a path in a guide is a route or it is a defect. FastAPI
    answers 404, and a reader following the guide has no way to tell the guide
    from the API.
    """
    assert len(documented_paths) >= _MIN_DOC_PATHS, "FIX THE SWEEP: documented-path floor not met"
    assert len(route_table) >= _MIN_ROUTES, "FIX THE SWEEP: route-oracle floor not met"
    unknown = [
        f"{name}:{line} -> {path}" for name, line, path, _query in documented_paths if path not in route_table
    ]
    assert not unknown, "docs/sdk names paths the backend does not serve:\n  " + "\n  ".join(sorted(unknown))


def test_no_documented_example_sends_a_query_parameter_to_the_chats_list(documented_paths):
    """AC (#15141): ``GET /api/chats`` (``api/chat.py``'s ``list_chats``)
    declares no query parameters at all, so a documented ``?limit=`` is dropped
    by FastAPI and the reader's paging silently does not apply -- the #15119
    shape, in a guide instead of the SDK.

    Pinned by name because that is the occurrence both guides carried. It is not
    a general query-parameter check: that needs a signature oracle over every
    router the guides touch, and is filed rather than half-built here.
    """
    offenders = [
        f"{name}:{line} -> {path}?{'&'.join(query)}"
        for name, line, path, query in documented_paths
        if query and path == f"{_BACKEND_API_ROOT}/chats"
    ]
    assert not offenders, (
        "GET /api/chats takes no query parameters; these examples send some:\n  " + "\n  ".join(offenders)
    )


def test_prose_naming_a_route_is_not_a_finding(tmp_path, monkeypatch):
    """Contrast: a guide may discuss ``/nonexistent/route`` in prose without
    failing. Only fenced code -- what a reader copies and runs -- is read.
    """
    doc = tmp_path / "prose.md"
    doc.write_text(
        'Historically the API served `/nonexistent/route` and "/also_gone/here".\n'
        "```python\n"
        'client.get("/chat/sessions")\n'
        "```\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("repo_tests.sdk_docs_paths_test._DOCS", tmp_path)
    extracted = {path for _name, _line, path, _query in _documented_paths()}
    assert extracted == {f"{_BACKEND_API_ROOT}/chat/sessions"}, (
        f"prose leaked into the extraction, or the fenced path was missed: {sorted(extracted)}"
    )


def test_a_documented_path_that_stops_existing_is_caught(route_table):
    """Contrast mutation: the comparison this file rests on must reject a path
    the oracle does not serve and accept one it does. Driven through the real
    ``_normalise`` and the real oracle, not a re-implementation.
    """
    assert _normalise("/chat/sessions") in route_table
    assert _normalise("/chats") in route_table, (
        "GET /api/chats is served by api/chat.py's list_chats -- if it has gone, the guides that "
        "document it must change with it."
    )
    assert _normalise("/chat/sessions/{session_id}") in route_table
    assert _normalise("/knowledge_base/no_such_route") not in route_table
