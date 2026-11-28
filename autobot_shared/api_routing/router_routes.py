# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one way to read the routes an ``APIRouter`` actually carries (#15093).

``fastapi>=0.139`` changed ``include_router`` from *copy the child's routes onto
me* to *record that I include this child*. The parent's ``routes`` list then
holds an opaque wrapper — its ``path`` is ``None``, it has no ``methods``, and
the real routes live on ``wrapper.original_router.routes``. Below 0.139 the same
call flattens eagerly and ``routes`` holds the real objects directly.

Both shapes can exist in this project at once: CI resolves the ``fastapi`` floor
declared in ``constraints/shared.txt`` (deferred shape) while a development checkout
may resolve lower (#15091, #22135). Code written for either one alone is wrong on the other, and wrong in
the worst possible direction: an ``hasattr``-guarded walk over the deferred shape
does not raise, it silently finds **nothing**, and a test asserting over nothing
passes.

Four files had already worked this out privately, each with its own copy and its
own gaps (``llc/tests/test_roles_routes_registered.py``,
``api/codebase_analytics/endpoints/impact_endpoint_test.py``,
``api/terminal_router_dependency_wiring_test.py``,
``api/self_capabilities_integration_test.py``). This module replaces those copies;
``repo_tests/router_routes_traversal_test.py`` fails when a fifth one appears.

## What this can and cannot tell you

**Can**, on every version: the set of real route objects a router carries,
their handlers, their ``dependant``, their ``methods``, and their path *as the
route itself declares it* — which already includes any prefix given to the
child's own ``APIRouter(prefix=...)`` constructor, because FastAPI applies that
at decoration time.

**Can too**, on the deferred shape: a prefix passed to the ``include_router``
call, read from the wrapper's ``include_context.prefix`` (#17325).

**Cannot**, on the deferred shape: dependencies passed to the ``include_router``
call, and a prefix on any wrapper that carries no ``include_context``. Nothing on the wrapper is
guaranteed to expose them. Rather than guess, every :class:`MountedRoute`
carries :attr:`MountedRoute.prefix_complete`; when it is ``False`` at least one
inclusion hop above that route hid its prefix and :attr:`MountedRoute.path` is
short by an unknown amount. Callers that need the *served* path must go through
``fastapi.openapi.utils.get_openapi(routes=app.routes)`` on a mounted app, which
is FastAPI's own supported view, or assert a gate behaviourally (see
``api/terminal_websocket_route_test.py``). An include-time ``dependencies=`` is
invisible for the same reason, which is why gates belong on the child router's
own constructor (``api/terminal_tools.py``) where they are readable everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Iterator, List, Optional, Set, Tuple

from starlette.routing import Match

__all__ = [
    "MatchedRoute",
    "MountedRoute",
    "RouteShapeError",
    "effective_routes",
    "effective_route_count",
    "included_router",
    "matched_route",
    "route_method_paths",
]


def included_router(route: Any) -> Optional[Any]:
    """The child router behind a deferred-inclusion wrapper, else ``None``.

    ``None`` is the answer for a real route object, which is what the eager
    shape yields, so a caller can branch on this alone without knowing which
    FastAPI is installed. The ``routes`` check keeps an unrelated attribute
    named ``original_router`` from being walked as if it were a router.
    """
    original = getattr(route, "original_router", None)
    if original is None or not hasattr(original, "routes"):
        return None
    return original


def _hop_prefix(parent: Any, wrapper: Any) -> Tuple[str, bool]:
    """``(prefix, known)`` to prepend when descending one inclusion hop.

    Two terms, and they behave differently:

    * **The including router's own prefix.** Eager inclusion rewrites it into
      every child path at include time; deferred inclusion leaves it on the
      parent and the child's paths are relative. Adding it exactly when we
      descend into a wrapper is therefore right on both shapes — on the eager
      shape there is no wrapper to descend into, so it is never added twice.
      This is the term that made ``llc/tests/test_roles_routes_registered.py``
      correct in CI and broken locally: it prepended ``llc_router.prefix`` by
      hand, which doubles to ``/llc/llc/...`` the moment inclusion is eager.
    * **The prefix given to the ``include_router`` call.** Readable only if the
      wrapper exposes it. A wrapper that does not is reported as *unknown*
      rather than as empty: the two are different answers, and collapsing them
      is how a path silently loses a segment (#14356 is the same failure on the
      source-parsing side).

    The child router's own ``prefix`` is deliberately not a term here. FastAPI
    applies it at decoration time, so it is already inside every ``route.path``
    beneath the child and adding it would duplicate the segment rather than
    recover anything.
    """
    # fastapi>=0.139's wrapper records the whole hop on ``include_context.prefix`` -- the including router's own
    # prefix AND the include_router() call's, verified against a real two-level nesting (#17325). Preferred
    # over the bare ``prefix`` below, which no real wrapper carries.
    recorded = getattr(getattr(wrapper, "include_context", None), "prefix", None)
    if isinstance(recorded, str):
        return recorded, True
    own = getattr(parent, "prefix", "") or ""
    hop = getattr(wrapper, "prefix", None)
    if isinstance(hop, str):
        return f"{own}{hop}", True
    return own, False


@dataclass(frozen=True)
class MountedRoute:
    """One real route, plus how much of its mount path could be recovered."""

    route: Any
    #: Include-time prefixes above this route that introspection could read.
    known_prefix: str = ""
    #: ``False`` when some inclusion hop above this route hid its prefix, so
    #: :attr:`path` is short by an unknown amount. Always ``True`` on the eager
    #: shape, where the prefix is already inside ``route.path``.
    prefix_complete: bool = True

    @property
    def path(self) -> str:
        """The route's path with every recovered prefix applied."""
        return f"{self.known_prefix}{getattr(self.route, 'path', '') or ''}"

    @property
    def methods(self) -> FrozenSet[str]:
        """HTTP methods, empty for a WebSocket route rather than ``None``."""
        return frozenset(getattr(self.route, "methods", None) or ())


def _walk(container: Any, prefix: str, complete: bool, seen: Set[int]) -> Iterator[MountedRoute]:
    if id(container) in seen:  # a router included into its own subtree
        return
    seen = seen | {id(container)}
    for route in getattr(container, "routes", None) or ():
        child = included_router(route)
        if child is None:
            yield MountedRoute(route=route, known_prefix=prefix, prefix_complete=complete)
            continue
        hop, known = _hop_prefix(container, route)
        yield from _walk(child, prefix + hop, complete and known, seen)


def effective_routes(container: Any) -> List[MountedRoute]:
    """Every real route reachable from *container*, on either FastAPI shape.

    *container* may be an ``APIRouter`` or a ``FastAPI`` app; mounting an app
    defers exactly the same way, so both are walked identically.
    """
    return list(_walk(container, "", True, set()))


def effective_route_count(container: Any) -> int:
    """How many real routes *container* serves.

    ``len(container.routes)`` is not this number on the deferred shape: it
    counts one entry per ``include_router`` **call**, so it does not move when
    an endpoint is added inside an already-included router. Anything using a
    route count as a change signal has to use this instead or it will not
    notice the change it exists to notice.
    """
    return len(effective_routes(container))


def route_method_paths(container: Any) -> Set[Tuple[str, str]]:
    """``(method, path)`` for every reachable route; WebSockets use ``"WEBSOCKET"``.

    Paths are subject to the prefix limit documented at module level. Use
    :func:`effective_routes` when a caller needs to know whether a prefix was
    recoverable.
    """
    found: Set[Tuple[str, str]] = set()
    for mounted in effective_routes(container):
        methods = mounted.methods or frozenset({"WEBSOCKET"})
        found.update((method, mounted.path) for method in methods)
    return found


class RouteShapeError(RuntimeError):
    """FastAPI's deferred-inclusion internals no longer look the way this module reads them.

    Raised instead of returning "no route": a resolver that silently found nothing would
    make every caller treat every route as one that declares nothing, which for an
    authorisation check is the wrong direction to fail quietly.
    """


@dataclass(frozen=True)
class MatchedRoute:
    """The concrete route a request scope resolves to, and the dependency tree that guards it."""

    route: Any
    #: The route's ``dependant`` including router-level and include-time dependencies, or ``None``.
    dependant: Any


def _select(wrapper: Any, scope: dict) -> Tuple[Any, Any]:
    """``(route, effective_context)`` FastAPI's own matching picks inside *wrapper*, or ``(None, None)``.

    Reads the private ``_IncludedRouter._match`` (fastapi>=0.139; the floor in ``constraints/shared.txt``),
    the only place the matched leaf and its include-time-merged dependency tree are both exposed.
    ``autobot_shared/api_routing/router_routes_test.py`` pins its shape.
    """
    select = getattr(wrapper, "_match", None)
    if not callable(select):
        raise RouteShapeError("_IncludedRouter._match is gone; re-derive matched_route() for this FastAPI")
    result = select(scope)
    if not isinstance(result, tuple) or len(result) != 4:
        raise RouteShapeError(f"_IncludedRouter._match returned {type(result).__name__}, expected a 4-tuple")
    match, _child, route, context = result
    if match is not Match.FULL:
        return None, None
    return route, context


def _resolve(route: Any, scope: dict) -> Optional[MatchedRoute]:
    context = None
    while included_router(route) is not None:
        route, context = _select(route, scope)
        if route is None:
            return None
    effective = getattr(context, "dependant", None)
    leaf = getattr(context, "original_route", None) or route
    return MatchedRoute(route=leaf, dependant=effective or getattr(leaf, "dependant", None))


def matched_route(container: Any, scope: dict) -> Optional[MatchedRoute]:
    """The concrete route *scope* fully matches in *container*, through nested and deferred includes.

    *container* is a ``FastAPI`` app or ``APIRouter``. On the eager shape the first fully matching
    entry is already the real route; on the deferred shape it is a wrapper and the leaf is found by
    descending with FastAPI's own matcher, so ``dependant`` carries every router-level and
    ``include_router(dependencies=...)`` dependency. ``None`` when nothing fully matches (a mount
    or a partial match is not a route).
    """
    for route in getattr(container, "routes", None) or ():
        if route.matches(scope)[0] is Match.FULL:
            return _resolve(route, scope)
    return None
