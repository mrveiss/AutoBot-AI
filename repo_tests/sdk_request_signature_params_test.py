# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Signature-derived query-parameter coverage (#15187).

Split out of ``sdk_request_url_test.py`` once this section pushed that file
past the 600-line cap (``scripts/check_python_file_size.py``). See that
file's module docstring for the #15119/#15053 background; this one covers
only the gap #15119's own guard left.

That guard (``test_every_query_parameter_the_sdk_sends_exists_on_the_route``,
in ``sdk_request_url_test.py``) only sees what a hand-written ``SDK_REQUESTS``
row happens to pass. ``AutoBotClient.get()`` drops ``None`` values, so a query
parameter defaulting to ``None`` that no row bothers to pass is never on the
wire that guard observes -- and most optional SDK parameters default to
``None``, so that is the common shape, not an edge case.

The tests below force every parameter -- named straight off each resource
method's own signature, independent of what any row does -- to a concrete
value, so it reaches the wire and gets checked whether or not a row
remembers it. A row is still required per parameter: an unexercised one is
itself a failure below, so deriving the set from signatures does not trade
one hole (a parameter no test sees) for another (a parameter this file
claims coverage for but never actually calls through a public API surface).

This does NOT close #15186's class of defect -- a parameter that *does*
exist on the route signature but the handler never applies (``page`` on
``/chat/sessions/{id}``). That is a behavioural gap, not a naming one: the
parameter passes every check here because it is declared, so only a test
that asserts two different values produce two different responses (as
``test_pagination_advances_when_the_cursor_from_one_page_is_passed_to_the_next``
in ``sdk_request_url_test.py`` does for the cursor) can catch it. Recorded
here so nobody assumes this file's coverage extends to that shape.
"""

from __future__ import annotations

import functools
import inspect
import types
import typing
from typing import Any

import pytest
from autobot_sdk import resources

from repo_tests.sdk_request_shared import SDK_REQUESTS, _RESOURCE_ATTRS, _assert_sent_params_are_accepted
from repo_tests.sdk_request_shared import _urls as _shared_urls

# Own mock base URL rather than importing one: sdk_request_shared.py cannot
# hold this literal (see its module docstring -- the hardcoded-value hook's
# test-file exemption is filename-matched, and that module's name does not
# qualify). Rebinding ``_urls`` to a partial keeps every ``_urls(call)`` call
# site below unchanged.
_BASE = "http://backend.test:9999"
_urls = functools.partial(_shared_urls, base=_BASE)


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
        # Truthy on purpose. Several call sites include an optional argument
        # only under ``if param:``, so an empty dict would be dropped before
        # it reached the wire — the parameter would read as "forced" while
        # never actually being checked, which is the exact blindness this
        # guard exists to remove (#15187 review).
        return {"x": "x"}
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
    ``_assert_sent_params_are_accepted`` pipeline the real guards use --
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
