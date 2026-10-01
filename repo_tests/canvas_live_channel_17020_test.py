# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every canvas write announces itself, and it does so on a channel (#17020).

`useCanvasWebSocket` opened `/api/canvas/{id}/ws`, which the backend never
served. `get_canvas_cell_event` -- the builder written for that event -- had
**zero callers**, as did `register_canvas_streaming_task` and its unregister
pair. `CanvasView` did `onMounted(loadCanvas)` and nothing else. So a feature
called "Live Canvas" loaded once and received nothing, for months.

WHAT MADE IT LOOK WIRED. `_format_canvas_cell` sits registered in
`MESSAGE_TYPE_FORMATTERS` under the key `"canvas_cell"`. A registration is not
a call. Every reader who checked for the name found it, in a dispatch map, and
stopped -- which is why this file asserts CALL SITES rather than the presence
of names.

TWO PROPERTIES, BOTH BY AST, NEITHER BY GREP:

1. Each route that mutates a cell publishes, and publishes AFTER its commit.
   Before the commit would announce a write a rollback discards, and inside the
   persistence step would make delivery its side effect -- EVENT_STATE_DOCTRINE
   principle 4.
2. No new WebSocket route appears on the canvas router. Principle 5 is
   "channels, not routes", and principle 1 names three parallel delivery
   systems as a state this codebase has already been in. The fix for an
   unserved bespoke socket must not be to serve it.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

_CANVAS_API = repo_root() / "autobot-backend" / "api" / "canvas.py"
_CANVAS_EVENTS = repo_root() / "autobot-backend" / "canvas" / "events.py"
_MANAGER = repo_root() / "autobot-backend" / "live_event_manager.py"
_LIVE_EVENTS = repo_root() / "autobot-backend" / "api" / "live_events.py"

#: The handlers that write cell content. Discovered by decorator below rather
#: than trusted from this list -- the list is what the discovery must AGREE
#: with, so a new mutating route makes this fail rather than slip through.
_MUTATING_ROUTES = {"put_canvas", "add_cell", "transition_cell"}

_PUBLISH_CALL = "_publish_cell"
_COMMIT_ATTR = "commit"


def _module(path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _functions(tree: ast.Module) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))}


def route_handlers(tree: ast.Module) -> dict[str, str]:
    """``{handler name: http method}`` for every ``@router.<method>`` in the module."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            func = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "router":
                    found[node.name] = func.attr
    return found


def call_names(node: ast.AST) -> list[str]:
    """Names of every call inside *node*, attribute calls by their attribute."""
    names: list[str] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if isinstance(func, ast.Attribute):
            names.append(func.attr)
        elif isinstance(func, ast.Name):
            names.append(func.id)
    return names


def _first_index(names: list[str], wanted: str) -> int:
    return names.index(wanted) if wanted in names else -1


# --------------------------------------------------------------------------
# Contrast pair for the ordering detector -- synthetic sources, no real paths
# --------------------------------------------------------------------------

_PUBLISHES_AFTER_COMMIT = """
async def handler():
    await session.commit()
    await _publish_cell(canvas_id, cell)
"""

_PUBLISHES_BEFORE_COMMIT = """
async def handler():
    await _publish_cell(canvas_id, cell)
    await session.commit()
"""

_NEVER_PUBLISHES = """
async def handler():
    await session.commit()
    return CellOut()
"""


def _ordering(source: str) -> tuple[int, int]:
    names = call_names(_functions(ast.parse(source))["handler"])
    return _first_index(names, _COMMIT_ATTR), _first_index(names, _PUBLISH_CALL)


def test_the_ordering_detector_tells_the_three_shapes_apart() -> None:
    commit_at, publish_at = _ordering(_PUBLISHES_AFTER_COMMIT)
    assert commit_at >= 0 and publish_at > commit_at

    commit_at, publish_at = _ordering(_PUBLISHES_BEFORE_COMMIT)
    assert publish_at >= 0 and publish_at < commit_at

    commit_at, publish_at = _ordering(_NEVER_PUBLISHES)
    assert commit_at >= 0 and publish_at == -1


# --------------------------------------------------------------------------
# The properties
# --------------------------------------------------------------------------


def test_the_mutating_routes_are_the_ones_this_file_names() -> None:
    """Discovery must agree with the list, so a new writing route fails here."""
    handlers = route_handlers(_module(_CANVAS_API))
    writing = {name for name, method in handlers.items() if method in {"put", "post", "patch"}}
    # `export_canvas` is a POST that writes nothing.
    writing.discard("export_canvas")
    assert writing == _MUTATING_ROUTES, (
        f"the set of writing canvas routes changed: {sorted(writing)} against "
        f"{sorted(_MUTATING_ROUTES)}. A new one must publish too -- add it here "
        f"and give it a publish, rather than widening this set alone"
    )


@pytest.mark.parametrize("handler_name", sorted(_MUTATING_ROUTES))
def test_each_mutating_route_publishes_after_its_commit(handler_name: str) -> None:
    handler = _functions(_module(_CANVAS_API))[handler_name]
    names = call_names(handler)
    commit_at = _first_index(names, _COMMIT_ATTR)
    publish_at = _first_index(names, _PUBLISH_CALL)

    assert commit_at >= 0, f"{handler_name}: no commit found -- this test's assumption broke"
    assert publish_at >= 0, (
        f"{handler_name} writes a cell and never calls {_PUBLISH_CALL}. A write no "
        f"subscriber hears is what made Live Canvas load-once (#17020)"
    )
    assert publish_at > commit_at, (
        f"{handler_name} publishes before it commits -- a rollback would leave "
        f"subscribers holding a change that never happened (doctrine principle 4)"
    )


def test_the_canvas_router_grows_no_websocket_route() -> None:
    """Principle 5: channels, not routes. The unserved socket must not be served."""
    methods = set(route_handlers(_module(_CANVAS_API)).values())
    assert "websocket" not in methods, (
        "a @router.websocket appeared on the canvas router. EVENT_STATE_DOCTRINE "
        "principle 5 puts new event types in the channel grammar, and principle 1 "
        "names three parallel delivery systems as a state this codebase has already "
        "been in. Publish on `canvas:{id}` instead"
    )


def test_the_canvas_prefix_is_a_valid_channel() -> None:
    source = _MANAGER.read_text(encoding="utf-8")
    tree = _module(_MANAGER)
    prefixes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_VALID_PREFIXES" for t in node.targets
        ):
            prefixes = {
                element.value
                for element in getattr(node.value, "elts", [])
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    assert prefixes, "could not read _VALID_PREFIXES -- this test stopped seeing its subject"
    assert "canvas" in prefixes, (
        f"`canvas` is not an accepted channel prefix ({sorted(prefixes)}), so every "
        f"subscribe to `canvas:{{id}}` is refused and the publisher reaches nobody"
    )
    assert "canvas" in source  # the docstring's channel list, kept honest


def test_the_canvas_channel_is_authorized_and_not_left_open() -> None:
    """Fail closed on channel authorization is a rule with teeth in the doctrine."""
    tree = _module(_LIVE_EVENTS)
    functions = _functions(tree)
    assert "_authorize_canvas_channel" in functions, (
        "`canvas:` has no authorizer. An unowned resource must be a denial, not an "
        "absence of restriction -- a canvas channel with no check would let any "
        "authenticated client read any user's canvas"
    )
    authorizer = functions["_authorize_canvas_channel"]

    dispatcher = functions["_authorize_channel"]
    assert "_authorize_canvas_channel" in call_names(dispatcher), (
        "`_authorize_canvas_channel` exists but `_authorize_channel` never calls it "
        "-- a registered-but-uncalled check is exactly the shape #17020 is about"
    )

    # The authorizer must have an `except` that returns False, not one that
    # passes: a raising lookup has to deny.
    handlers = [n for n in ast.walk(authorizer) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "_authorize_canvas_channel has no except branch -- a raising lookup would propagate"
    returns_false = [
        n
        for handler in handlers
        for n in ast.walk(handler)
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and n.value.value is False
    ]
    assert returns_false, "_authorize_canvas_channel's except branch does not return False -- it must fail closed"


def test_the_publisher_does_not_persist_the_notification() -> None:
    """The durable fact is the cell row; the event is the notification (principle 2)."""
    source = _CANVAS_EVENTS.read_text(encoding="utf-8")
    assert "PersistStrategy.NONE" in source, (
        "canvas.events no longer publishes with PersistStrategy.NONE. If that is "
        "deliberate, the doctrine's replay question needs answering in the issue: a "
        "persisted event that duplicates a row a client can re-GET is double storage"
    )
