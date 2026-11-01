# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No function re-derives the repository root from its own file depth (#18101).

`autobot_shared.paths` owns root resolution: `project_root()` for the configured or installed
tree, `git_repo_root(start)` for callers that go on to run `git ls-files`. A function whose whole
body is `Path(__file__).resolve().parents[N]` is the same answer re-derived, and it is the
fragile form: the depth encodes the file's position, so moving the file silently moves "root".

The detector is name-agnostic. The census behind #18101 found six names for the one concept, and
a name-keyed detector would have missed the seventh.

Exemptions are a ledger, not a waiver. Each carries a reason; each is re-derived from the tree
by the detector itself, so an entry that no longer matches (the file converted, moved, or its
resolver deleted) fails here instead of lingering as an unexplained exemption.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "pipeline-scripts",
    "repo_tests",
    "scripts",
    "tools",
)

#: lint hooks run as a bare script from the repo root, before any `autobot_shared` import path
#: exists; their own `sys.path` bootstrap is the same depth read once (the #11761 precedent).
_BARE_SCRIPT = (
    "standalone lint hook: invoked as a bare script, autobot_shared is not on sys.path until "
    "this file bootstraps it (#11761, #15914); converting would need the very depth it removes"
)

#: path -> why a depth-based resolver may remain. Every value must be non-empty.
EXEMPT: dict[str, str] = {
    "tools/lint/check_extension_import_boundaries.py": _BARE_SCRIPT,
    "autobot-backend/api/codebase_analytics/endpoints/shared.py": "deferred, not exempt in principle: owned by queued branch issue-18067-duplicate-tooling (#18101); also carries the #10730 deployed-layout probe",
}


def _mentions_file(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


def _ends_in_a_climb(node: ast.AST) -> bool:
    """True when the returned value IS a depth climb, not a call that merely receives one.

    Unwraps `.resolve()`-style method calls and `Path(...)`/`str(...)` wrappers,
    then asks whether what is left is `.parents[N]` or `.parent`. `git_repo_root(<file>.parent)`
    passes a climb as an argument and is the canonical form, so it must not match.
    """
    while True:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr != "Path":
            node = node.func.value
        elif isinstance(node, ast.Call) and node.args and _is_path_wrapper(node.func):
            node = node.args[0]
        else:
            break
    if isinstance(node, ast.Subscript):
        return isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
    return isinstance(node, ast.Attribute) and node.attr == "parent"


def _is_path_wrapper(func: ast.AST) -> bool:
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name in {"Path", "str", "PurePath"}


def depth_resolvers(source: str) -> list[str]:
    """Names of functions whose single return climbs from `__file__` by depth."""
    found = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
            if _mentions_file(body[0].value) and _ends_in_a_climb(body[0].value):
                found.append(fn.name)
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("parents depth", "def r():\n    return Path(__file__).resolve().parents[2]\n", ["r"]),
        ("parent chain", "def anything():\n    return Path(__file__).resolve().parent.parent\n", ["anything"]),
        ("docstring first", 'def r():\n    """doc"""\n    return pathlib.Path(__file__).parents[1]\n', ["r"]),
        ("delegating", "def r():\n    return git_repo_root(Path(__file__).resolve().parent)\n", []),
        ("canonical", "def r():\n    return project_root()\n", []),
        (
            "a path under the root is not the root",
            'def r():\n    return Path(__file__).resolve().parents[2] / "main.py"\n',
            [],
        ),
        ("component dir not climbed", "def r():\n    return Path(__file__).resolve()\n", []),
        ("not from __file__", "def r(p):\n    return p.parents[1]\n", []),
    ],
)
def test_the_detector_tells_a_depth_resolver_from_a_delegating_one(
    label: str, source: str, expected: list[str]
) -> None:
    assert depth_resolvers(source) == expected, label


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith(".py")]


REACH = declare(
    "root-resolver-depth-scan",
    discover=_population,
    floor=7246,  # mid-window: population 7396, window (7096, 7396)
    what="tracked python",
    roots=_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _detected() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rel in REACH.examined(repo_root()):
        names = depth_resolvers((repo_root() / rel).read_text(encoding="utf-8"))
        if names:
            out[rel] = names
    return out


def test_no_new_depth_based_root_resolver() -> None:
    new = sorted(set(_detected()) - set(EXEMPT))
    assert not new, (
        f"#18101: {new} derive the repo root from their own file depth. Call "
        "`autobot_shared.paths.git_repo_root(Path(__file__).resolve().parent)` (or `project_root()`), "
        "or add a reasoned entry to EXEMPT if the file genuinely cannot import autobot_shared."
    )


def test_every_exemption_still_matches_and_says_why() -> None:
    stale = sorted(set(EXEMPT) - set(_detected()))
    assert not stale, f"#18101: exemptions that no longer match a depth resolver; delete them: {stale}"
    assert all(reason.strip() for reason in EXEMPT.values()), "an exemption without a reason"


#: Converted sites: file -> the depth expression it used to evaluate, as a function of its own path.
#: Each must still land on the directory the canonical call names, from the file's real location.
_CONVERTED = {
    "autobot-backend/workers/audit_tasks.py": lambda f: f.resolve().parent.parent.parent,
    "autobot-backend/api/codebase_analytics/frontend_call_scanner_comments_test.py": lambda f: f.resolve().parents[3],
    "repo_tests/secret_access_check_is_wired_16982_test.py": lambda f: f.resolve().parents[1],
}


@pytest.mark.parametrize("rel", sorted(_CONVERTED))
def test_a_converted_site_resolves_to_the_path_it_resolved_to_before(rel: str) -> None:
    from autobot_shared.paths import git_repo_root, project_root

    old = _CONVERTED[rel](repo_root() / rel)
    assert git_repo_root(old).resolve() == old
    assert project_root().resolve() == old
    assert depth_resolvers((repo_root() / rel).read_text(encoding="utf-8")) == []
