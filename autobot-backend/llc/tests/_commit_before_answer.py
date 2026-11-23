# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Measuring instruments for the commit-before-answer guard (#21332).

Owner ruling (2026-11-21): every Company OS write route commits before it answers, so a 2xx always means
committed. The mechanism is ONE dependency (`llc.deps.SESSION_DEP`: `get_session` resolved with FastAPI's
`scope="function"`), and this module reads the real route graph to prove every route uses it:

* `llc_write_routes`        the write `APIRoute`s of the real, aggregated `llc.api.router` (population G2 walks)
* `source_write_routes`     the same population derived from the decorators in source, a second way (the floor)
* `session_violations`      a route's dependant tree, as FastAPI resolved it: every session node must be
                            `get_session` with scope `function` (`Annotated`, aliases and sub-dependencies are
                            all one shape in that graph)
* `sessionless_routes`      write routes with no session node, compared to `OWN_SESSION_HANDLERS` exactly (G3)
* `swallowed_failures`      AST rule G4: no `except` that rolls back or catches a failing commit and then falls
                            through to a normal return
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from autobot_shared.api_routing.router_routes import effective_routes
from autobot_shared.testfile_names import is_test_filename
from llc.deps import get_session
from user_management.database import get_async_session

LLC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LLC_ROOT.parents[1]
API_DIR = LLC_ROOT / "api"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_DECORATOR_NAMES = frozenset(name.lower() for name in WRITE_METHODS)
#: Every callable that provides a request database session to a route.
SESSION_PROVIDERS = (get_session, get_async_session)

#: Write handlers with no request session: each opens its own session and commits before it returns. An exact
#: list (G3): an eleventh handler of this shape fails until it is named here with its reason.
_AGENT_API = "autobot-backend/llc/api/agent_api.py"
_AI_LINES = "autobot-backend/llc/api/ai_lines.py"
_OWN_COMMIT = "opens its own session and commits inside the `async with` before it returns"
_OWN_SERVICE = "calls a service that opens its own session and commits (`ApprovalGateService.create_approval`)"
OWN_SESSION_HANDLERS: dict[tuple[str, str], str] = {
    (_AGENT_API, "update_work_item_status"): _OWN_COMMIT,
    (_AGENT_API, "ingest_cost_event"): _OWN_COMMIT,
    (_AGENT_API, "post_comment"): _OWN_COMMIT,
    (_AGENT_API, "upload_work_product"): "opens its own session and commits when `session.begin()` exits",
    (_AGENT_API, "report_heartbeat"): _OWN_COMMIT,
    (_AGENT_API, "agent_upload_attachment"): "`AttachmentService.upload` commits (`_commit_staged`) before it returns",
    (_AGENT_API, "agent_create_wiki_entry"): _OWN_COMMIT,
    (_AI_LINES, "propose_my_change"): _OWN_SERVICE,
    (_AI_LINES, "propose_change"): _OWN_SERVICE,
}


def llc_write_routes(router) -> list[APIRoute]:  # noqa: ANN001
    """The write routes of *router* (the aggregated `llc.api.router`), on either `include_router` shape (#15093)."""
    routes = (mounted.route for mounted in effective_routes(router))
    return [r for r in routes if isinstance(r, APIRoute) and r.methods & WRITE_METHODS]


def route_key(route: APIRoute, root: Path = REPO_ROOT) -> tuple[str, str]:
    """`(path relative to the repo root, handler name)`: how a route is named in the baseline and the exemptions."""
    source = Path(inspect.getsourcefile(inspect.unwrap(route.endpoint)) or "")
    try:
        return source.resolve().relative_to(root).as_posix(), route.endpoint.__name__
    except ValueError:
        return source.as_posix(), route.endpoint.__name__


def _session_nodes(dependant: Dependant) -> list[Dependant]:
    found: list[Dependant] = []
    for sub in dependant.dependencies:
        if sub.call in SESSION_PROVIDERS:
            found.append(sub)
        found.extend(_session_nodes(sub))
    return found


def session_nodes(route: APIRoute) -> list[Dependant]:
    """Every node of the resolved dependency tree (route-, router- and parameter-level) that provides a session."""
    return _session_nodes(route.dependant)


def session_violations(route: APIRoute) -> list[str]:
    """Why *route* does not commit before it answers: a session node that is not the function-scoped `get_session`."""
    problems = []
    for node in session_nodes(route):
        if node.call is not get_session:
            problems.append(f"resolves {getattr(node.call, '__name__', node.call)} (commits after the response)")
        elif node.scope != "function":
            problems.append(f"resolves get_session with scope {node.scope!r}, not 'function'")
    return problems


def sessionless_routes(routes: list[APIRoute], root: Path = REPO_ROOT) -> set[tuple[str, str]]:
    """The routes whose dependency tree holds no session node at all."""
    return {route_key(r, root) for r in routes if not session_nodes(r)}


def violating_files(routes: list[APIRoute], root: Path = REPO_ROOT) -> set[str]:
    """The files that define at least one route with a session violation."""
    return {route_key(r, root)[0] for r in routes if session_violations(r)}


def _decorates_write_route(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _DECORATOR_NAMES
        and isinstance(node.func.value, ast.Name)
    )


def decorated_write_routes(source: str, rel: str) -> set[tuple[str, str]]:
    """`(rel, handler name)` for each function carrying a `@<router>.post|put|patch|delete(...)` decorator."""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_decorates_write_route(d) for d in node.decorator_list):
                found.add((rel, node.name))
    return found


def source_write_routes(api_dir: Path = API_DIR, root: Path = REPO_ROOT) -> set[tuple[str, str]]:
    """The write-route population read from the decorators in `llc/api` source: the second derivation."""
    found: set[tuple[str, str]] = set()
    for path in sorted(api_dir.glob("*.py")):
        if not is_test_filename(path.name):
            found |= decorated_write_routes(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
    return found


def _has_call(nodes: list[ast.stmt], attr: str) -> bool:
    return any(
        isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == attr
        for n in nodes
        for c in ast.walk(n)
    )


def _no_return_names(tree: ast.AST) -> dict[str, bool]:
    """`-> NoReturn` helpers of the module, mapped to whether each is `async` (and so only raises when awaited)."""
    return {
        n.name: isinstance(n, ast.AsyncFunctionDef)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.returns is not None
        and ast.unparse(n.returns) in ("NoReturn", "typing.NoReturn")
    }


def _returns_inside(nodes: list[ast.stmt]) -> bool:
    """A `return` reachable in *nodes*: one in a nested function or class is not the handler's own."""
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Return):
            return True
        if _returns_inside(list(ast.iter_child_nodes(node))):
            return True
    return False


def _ends_by_raising(handler: ast.ExceptHandler, no_return: dict[str, bool]) -> bool:
    """The handler raises on every path: it ends with a raise and has no `return` that leaves before it."""
    if _returns_inside(handler.body):
        return False
    last = handler.body[-1]
    if isinstance(last, ast.Raise):
        return True
    expr = last.value if isinstance(last, ast.Expr) else None
    awaited = isinstance(expr, ast.Await)
    call = expr.value if awaited else expr
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in no_return):
        return False
    return awaited or not no_return[call.func.id]  # an un-awaited async helper only builds a coroutine


def swallowed_failures(source: str, rel: str) -> list[str]:
    """G4: `except` clauses that roll back, or guard a `commit()`, and then let the handler return normally.

    Such a handler turns a failed write into the 2xx the route builds next (`agent_hires.py` did, #21332).
    A clause is fine when it ends by raising, directly or through a `-> NoReturn` helper of the same file.
    """
    tree = ast.parse(source)
    no_return = _no_return_names(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        guards_commit = _has_call(node.body, "commit")
        for handler in node.handlers:
            if (guards_commit or _has_call(handler.body, "rollback")) and not _ends_by_raising(handler, no_return):
                found.append(f"{rel}:{handler.lineno}")
    return sorted(found)


def swallowed_failures_in_tree(api_dir: Path = API_DIR, root: Path = REPO_ROOT) -> list[str]:
    """G4 over every non-test module of `llc/api`."""
    found: list[str] = []
    for path in sorted(api_dir.glob("*.py")):
        if not is_test_filename(path.name):
            found += swallowed_failures(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
    return found


def baseline_additions(current: set[str], base: set[str] | None) -> set[str]:
    """Entries *current* has that the base did not: a shrink-only baseline allows none. `None` = new at this head."""
    return set() if base is None else current - base


def stale_entries(baseline: set[str], violating: set[str]) -> set[str]:
    """Baselined files that no longer violate: they must leave the baseline, not stay as headroom."""
    return baseline - violating
