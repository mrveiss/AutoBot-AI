# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One `validate_session_ownership`, with named postures (#14016).

The conversation-file routes used to carry a second validator of the same name with another arity,
parameter order and return type: called positionally with the canonical order it swapped `request`
and `session_id`, a check that runs, passes and guards nothing. There is now ONE definition, in
`autobot-backend/security/session_ownership.py`, taking a `SessionPosture`; the file routes call it
with `SessionPosture.STRICT`. The detector reads the syntax tree, so prose or a string naming the
function is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_NAME = "validate_session_ownership"
_CANONICAL = "autobot-backend/security/session_ownership.py"


def _defines_name(source: str) -> bool:
    """True when `source` defines a function (or method) called `validate_session_ownership`."""
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _NAME for n in ast.walk(ast.parse(source))
    )


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "session-ownership-validator-scan",
    discover=_source_population,
    # Mid-window, from REACH.window() = (2697, 2997, 2847).
    floor=3224,  # re-pinned mid-window (train 73): population 3250, window [2950, 3250] (#17844)
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _definers() -> tuple[str, ...]:
    found = []
    for rel in REACH.examined(repo_root()):
        text = (repo_root() / rel).read_text(encoding="utf-8")
        if _NAME in text and _defines_name(text):
            found.append(rel)
    return tuple(found)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a sync def", "def validate_session_ownership(a, b):\n    pass\n", True),
        ("an async def", "async def validate_session_ownership(a):\n    pass\n", True),
        ("a method", "class C:\n    def validate_session_ownership(self):\n        pass\n", True),
        ("an import", "from security.session_ownership import validate_session_ownership\n", False),
        ("a call", "async def f():\n    await validate_session_ownership('s', r)\n", False),
        ("a string and a comment", "# def validate_session_ownership\nx = 'def validate_session_ownership'\n", False),
        ("a differently named fork", "async def _authorize_session_for_user(r, s, u):\n    pass\n", False),
    ],
)
def test_the_matcher_tells_a_definition_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _defines_name(source) is expected, label


def test_exactly_one_definition_and_it_is_the_canonical_module() -> None:
    assert _definers() == (_CANONICAL,), (
        f"#14016: {list(_definers())} define `{_NAME}`; it lives once in {_CANONICAL}. "
        "Import it, or give a differently-shaped helper its own private name."
    )


_FILE_ROUTES = "autobot-backend/api/conversation_files.py"


_HELPER = "_authorize_file_operation"


def _local_names(tree: ast.AST) -> frozenset[str]:
    """`validate_session_ownership` plus every `from ... import validate_session_ownership as v` alias.
    Module aliases (`import x as so`) need nothing: `so.validate_session_ownership` is an attribute ref."""
    aliased = {
        a.asname
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
        if a.name == _NAME and a.asname
    }
    return frozenset({_NAME} | aliased)


def _is_ref(node: ast.AST, names: frozenset[str] = frozenset({_NAME})) -> bool:
    return (isinstance(node, ast.Name) and node.id in names) or (isinstance(node, ast.Attribute) and node.attr == _NAME)


def _is_strict_call(node: ast.AST, names: frozenset[str] = frozenset({_NAME})) -> bool:
    """A call of the validator (bare, aliased or `mod.`-qualified) passing `posture=SessionPosture.STRICT`."""
    return (
        isinstance(node, ast.Call)
        and _is_ref(node.func, names)
        and any(kw.arg == "posture" and ast.unparse(kw.value) == "SessionPosture.STRICT" for kw in node.keywords)
    )


def _refs_not_strict(source: str) -> list[int]:
    """Lines of EVERY reference to the validator that is not a STRICT call: a plain, aliased or attribute call,
    a `Depends(validate_session_ownership)`, or any bare mention. Imports are not references."""
    tree = ast.parse(source)
    names = _local_names(tree)
    allowed = {id(n.func) for n in ast.walk(tree) if _is_strict_call(n, names)}
    return sorted(n.lineno for n in ast.walk(tree) if _is_ref(n, names) and id(n) not in allowed)


def _is_route(fn: ast.AST) -> bool:
    return isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and getattr(d.func.value, "id", "") == "router"
        for d in fn.decorator_list
    )


def _awaits_check(fn: ast.AST, names: frozenset[str]) -> bool:
    """True when `fn` AWAITS the helper or a STRICT validator call; a mention or a bare call is not a check."""
    for n in ast.walk(fn):
        if not (isinstance(n, ast.Await) and isinstance(n.value, ast.Call)):
            continue
        callee = n.value.func
        if (isinstance(callee, ast.Name) and callee.id == _HELPER) or _is_strict_call(n.value, names):
            return True
    return False


def _routes_without_check(source: str) -> list[str]:
    """@router handlers that await neither `_authorize_file_operation` nor a STRICT validator call."""
    tree = ast.parse(source)
    names = _local_names(tree)
    return [fn.name for fn in ast.walk(tree) if _is_route(fn) and not _awaits_check(fn, names)]


def _helper_has_strict_call(source: str) -> bool:
    """The helper's OWN body contains a STRICT validator call (a call elsewhere in the file does not count)."""
    tree = ast.parse(source)
    names = _local_names(tree)
    return any(
        isinstance(fn, ast.AsyncFunctionDef)
        and fn.name == _HELPER
        and any(_is_strict_call(n, names) for n in ast.walk(fn))
        for fn in ast.walk(tree)
    )


_ALIAS_IMPORT = "from security.session_ownership import validate_session_ownership as v\n"
_STRICT_CALL = "validate_session_ownership(s, r, posture=SessionPosture.STRICT)"


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("strict", f"{_STRICT_CALL}\n", []),
        ("strict through a module", "m.validate_session_ownership(s, r, posture=SessionPosture.STRICT)\n", []),
        ("default", "validate_session_ownership(s, r)\n", [1]),
        ("another posture", "validate_session_ownership(s, r, posture=SessionPosture.DEFAULT)\n", [1]),
        ("a Depends form", "def f(o=Depends(validate_session_ownership)):\n    pass\n", [1]),
        ("an attribute call", "m.validate_session_ownership(s, r)\n", [1]),
        ("a bare mention", "x = validate_session_ownership\n", [1]),
        ("an import only", "from security.session_ownership import validate_session_ownership\n", []),
    ],
)
def test_the_reference_matcher_flags_every_non_strict_use(label: str, source: str, expected: list[int]) -> None:
    assert _refs_not_strict(source) == expected, label


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "authorized helper",
            "@router.get('/x')\nasync def h(r, s):\n    await _authorize_file_operation(r, s, 'v')\n",
            [],
        ),
        ("strict call", f"@router.get('/x')\nasync def h(r, s):\n    await {_STRICT_CALL}\n", []),
        ("no check at all", "@router.get('/x')\nasync def h(r, s):\n    return 1\n", ["h"]),
        (
            "a default call is not a check",
            "@router.get('/x')\nasync def h(r, s):\n    await validate_session_ownership(s, r)\n",
            ["h"],
        ),
        ("a non-route needs none", "async def helper(r, s):\n    return 1\n", []),
        (
            "a mention without an await",
            "@router.get('/x')\nasync def h(r, s):\n    x = _authorize_file_operation\n",
            ["h"],
        ),
        (
            "a call that is not awaited",
            "@router.get('/x')\nasync def h(r, s):\n    _authorize_file_operation(r, s, 'v')\n",
            ["h"],
        ),
        (
            "an aliased non-strict call",
            _ALIAS_IMPORT + "@router.get('/x')\nasync def h(r, s):\n    await v(s, r)\n",
            ["h"],
        ),
        (
            "an aliased strict call",
            _ALIAS_IMPORT + "@router.get('/x')\nasync def h(r, s):\n    await v(s, r, posture=SessionPosture.STRICT)\n",
            [],
        ),
    ],
)
def test_the_route_matcher_finds_a_handler_with_no_check(label: str, source: str, expected: list[str]) -> None:
    assert _routes_without_check(source) == expected, label


_HELPER_OK = f"async def {_HELPER}(r, s, op):\n    await {_STRICT_CALL}\n    return 1\n"
_ROUTE_OK = "@router.get('/x')\nasync def h(r, s):\n    await _authorize_file_operation(r, s, 'v')\n"
_HELPER_NO_STRICT = f"async def {_HELPER}(r, s, op):\n    return 1\n"
_OTHER_ROUTE_STRICT = f"@router.get('/p')\nasync def p(r, s):\n    await {_STRICT_CALL}\n"


def _verdict(source: str) -> bool:
    """True when the file passes every file-route check."""
    return _helper_has_strict_call(source) and not _refs_not_strict(source) and not _routes_without_check(source)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("the correct form", _HELPER_OK + _ROUTE_OK, True),
        (
            "helper lost its STRICT call while another route keeps one",
            _HELPER_NO_STRICT + _ROUTE_OK + _OTHER_ROUTE_STRICT,
            False,
        ),
        (
            "a route mentions the helper without awaiting it",
            _HELPER_OK + "@router.get('/x')\nasync def h(r, s):\n    x = _authorize_file_operation\n",
            False,
        ),
        (
            "an aliased non-strict call",
            _HELPER_OK + _ALIAS_IMPORT + _ROUTE_OK + "async def q(r, s):\n    await v(s, r)\n",
            False,
        ),
        (
            "a module-aliased non-strict call",
            _HELPER_OK
            + "import security.session_ownership as so\n"
            + _ROUTE_OK
            + "async def q(r, s):\n    await so.validate_session_ownership(s, r)\n",
            False,
        ),
    ],
)
def test_the_file_route_verdict_catches_a_hollow_helper_and_unawaited_or_aliased_checks(
    label: str, source: str, expected: bool
) -> None:
    assert _verdict(source) is expected, label


def test_every_file_route_check_runs_under_the_strict_posture() -> None:
    source = (repo_root() / _FILE_ROUTES).read_text(encoding="utf-8")
    assert _NAME in source, "the file routes no longer reach the validator at all"
    assert _helper_has_strict_call(source), f"#14016: `{_HELPER}` itself no longer makes a STRICT call"
    assert _refs_not_strict(source) == []
    assert _routes_without_check(source) == []
