# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request-**body** coverage for every SDK method that sends one (#15057).

``sdk_request_url_test.py`` pins the path and verb of all 17 requests and
``sdk_request_signature_params_test.py`` pins their query parameters, both
against the backend's own route table. Neither reads a body: the wire capture
they share records only ``request.url.params``, so a method could send an
entirely invented JSON document and every existing guard would pass. That is
how ``knowledge.search`` came to send ``max_results`` -- a name
``SearchRequest`` does not declare -- for as long as it did. Pydantic's default
``extra`` policy is ``ignore``, so the key was dropped without an error and the
caller's ``limit`` silently never applied: the #15119 shape, moved from a query
string into a body where nothing was looking.

The oracle is ``route_request_bodies`` (``conftest.py``), read straight out of
the OpenAPI document FastAPI publishes for the backend's own request models, so
a schema change fails here rather than at a caller (#15057 AC4).

Two things this file checks that a field-name comparison alone would miss:

* **the media type.** ``POST /api/agent/execute_command`` mixes ``Form`` with a
  ``dict`` body parameter, so FastAPI publishes it as
  ``application/x-www-form-urlencoded``. Every SDK method sends JSON. No choice
  of field names makes that request succeed -- see ``_UNSATISFIABLE`` below.
* **the required fields.** A body missing one is a 422 the SDK cannot see until
  it is pointed at a live backend, which is the situation that produced #15053.
"""

from __future__ import annotations

import functools

import pytest

from repo_tests.sdk_request_shared import SDK_REQUESTS
from repo_tests.sdk_request_shared import _bodies as _shared_bodies
from repo_tests.sdk_request_shared import _template_for

# Own mock base URL rather than importing one -- see ``sdk_request_shared.py``'s
# module docstring for why that module cannot hold this literal.
_BASE = "http://backend.test:9999"
_bodies = functools.partial(_shared_bodies, base=_BASE)

_JSON = "application/json"

#: The floor every sweep below is measured against. Seventeen requests, of which
#: these send a body today. A sweep that collapses to fewer has stopped looking
#: at the SDK rather than found it clean, and must fail by name rather than pass
#: over an empty set.
_MIN_BODY_ROWS = 6

#: Rows whose route no client can satisfy, with the issue that will remove them.
#:
#: ``POST /api/agent/execute_command`` declares ``command_data: dict`` alongside
#: ``user_role: str = Form("user")``. The ``Form`` default makes FastAPI read the
#: whole body as form data, and a form field is a string, so ``command_data``
#: can never validate as a dict. Measured against the mounted route, all four
#: candidate shapes answer 422 -- the SDK's own JSON, the field names the route
#: names, that JSON as a form value, and a plain string. There is no body the
#: SDK could send instead, so the entry is a deferral of the backend half, not
#: an exemption: ``test_every_unsatisfiable_row_is_still_unsatisfiable`` fails
#: the moment the route becomes callable, and the entry comes out with it.
_UNSATISFIABLE = {"agents.send_command": "#15057 (backend half deferred: the route is uncallable by any client)"}


def _body_rows() -> list[tuple[str, str, str, str, frozenset[str]]]:
    """``(row name, verb, path, media type, body field names)`` per body-bearing row."""
    rows = []
    for name, call, _verb, _path in SDK_REQUESTS:
        verb, path, media, keys = _bodies(call)[0]
        if media:
            rows.append((name, verb, path, media, keys))
    return rows


@pytest.fixture(scope="module")
def body_rows() -> list[tuple[str, str, str, str, frozenset[str]]]:
    return _body_rows()


def test_the_sweep_still_finds_the_requests_it_claims_to_check(body_rows):
    """Evaluated before every substantive assertion below, so a sweep that
    matched nothing fails by name instead of passing over an empty set.
    """
    assert len(body_rows) >= _MIN_BODY_ROWS, (
        f"FIX THE SWEEP: only {len(body_rows)} of {len(SDK_REQUESTS)} pinned SDK requests were seen to send a "
        f"body, below the floor of {_MIN_BODY_ROWS}. Either the capture broke or bodies stopped being sent; "
        "either way the assertions below would check almost nothing."
    )


def test_every_sdk_body_is_json(body_rows):
    """Every SDK method posts JSON. A route publishing another media type is a
    422 no field-name check can see (#15057).
    """
    assert body_rows, "FIX THE SWEEP: no body-bearing rows"
    wrong = {name: media for name, _verb, _path, media, _keys in body_rows if media != _JSON}
    assert not wrong, f"the SDK sends a non-JSON body for {wrong} -- AutoBotClient.post/put only ever send JSON."


def _oracle_entry(name, verb, path, keys, route_request_bodies):
    """The oracle's row for one request, or ``None`` when there is nothing to check.

    ``AutoBotClient.post`` always sends ``json=body or {}``, so a method with no
    body of its own still puts ``{}`` and a JSON content type on the wire.
    ``/enable`` and ``/disable`` declare no body at all; an empty object reaching
    them is inert, and failing on it would report the client's encoding choice as
    a contract breach. A request carrying **actual keys** to a route that
    declares no body is a different matter and does fail here.
    """
    template = _template_for(path, {p for _v, p in route_request_bodies})
    if template is None:
        assert not keys, (
            f"{name} sends {sorted(keys)} to {verb} {path}, which declares no request body at all. "
            "Every one of those fields is discarded before the handler runs."
        )
        return None
    return route_request_bodies[(verb, template)], template


def test_every_body_field_the_sdk_sends_is_declared_by_the_route(body_rows, route_request_bodies):
    """AC (#15057): the SDK sends what the route reads. A field the request model
    does not declare is dropped by pydantic without an error, so the caller's
    intent silently does not apply -- ``max_results`` did exactly that.
    """
    assert len(body_rows) >= _MIN_BODY_ROWS, "FIX THE SWEEP: body row floor not met"
    for name, verb, path, _media, keys in body_rows:
        if name in _UNSATISFIABLE:
            continue
        entry = _oracle_entry(name, verb, path, keys, route_request_bodies)
        if entry is None:
            continue
        (_route_media, declared, _required), template = entry
        if declared is None:
            continue  # bare-object body: the schema constrains nothing to check against
        unknown = keys - declared
        assert not unknown, (
            f"{name} sends {sorted(unknown)} to {verb} {template}, whose request model declares "
            f"{sorted(declared)}. Pydantic drops an undeclared key without an error, so the caller's "
            "intent silently does not apply."
        )


def test_every_required_body_field_is_sent(body_rows, route_request_bodies):
    """AC (#15057): a body missing a required field is a 422 the SDK cannot see
    until it is pointed at a live backend -- the situation that produced #15053.
    """
    assert len(body_rows) >= _MIN_BODY_ROWS, "FIX THE SWEEP: body row floor not met"
    for name, verb, path, _media, keys in body_rows:
        if name in _UNSATISFIABLE:
            continue
        entry = _oracle_entry(name, verb, path, keys, route_request_bodies)
        if entry is None:
            continue
        (_route_media, _declared, required), template = entry
        missing = required - keys
        assert not missing, f"{name} omits required {sorted(missing)} from {verb} {template}; the route answers 422."


def test_every_sdk_body_matches_the_media_type_the_route_publishes(body_rows, route_request_bodies):
    """AC (#15057): field names are only half the contract. A route published as
    form-encoded rejects a JSON body whatever the field names are.
    """
    assert len(body_rows) >= _MIN_BODY_ROWS, "FIX THE SWEEP: body row floor not met"
    for name, verb, path, media, _keys in body_rows:
        if name in _UNSATISFIABLE:
            continue
        entry = _oracle_entry(name, verb, path, _keys, route_request_bodies)
        if entry is None:
            continue
        (route_media, _declared, _required), template = entry
        assert media == route_media, (
            f"{name} sends {media} to {verb} {template}, which FastAPI publishes as {route_media}."
        )


def test_every_unsatisfiable_row_is_still_unsatisfiable(body_rows, route_request_bodies):
    """A deferral that cannot rot: each ``_UNSATISFIABLE`` entry must still name
    a route no JSON body can satisfy. When the backend half lands, this fails
    and the entry comes out with it rather than quietly exempting a fixed route.
    """
    assert _UNSATISFIABLE, "FIX THE SWEEP: the deferral registry is empty; delete it rather than iterating nothing"
    seen = {name for name, _verb, _path, _media, _keys in body_rows}
    for name, reason in _UNSATISFIABLE.items():
        assert name in seen, f"{name} no longer sends a body at all; drop its {reason} entry."
        verb, path, _media, _keys = next((v, p, m, k) for n, v, p, m, k in body_rows if n == name)  # noqa: B007
        (route_media, _declared, _required), template = _oracle_entry(name, verb, path, _keys, route_request_bodies)
        assert route_media != _JSON, (
            f"{verb} {template} now publishes {route_media}: it is satisfiable, so {name} must be fixed "
            f"and its entry ({reason}) removed from _UNSATISFIABLE."
        )


def test_the_search_route_still_declares_the_offset_defaults_publishes(route_request_bodies):
    """#15170's decision, pinned to the code it rests on.

    ``autobot_sdk.defaults.DEFAULT_OFFSET`` is kept because the search route the
    SDK already calls declares ``offset`` on its request model. If that stops
    being true the docstring becomes the same kind of stale claim it replaced,
    so it fails here instead.
    """
    entry = route_request_bodies.get(("POST", "/api/knowledge_base/search"))
    assert entry is not None, "FIX THE SWEEP: the oracle no longer knows POST /api/knowledge_base/search"
    _media, declared, _required = entry
    assert declared, "FIX THE SWEEP: the search route's request model published no fields"
    assert "offset" in declared, (
        "POST /api/knowledge_base/search no longer declares 'offset'. That declaration is the whole reason "
        "autobot_sdk.defaults.DEFAULT_OFFSET is kept (#15170, option (a)) -- revisit that decision and the "
        "docstring recording it."
    )


def test_the_guard_flags_a_body_field_the_route_does_not_declare(route_request_bodies):
    """Contrast mutation: an undeclared body key must fail, and removing it must
    pass, through the same oracle the real guards use.
    """
    (_media, declared, _required), _template = _oracle_entry(
        "probe", "POST", "/api/knowledge_base/search", frozenset({"query"}), route_request_bodies
    )
    assert declared and "limit" in declared and "max_results" not in declared, (
        "FIX THE SWEEP: the search route's declared fields are not what this mutation stands on"
    )
    assert frozenset({"query", "max_results"}) - declared == frozenset({"max_results"})
    assert not frozenset({"query", "limit"}) - declared


def test_the_guard_does_not_fire_on_a_route_with_a_bare_object_body(route_request_bodies):
    """``add_text`` takes ``request: dict``: FastAPI publishes no properties, so
    the oracle reports ``None`` and the field check stands down rather than
    calling every key it sends undeclared.
    """
    entry = route_request_bodies.get(("POST", "/api/knowledge_base/add_text"))
    assert entry is not None, "FIX THE SWEEP: the oracle no longer knows POST /api/knowledge_base/add_text"
    _media, declared, _required = entry
    assert declared is None, "add_text now publishes a typed request model -- tighten this guard to check it."
