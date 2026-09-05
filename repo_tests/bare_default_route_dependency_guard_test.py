# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A route dependency written as a bare default instead of Depends() never runs (#15769).

    async def trigger_cognition_seed(
        request: SeedRequest,
        background_tasks: BackgroundTasks,
        _user=check_admin_permission,      # never called -- FastAPI does not invoke a plain default
    ):

FastAPI only calls a dependency wired through ``Depends(...)``. A bare callable
default *reads* as gated -- the import is present and used, the name sits in
the signature -- but is simply never invoked, so an unauthorised caller gets
the same 200 an authorised one would. #15759 found exactly this on
``POST /cognition-store/seed``. It also defeats
``initialization/router_registry/core_router_auth_guard_test.py`` (#15745):
that guard walks the assembled ``Dependant`` tree, which never contains a
default FastAPI never called, so it reads the router as gated.

WHY THE FIXTURE IS SYNTHETIC, NOT THE LIVE VIOLATION SET
---------------------------------------------------------
The one known instance was fixed in #15759; the live population is zero
(measured below). A guard whose own pass/fail is seeded from that population
would be vacuous today and would break the moment a violation reappears --
the exact trap #15762 records against three other tests built that way. The
contrast pair below is two literal strings this file writes itself, never a
route read out of the tree it also scans.

THE NUMERIC-CONSTANT CASE THIS GUARD MUST NOT FLAG (#15769's own AC)
----------------------------------------------------------------------
``api/knowledge.py:2035`` -- ``limit: int = QueryDefaults.DEFAULT_SEARCH_LIMIT``
-- is a bare ``Attribute`` default with exactly the AST shape of the bug
(``_user=check_admin_permission`` is a bare ``Name``; ``QueryDefaults.
DEFAULT_SEARCH_LIMIT`` is a bare ``Attribute``). Nothing at the AST level
distinguishes "a module-level numeric constant" from "an unwrapped dependency
callable" except the one convention Python already uses to tell them apart:
PEP 8 spells a constant ``UPPER_SNAKE_CASE`` and a callable ``lower_snake_case``.
``_looks_like_constant`` reads exactly that -- the default's terminal
identifier (``.id`` for a ``Name``, ``.attr`` for an ``Attribute``) is
all-uppercase -- and only a default that fails it is a violation. Flagging
``DEFAULT_SEARCH_LIMIT`` would get this guard silenced rather than fixed,
per the issue itself.

REACH, NOT FINDINGS (the vacuity floor)
------------------------------------------
The live violation count is zero either way, so a scanner that silently
parses nothing would print the identical clean line as one that parsed
everything. ``_MIN_EXPECTED_ROUTES_SCANNED`` binds the floor to how many
route functions were actually parsed, not to what they contained -- the same
shape as ``core_router_auth_guard_test.py``'s ``_MIN_EXPECTED_CORE_ROUTERS``.
Measured at 2,867 route functions across every tracked ``.py`` file in the
repository (autobot-backend, autobot-slm-backend, autobot-infrastructure and
the repo root all included, per #15769's own reach); the floor sits
comfortably below that.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO = Path(__file__).resolve().parents[1]

_ROUTE_METHODS = frozenset({"get", "post", "put", "delete", "patch", "websocket", "options", "head"})

# Directories never worth walking into (mirrors
# repo_tests/with_error_handling_single_definition_test.py:134's own list) --
# git ls-files already excludes untracked worktree copies, this is a second,
# defensive filter against the same class of accident.
_SKIP_PARTS = {"node_modules", ".worktrees", "__pycache__", "venv", ".venv"}

# Bound to REACH (route functions actually parsed), not to how many violations
# turn up -- see the module docstring for why the floor is the only thing that
# tells a clean sweep apart from a vacuous one here.
_MIN_EXPECTED_ROUTES_SCANNED = 2500


def _is_route_decorator(node: ast.expr) -> bool:
    """True for ``@x.get(...)``/``@x.post(...)``/etc, whatever ``x`` is named.

    The repo uses dozens of router variable names (``router``, ``admin_router``,
    ``app``, ``fleet_router``, ...), so this matches on the attribute name
    alone, never on the base object.
    """
    target = node.func if isinstance(node, ast.Call) else node
    return isinstance(target, ast.Attribute) and target.attr in _ROUTE_METHODS


def _terminal_identifier(node: ast.expr) -> str | None:
    """The name a bare default resolves to: ``.id`` for a Name, ``.attr`` for an Attribute."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _looks_like_constant(name: str) -> bool:
    """PEP 8's own discriminator: SCREAMING_SNAKE_CASE reads as a constant, not a callable."""
    return name.upper() == name and any(char.isalpha() for char in name)


def _bare_default_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Tuple[str, int]]:
    """(arg name, line) for every parameter whose default is a bare, non-constant Name/Attribute.

    A ``Depends(...)`` default is an ``ast.Call``, never a bare Name/Attribute,
    so it never reaches ``_terminal_identifier`` at all -- this only ever
    flags the shape #15769 describes.
    """
    violations: List[Tuple[str, int]] = []
    positional = func.args.args
    offset = len(positional) - len(func.args.defaults)
    pairs = list(zip(positional[offset:], func.args.defaults))
    pairs += list(zip(func.args.kwonlyargs, func.args.kw_defaults))
    for arg, default in pairs:
        if default is None:
            continue
        name = _terminal_identifier(default)
        if name is not None and not _looks_like_constant(name):
            violations.append((arg.arg, arg.lineno))
    return violations


def _iter_route_functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_route_decorator(dec) for dec in node.decorator_list):
                yield node


def _tracked_python_files() -> List[Path]:
    """Every git-tracked ``.py`` file, wherever it lives.

    #15769 asks for the whole tracked tree (autobot-backend,
    autobot-slm-backend, autobot-infrastructure and the repo root), not one
    directory -- see ``with_error_handling_single_definition_test.py`` for why
    a scan narrower than its own claim is a defect in the guard, not a clean
    result.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    paths = (_REPO / rel for rel in listing.split("\0") if rel.endswith(".py"))
    return [path for path in paths if not _SKIP_PARTS & set(path.relative_to(_REPO).parts)]


def _scan_repo() -> Tuple[int, List[Tuple[Path, str, int]], List[Tuple[Path, str]]]:
    """(routes parsed, violations, unreadable) across every tracked ``.py`` file.

    An unparseable file is recorded, never swallowed into an empty result --
    #15202's precedent for this exact shape of scan.
    """
    routes = 0
    violations: List[Tuple[Path, str, int]] = []
    unreadable: List[Tuple[Path, str]] = []
    for path in _tracked_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError) as failure:
            unreadable.append((path, f"{type(failure).__name__}: {failure}"))
            continue
        for func in _iter_route_functions(tree):
            routes += 1
            for arg_name, lineno in _bare_default_args(func):
                violations.append((path, arg_name, lineno))
    return routes, violations, unreadable


@pytest.fixture(scope="module")
def scan_result() -> Tuple[int, List[Tuple[Path, str, int]], List[Tuple[Path, str]]]:
    return _scan_repo()


class TestScanIsNotVacuous:
    """A guard that silently parses nothing would report a clean sweep too."""

    def test_route_reach_meets_floor(self, scan_result):
        routes, _violations, _unreadable = scan_result
        assert routes >= _MIN_EXPECTED_ROUTES_SCANNED, (
            f"only {routes} route functions were parsed, below the recorded floor of "
            f"{_MIN_EXPECTED_ROUTES_SCANNED} -- every assertion below is vacuous if the "
            "scan itself silently collapsed"
        )

    def test_no_tracked_source_is_unreadable_by_this_guard(self, scan_result):
        _routes, _violations, unreadable = scan_result
        assert (
            not unreadable
        ), f"these tracked sources could not be parsed, so this guard saw NONE of their routes: {unreadable}"


class TestBareDefaultRouteDependencyGuard:
    def test_no_bare_default_route_dependencies(self, scan_result):
        _routes, violations, _unreadable = scan_result
        assert not violations, (
            f"{violations} -- each default reads as a gate in the route signature but is "
            "never called by FastAPI. Wire it through Depends(...); if it is genuinely a "
            "constant, give it a SCREAMING_SNAKE_CASE name so this guard can tell the "
            "difference (see api/knowledge.py:2035)"
        )


class TestKnownLegitimateCaseStaysUnflagged:
    def test_numeric_constant_default_is_not_flagged(self):
        """api/knowledge.py:2035 -- ``limit: int = QueryDefaults.DEFAULT_SEARCH_LIMIT``.

        Same bare-Attribute shape as the bug this guard exists to catch; only
        the SCREAMING_SNAKE_CASE name tells them apart. Pinned so a future
        rename that breaks that convention is caught here, not by someone
        silencing the guard instead of fixing the name.
        """
        path = _REPO / "autobot-backend" / "api" / "knowledge.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        (func,) = (f for f in _iter_route_functions(tree) if f.name == "search_man_pages")
        flagged = {arg for arg, _lineno in _bare_default_args(func)}
        assert "limit" not in flagged, "QueryDefaults.DEFAULT_SEARCH_LIMIT was flagged -- see module docstring"


_BUG_SHAPE_SOURCE = """
@router.post("/cognition-store/seed")
async def trigger_cognition_seed(request, background_tasks, _user=check_admin_permission):
    pass
"""

_FIXED_SHAPE_SOURCE = """
@router.post("/cognition-store/seed")
async def trigger_cognition_seed(request, background_tasks, _user: bool = Depends(check_admin_permission)):
    pass
"""


def _only_route_function(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    (func,) = _iter_route_functions(ast.parse(source))
    return func


class TestContrastPair:
    """A guard that never fires passes its own suite -- this proves it can fire.

    Both halves run the SAME production code (``_bare_default_args`` via
    ``_iter_route_functions``) on two synthetic sources, neither of which is
    read from the tree this guard also scans (see module docstring).
    """

    def test_bare_callable_default_is_flagged(self):
        func = _only_route_function(_BUG_SHAPE_SOURCE)
        assert [arg for arg, _lineno in _bare_default_args(func)] == ["_user"]

    def test_depends_call_default_is_not_flagged(self):
        func = _only_route_function(_FIXED_SHAPE_SOURCE)
        assert _bare_default_args(func) == []
