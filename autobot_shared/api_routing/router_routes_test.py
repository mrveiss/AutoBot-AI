# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The traversal must give the same answer on both FastAPI shapes (#15093).

Two halves, deliberately:

* **Synthetic** — hand-built stand-ins for the eager and the deferred shape.
  These run identically everywhere, so the helper's contract is pinned on a
  checkout that resolves either FastAPI (#15091 — a development box resolves
  0.135.2, CI pins 0.141.1, and a local pass therefore carries no information
  about the deferred behaviour).
* **Real FastAPI** — the same properties asserted against whatever version is
  installed, phrased so that they hold on both. These are what make the
  synthetic stand-ins evidence rather than a story: if the real wrapper ever
  stops being named ``original_router`` the real half fails while the synthetic
  half still passes.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, FastAPI

from autobot_shared.api_routing.router_routes import (
    MountedRoute,
    effective_route_count,
    effective_routes,
    included_router,
    route_method_paths,
)

# --- synthetic shapes -------------------------------------------------------


class _Route:
    """A real route object: what the eager shape leaves in ``routes``."""

    def __init__(self, path: str, methods=("GET",)):
        self.path = path
        self.methods = set(methods)


class _Deferred:
    """The deferred wrapper: no usable ``path``, real routes one level down."""

    path = None

    def __init__(self, child, prefix=None):
        self.original_router = child
        if prefix is not None:
            self.prefix = prefix


class _Router:
    def __init__(self, *routes):
        self.routes: List[object] = list(routes)


def test_eager_shape_is_returned_unchanged():
    router = _Router(_Route("/a"), _Route("/b"))

    assert [m.path for m in effective_routes(router)] == ["/a", "/b"]
    assert all(m.prefix_complete for m in effective_routes(router))


def test_deferred_shape_is_flattened():
    child = _Router(_Route("/leaf"))
    parent = _Router(_Route("/own"), _Deferred(child, prefix=""))

    assert [m.path for m in effective_routes(parent)] == ["/own", "/leaf"]


def test_deferred_nesting_recurses():
    """Inclusion nests; a single-level unwrap is the bug this replaces."""
    leaf = _Router(_Route("/leaf"))
    middle = _Router(_Deferred(leaf, prefix="/mid"))
    parent = _Router(_Deferred(middle, prefix="/top"))

    assert [m.path for m in effective_routes(parent)] == ["/top/mid/leaf"]


def test_an_unreadable_include_prefix_is_reported_not_invented():
    """A wrapper with no ``prefix`` must not be read as *no prefix*.

    Reporting an unknown prefix as ``""`` produces a path that looks served and
    is not — the failure mode #14356 recorded for the source-parsing side of the
    same grammar.
    """
    parent = _Router(_Deferred(_Router(_Route("/leaf"))))

    (mounted,) = effective_routes(parent)
    assert mounted.path == "/leaf"
    assert mounted.prefix_complete is False


def test_a_cycle_terminates():
    router = _Router()
    router.routes.append(_Deferred(router, prefix=""))
    router.routes.append(_Route("/a"))

    assert [m.path for m in effective_routes(router)] == ["/a"]


def test_included_router_ignores_a_lookalike_attribute():
    class _Decoy:
        path = "/x"
        methods = {"GET"}
        original_router = "not a router"

    assert included_router(_Decoy()) is None
    assert [m.path for m in effective_routes(_Router(_Decoy()))] == ["/x"]


def test_websocket_routes_report_a_method():
    class _WS:
        path = "/ws"
        methods = None

    assert route_method_paths(_Router(_WS())) == {("WEBSOCKET", "/ws")}
    assert MountedRoute(route=_WS()).methods == frozenset()


# --- real FastAPI, whichever version is installed ---------------------------


def _child_with(path: str) -> APIRouter:
    child = APIRouter()

    @child.get(path)
    async def _handler():  # pragma: no cover - never called
        return {}

    return child


def test_real_inclusion_is_flattened_on_this_fastapi():
    """The property that fails today without this helper.

    ``len(parent.routes)`` is 1 on both shapes here; what differs is *what* that
    one entry is. The traversal has to yield the leaf either way.
    """
    parent = APIRouter()
    parent.include_router(_child_with("/leaf"))

    paths = [m.path for m in effective_routes(parent)]
    assert paths == ["/leaf"], f"traversal did not reach the included route; got {paths}"


def test_real_constructor_prefix_is_already_in_the_path():
    """A child's own ``APIRouter(prefix=...)`` is applied at decoration time.

    So it must not be added a second time by the traversal. This holds on both
    shapes and is the reason the helper never substitutes ``child.prefix`` for
    an unreadable include-time prefix.
    """
    child = APIRouter(prefix="/own")

    @child.get("/leaf")
    async def _handler():  # pragma: no cover - never called
        return {}

    parent = APIRouter()
    parent.include_router(child)

    assert [m.path for m in effective_routes(parent)] == ["/own/leaf"]


def test_real_including_routers_own_prefix_is_applied_exactly_once():
    """The term that differs between the two shapes, pinned on both.

    Eager inclusion folds the including router's prefix into every child path;
    deferred inclusion leaves it on the parent. Adding it on descent is right
    both times — but only if it is added exactly once, so this fails on the
    ``/parent/parent/leaf`` a double-count would produce just as loudly as on
    the ``/leaf`` that omitting it would produce.
    """
    parent = APIRouter(prefix="/parent")
    parent.include_router(_child_with("/leaf"))

    assert [m.path for m in effective_routes(parent)] == ["/parent/leaf"]


def test_real_include_time_prefix_is_either_recovered_or_flagged():
    """Version-independent by construction, and it records which shape ran.

    On eager inclusion the prefix is rewritten into ``route.path``, so the path
    is complete. On the deferred shape it is recoverable only if the wrapper
    exposes it, and what it exposes might be the hop alone or the whole chain.
    The three-way disjunction below is exactly the set of correct answers;
    anything else — a lost segment claimed as complete, or a doubled one — fails
    here rather than reaching a caller as a path nothing serves.
    """
    parent = APIRouter(prefix="/parent")
    parent.include_router(_child_with("/leaf"), prefix="/pre")

    (mounted,) = effective_routes(parent)
    assert mounted.path == "/parent/pre/leaf" or (not mounted.prefix_complete and mounted.path == "/parent/leaf"), (
        f"path={mounted.path!r} (prefix_complete={mounted.prefix_complete}) is neither the served "
        "path nor an honestly-flagged partial one. A hop was invented, doubled or lost."
    )


def test_real_route_count_is_endpoints_not_include_calls():
    """The property ``len(parent.routes)`` does not have, and cache keys need.

    On the deferred shape ``len(parent.routes)`` counts one entry per
    ``include_router`` **call**, so it reads 1 for a child holding any number of
    endpoints and does not move when one is added inside an already-included
    router. Anything using a route count as a change signal has to use this
    count or it will not notice the change it exists to notice
    (``api/self_capabilities.py``).
    """
    child = _child_with("/one")

    @child.get("/two")
    async def _second():  # pragma: no cover - never called
        return {}

    parent = APIRouter()
    parent.include_router(child)

    assert effective_route_count(parent) == 2, (
        f"traversal counted {effective_route_count(parent)} of 2 endpoints; "
        f"len(parent.routes) is {len(parent.routes)}"
    )


def test_real_app_mount_is_traversable():
    """Mounting an app defers the same way; it is not a workaround for this."""
    app = FastAPI()
    router = APIRouter()
    router.include_router(_child_with("/leaf"))
    app.include_router(router)

    assert "/leaf" in {m.path for m in effective_routes(app)}


def test_real_dependant_survives_the_traversal():
    """Whatever the shape, the object yielded must be the real route.

    Handler-level assertions (auth dependencies, response models) are made on
    these objects; a wrapper reaching a caller would make every such assertion
    vacuous rather than failing it.
    """
    parent = APIRouter()
    parent.include_router(_child_with("/leaf"))

    (mounted,) = effective_routes(parent)
    assert getattr(mounted.route, "dependant", None) is not None
    assert mounted.methods == frozenset({"GET"})


def test_non_vacuity_the_real_half_saw_a_deferred_or_eager_shape():
    """Fails if the real half ever inspects an empty router.

    Every assertion above is over an enumeration; an enumeration that comes back
    empty makes them all pass while verifying nothing (#15087).
    """
    parent = APIRouter()
    parent.include_router(_child_with("/leaf"))

    assert parent.routes, "non-vacuity: include_router left the parent with no entries at all"
    assert effective_routes(parent), "non-vacuity: the traversal reached no routes"


def test_the_installed_fastapi_shape_is_one_of_the_two_known_ones():
    """A third inclusion shape must fail loudly, not be traversed as nothing.

    The helper recognises exactly two: real routes in ``parent.routes`` (eager)
    and a wrapper whose ``original_router`` holds them (deferred). If a future
    FastAPI introduces a third, every traversal here would come back empty and
    every assertion built on one would pass while inspecting nothing — the
    #15087 failure mode, arriving via a dependency bump rather than a bug.
    """
    parent = APIRouter()
    parent.include_router(_child_with("/leaf"))
    (entry,) = parent.routes

    eager = getattr(entry, "path", None) == "/leaf" and included_router(entry) is None
    deferred = included_router(entry) is not None

    assert eager or deferred, (
        "unrecognised include_router shape: parent.routes holds "
        f"{type(entry).__name__}(path={getattr(entry, 'path', None)!r}) with no original_router. "
        "autobot_shared/api_routing/router_routes.py must learn it before anything trusts a traversal."
    )
