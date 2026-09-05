# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test-harness stub module may not both promise a real contract and
auto-vivify everything it did not think of (#14982, #13257).

``autobot-backend/conftest.py`` used to stub ``auth_middleware`` with four
real, named, callable stubs (``get_current_user``, ``check_admin_permission``,
``require_device_jwt``, ``get_auth_middleware``) and then close the block with
``_auth_stub.__getattr__ = lambda attr: MagicMock()``. Any name nobody had
gotten around to stubbing -- ``authenticate_websocket``,
``verify_internal_api_key``, ``AuthenticationMiddleware`` at the time -- fell
through to that catch-all instead of raising, so a missing stub was
indistinguishable from a working one. It already cost real coverage:
``get_auth_middleware`` went unstubbed this way, and twelve tests across three
shards (``test_labels.py``, ``test_budget_token_mode.py``, ``test_routine.py``)
asserted non-admin behaviour and passed because a MagicMock's stringified repr
happened to match nothing, not because the auth logic they name was exercised
(#14944 turned that silent wrong answer into a loud ``TypeError``, which is how
the gap surfaced).

THE PATTERN THIS GUARDS, PRECISELY
-----------------------------------
Not "any ``__getattr__`` on a stub module" -- that would also flag
``testkit/module_stubs.py``'s ``StubSet`` and the many ``_make_pkg_stub``-style
helpers scattered across conftests, which exist BECAUSE nobody can enumerate
every attribute a third-party or opaque package's consumers might touch, and
whose entire contract is honestly "everything here is a MagicMock." Banning
those would either force-rewrite dozens of unrelated, working stubs or need a
manually-curated exemption list that decays the moment someone adds a new one.

The actual defect is narrower and it is what #14982 names: a stub module that
ALSO makes at least one specific, named promise -- a real ``def``/``async def``
(or an inline ``lambda``) bound to a specific attribute, the "every exported
name must be a real callable with a real signature" contract
``autobot-backend/conftest.py``'s auth_middleware block documents -- and then
lets a catch-all silently cover for every name it didn't think to keep that
promise for. A module making ZERO such promises (``_make_pkg_stub``'s output:
only ``pytest_plugins``/``setUpModule``/... bookkeeping constants,
``autobot_shared.redis_management``'s stub: only a ``DATABASE_MAPPING`` dict)
is not making a false one, so it is not this guard's business -- REDIS_MANAGEMENT
(``autobot-backend/conftest.py``, the ``for _redis_sub in [...]`` block) has the
exact same catch-all shape today and is correctly NOT flagged, precisely
because it is a pure blanket mock rather than a broken promise.

So: ``_is_hybrid_catchall_violation`` requires BOTH
  1. at least one OTHER attribute on the same stub object bound to a named
     ``def``/``async def`` or an inline ``lambda`` (a real, specific promise), AND
  2. ``__getattr__`` bound to a callable whose entire body -- ignoring its
     parameter completely -- is a single ``return`` of a bare
     ``MagicMock()``/``Mock()``/``AsyncMock()`` call (the auto-vivifying
     fallback, as opposed to ``testkit/module_stubs.py``'s ``_delegate``-style
     stand-ins, which try the real module first and raise ``AttributeError``
     for dunders rather than mocking unconditionally).

REACH: every tracked ``conftest.py`` PLUS every tracked file under a
``testkit/`` directory (#13451 names this the canonical place stub-builders
live once split out of a conftest, which is exactly what
``testkit/auth_middleware_stub.py`` is -- #14982 moved the block there so
fixing this file did not grow ``autobot-backend/conftest.py`` past its
grandfathered line-count ceiling). A scan of ``conftest.py`` alone would have
gone vacuous the moment that move landed; the floor pins that both halves stay
reachable (test_the_scan_reaches_conftest_and_testkit_files below), the same
lesson ``with_error_handling_single_definition_test.py`` (#15202) recorded for
a scan narrowed back to one tree.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO = Path(__file__).resolve().parents[1]

#: Population floor for the REACH below. Measured at 30 (29 conftest.py files
#: git already tracks, plus this fix's own testkit/auth_middleware_stub.py).
#: RATCHET: raise it when a new conftest.py or testkit/ file genuinely lands;
#: lower it only with a stated reason (a directory deletion, not a filter bug).
_REACH_FLOOR = 25

#: How far the population may outgrow the floor before the floor is stale.
#: Same 1.5x discipline as with_error_handling_single_definition_test.py.
_MAX_FLOOR_SLACK = 1.5

_MOCK_CTOR_NAMES = frozenset({"MagicMock", "Mock", "AsyncMock"})


def _tracked_reach_paths() -> List[Path]:
    """Every tracked ``conftest.py`` plus every tracked file under ``testkit/``."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "*conftest.py", "*testkit/*.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    return [_REPO / relative for relative in listing.split("\0") if relative]


def _is_mock_ctor_call(node: Optional[ast.expr]) -> bool:
    """True if `node` is a zero-argument call to Mock/MagicMock/AsyncMock by name."""
    return (
        isinstance(node, ast.Call)
        and not node.args
        and not node.keywords
        and isinstance(node.func, ast.Name)
        and node.func.id in _MOCK_CTOR_NAMES
    )


def _is_blind_catchall_body(node) -> bool:
    """True if `node` (a Lambda/FunctionDef/AsyncFunctionDef) ignores its
    parameter entirely and unconditionally constructs a fresh mock.

    A docstring-only leading statement is tolerated so a documented version of
    the same shape is still caught; anything else in the body (an `if`, a
    `try`, a call that isn't the bare constructor) means the callable is doing
    something conditional on the requested name -- e.g. ``testkit/module_stubs
    .py``'s ``_delegate``, which tries the real module first and raises
    ``AttributeError`` for dunders -- and is not this pattern.
    """
    if isinstance(node, ast.Lambda):
        return _is_mock_ctor_call(node.body)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        if len(body) != 1:
            return False
        (stmt,) = body
        return isinstance(stmt, ast.Return) and _is_mock_ctor_call(stmt.value)
    return False


def _is_named_real_promise(node, funcs_by_name: Dict[str, object]) -> bool:
    """True if `node` is an inline lambda or a name bound to a def/async def.

    This is the "specific, named promise" half of the hybrid pattern -- e.g.
    ``_auth_stub.get_current_user = _get_current_user_stub`` where
    ``_get_current_user_stub`` is a real ``async def`` in the same file. A
    class reference (``AuthenticationMiddleware``), a dict/list/None constant
    (``DATABASE_MAPPING``, ``pytest_plugins``), or a name the file never
    defines a function for (``MagicMock`` itself) does not count.
    """
    if isinstance(node, ast.Lambda):
        return True
    if isinstance(node, ast.Name):
        target = funcs_by_name.get(node.id)
        return isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef))
    return False


def _functions_by_name(tree: ast.Module) -> Dict[str, object]:
    """Every def/async def in `tree`, keyed by name (last definition wins)."""
    out: Dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def find_hybrid_catchall_violations(source: str, label: str) -> List[str]:
    """Hybrid-catchall violations in `source`. `label` names it in the message.

    A violation is a stub object with >=1 attribute bound to a named real
    promise (def/async def/lambda) AND a ``__getattr__`` bound to a blind
    catch-all (see module docstring for why both halves are required).
    """
    tree = ast.parse(source)
    funcs_by_name = _functions_by_name(tree)

    # base variable name -> {attr: assigned value node}
    by_base: Dict[str, Dict[str, ast.expr]] = {}
    getattr_lineno: Dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)):
                continue
            base = target.value.id
            by_base.setdefault(base, {})[target.attr] = node.value
            if target.attr == "__getattr__":
                getattr_lineno[base] = node.lineno

    violations: List[str] = []
    for base, attrs in by_base.items():
        catchall = attrs.get("__getattr__")
        if catchall is None:
            continue
        resolved = catchall
        if isinstance(catchall, ast.Name):
            resolved = funcs_by_name.get(catchall.id, catchall)
        if not _is_blind_catchall_body(resolved):
            continue
        has_named_promise = any(
            attr != "__getattr__" and _is_named_real_promise(value, funcs_by_name) for attr, value in attrs.items()
        )
        if has_named_promise:
            violations.append(
                f"{label}:{getattr_lineno[base]} -- stub object {base!r} mixes a real named "
                "promise with an auto-vivifying __getattr__ catch-all"
            )
    return violations


def _scan_for_violations(paths: List[Path]) -> Tuple[List[str], List[Tuple[Path, str]]]:
    """(violations, unreadable). A source that cannot be parsed lands in the second list."""
    violations: List[str] = []
    unreadable: List[Tuple[Path, str]] = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            violations.extend(find_hybrid_catchall_violations(source, str(path.relative_to(_REPO))))
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError) as failure:
            unreadable.append((path, f"{type(failure).__name__}: {failure}"))
    return violations, unreadable


@pytest.fixture(scope="module")
def reach_paths() -> List[Path]:
    return _tracked_reach_paths()


@pytest.fixture(scope="module")
def scan_result(reach_paths) -> Tuple[List[str], List[Tuple[Path, str]]]:
    return _scan_for_violations(reach_paths)


def test_the_scan_sees_something(reach_paths):
    """A guard whose file filter matched nothing would report clean, not report
    a skip -- split out so the two failures read differently."""
    assert len(reach_paths) >= _REACH_FLOOR, (
        f"only {len(reach_paths)} conftest.py/testkit files survived the git filter, "
        f"below the recorded floor of {_REACH_FLOOR} -- the filter is eating the tree, "
        "so the check below is vacuous"
    )


def test_the_floor_has_not_decayed_into_slack(reach_paths):
    ceiling = int(_REACH_FLOOR * _MAX_FLOOR_SLACK)
    assert len(reach_paths) <= ceiling, (
        f"the tree has grown to {len(reach_paths)} conftest.py/testkit files against a "
        f"floor of {_REACH_FLOOR} -- raise _REACH_FLOOR to just under the new population. "
        "This is not a defect in the codebase; it is the floor going stale."
    )


def test_the_scan_reaches_conftest_and_testkit_files(reach_paths):
    """Both halves of REACH must stay populated (see module docstring)."""
    relative = {path.relative_to(_REPO) for path in reach_paths}
    assert any(path.name == "conftest.py" for path in relative), "no conftest.py reached the scan"
    assert any("testkit" in path.parts for path in relative), "no testkit/ file reached the scan"
    assert _REPO / "autobot-backend" / "testkit" / "auth_middleware_stub.py" in reach_paths, (
        "the file this fix moved the auth_middleware stub into did not reach the scan -- "
        "a scan narrowed back to conftest.py alone would be vacuous for this exact fix (#14982)"
    )


def test_no_tracked_stub_is_unreadable_by_this_guard(scan_result):
    _violations, unreadable = scan_result
    assert not unreadable, (
        "these tracked sources could not be parsed, so this guard saw NONE of their "
        "attribute assignments and scored them clean without reading them:\n  "
        + "\n  ".join(f"{path.relative_to(_REPO)}  ->  {reason}" for path, reason in unreadable)
    )


def test_no_tracked_conftest_or_testkit_stub_mixes_a_real_promise_with_a_catchall(scan_result):
    violations, _unreadable = scan_result
    assert not violations, (
        "A stub module both promises a real, named callable for some attribute AND "
        "auto-vivifies every other one via a catch-all __getattr__ -- exactly the "
        "auth_middleware pattern #14982 removed, which let a missing stub "
        "(get_auth_middleware) pass as a working one for twelve tests across three "
        "shards. Give the remaining names real stubs instead of restoring the "
        "catch-all:\n  " + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# Contrast pair (#14982's own requirement: one fixture that SHOULD trip this
# guard, one that must not).
# ---------------------------------------------------------------------------


def test_a_hybrid_catchall_trips_the_guard():
    """SHOULD trip: this is the auth_middleware shape before #14982's fix --
    a real, named stub for one attribute, plus a blind catch-all for the rest."""
    source = """
from unittest.mock import MagicMock

def _get_current_user_stub(request=None):
    return {"role": "admin"}

_auth_stub.get_current_user = _get_current_user_stub
_auth_stub.__getattr__ = lambda attr: MagicMock()
"""
    violations = find_hybrid_catchall_violations(source, "fixture")
    assert violations, "a hybrid catch-all (named promise + blind fallback) must be caught"
    assert "_auth_stub" in violations[0]


def test_a_pure_blanket_mock_stub_does_not_trip_the_guard():
    """Must NOT trip: this is _make_pkg_stub's shape -- every attribute is
    honestly a mock, so there is no broken promise to catch."""
    source = """
from unittest.mock import MagicMock

_pkg_stub.pytest_plugins = []
_pkg_stub.setUpModule = None
_pkg_stub.FetchResult = MagicMock
_pkg_stub.__getattr__ = lambda attr: MagicMock()
"""
    assert find_hybrid_catchall_violations(source, "fixture") == []


def test_a_real_fallback_delegate_does_not_trip_the_guard():
    """Must NOT trip: this is testkit/module_stubs.py's _delegate shape -- it
    tries the real module first and raises AttributeError for dunders, so it
    is not an unconditional mock even though the object also carries named
    real promises (get_async_redis_client / get_redis_client)."""
    source = """
def get_async_redis_client(*_a, **_k):
    return None

def get_redis_client(*_a, **_k):
    return None

def _delegate(attr):
    if not attr.startswith("__"):
        try:
            return getattr(real, attr)
        except AttributeError:
            pass
    if attr.startswith("__"):
        raise AttributeError(attr)
    return MagicMock()

_mod.get_async_redis_client = get_async_redis_client
_mod.get_redis_client = get_redis_client
_mod.__getattr__ = _delegate
"""
    assert find_hybrid_catchall_violations(source, "fixture") == []


def test_a_named_promise_alone_does_not_trip_the_guard():
    """Must NOT trip: a real, named stub with no catch-all at all -- exactly
    what auth_middleware's stub looks like after #14982's fix."""
    source = """
def _get_current_user_stub(request=None):
    return {"role": "admin"}

_auth_stub.get_current_user = _get_current_user_stub
"""
    assert find_hybrid_catchall_violations(source, "fixture") == []


def test_a_blind_catchall_alone_does_not_trip_the_guard():
    """Must NOT trip: a blind catch-all with no OTHER named promise on the
    same object -- exactly redis_management's shape (only a DATABASE_MAPPING
    dict alongside it), which is deliberately not this guard's business (see
    module docstring)."""
    source = """
from unittest.mock import MagicMock

_redis_stub.DATABASE_MAPPING = {"celery_broker": 0}
_redis_stub.__getattr__ = lambda attr: MagicMock()
"""
    assert find_hybrid_catchall_violations(source, "fixture") == []
