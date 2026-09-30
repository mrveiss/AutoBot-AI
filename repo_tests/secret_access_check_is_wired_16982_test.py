# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A secret-access rule may not exist only in code no production path calls (#16982).

`Secret.is_accessible_by` models secret access over owner, org, team and scope plus
a session/`shared_with` grant lookup, and its only callers are its own tests. So a
reader concludes the secrets rules live there; they do not, and a change to it
changes nothing that ships. #16927's owner ruling first drafted it as "the real
access check" for secrets, which is the misreading this guard exists to prevent.

## Why the assertion is a disjunction

#16982 offers two dispositions — wire it into the read path, or retire it in favour
of the vault grant — and this test deliberately does not prefer one. The invariant
that matters under either is:

    the symbol is referenced from at least one non-test production module,
    OR it does not exist

Written as a disjunction so the guard survives the decision instead of having to be
rewritten by it. It fails in exactly one state: **defined and unwired**, which is
today's. A guard that encoded the fix would have to be edited to permit the fix,
and a guard edited to permit what it forbids is the shape
`MEASUREMENT_DISCIPLINE.md` warns about — #17650 is an open instance.

## Why it searches for the symbol rather than counting call sites

A control reached through a shared helper looks uncalled to a grep of its own name,
which is how "no production caller" claims go wrong. The check here is deliberately
weak in the permissive direction: **any** production reference satisfies it,
including one inside a helper that forwards. It answers "is this reachable from
shipped code at all", not "is it correctly enforced" — the second needs a test of
the read path, not a reachability sweep.

The complement of that weakness is what makes a failure meaningful: if not even a
mention exists outside the tests, the rule cannot be running.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SYMBOL = "is_accessible_by"

#: Where the definition lives today. If it moves, the finder below still locates it
#: — this is the hint for the failure message, not the search.
_DEFINING_MODULE = "autobot-backend/models/secret.py"

#: Production trees. `repo_tests/` is absent on purpose: a reference from a guard is
#: not a production caller, and counting one would let this test satisfy itself.
_ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_test_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith("_test.py") or name.startswith("test_") or "/tests/" in f"/{rel}"


def _production_modules() -> list[Path]:
    root = _repo_root()
    out: list[Path] = []
    for tree in _ROOTS:
        for path in sorted((root / tree).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if any(skip in rel for skip in ("__pycache__", "/.venv/", "/node_modules/")):
                continue
            if _is_test_path(rel):
                continue
            out.append(path)
    return out


def _defines_symbol(path: Path) -> bool:
    """True if *path* defines `is_accessible_by` (as opposed to referencing it)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _SYMBOL for n in ast.walk(tree))


def _references_symbol(path: Path) -> bool:
    """True if *path* mentions the symbol somewhere other than its own definition."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if _SYMBOL not in source:
        return False
    # A module that only defines it is not a caller of it.
    return not (_defines_symbol(path) and source.count(_SYMBOL) == 1)


@pytest.fixture(scope="module")
def modules() -> list[Path]:
    found = _production_modules()
    # Non-vacuity: an empty or tiny sweep would satisfy every assertion below by
    # finding nothing. `MEASUREMENT_DISCIPLINE.md` -- nothing found and did not look
    # must not read alike.
    assert len(found) > 500, f"only {len(found)} production modules swept -- the roots or filters are wrong"
    return found


def test_the_access_check_is_wired_into_production_or_absent(modules: list[Path]) -> None:
    """#16982: defined-and-unwired is the one state that fails."""
    root = _repo_root()
    definers = [p for p in modules if _defines_symbol(p)]
    referencers = [p for p in modules if _references_symbol(p)]

    if not definers:
        return  # disposition (b): retired. The rule no longer claims to exist.

    assert referencers, (
        f"`{_SYMBOL}` is defined in "
        f"{', '.join(p.relative_to(root).as_posix() for p in definers)} "
        "and referenced by no production module -- only by its own tests.\n"
        "A secret-access rule that no shipped path calls decides nothing, while reading "
        "as the place the rules live (#16982, and #16927's ruling first drafted it as "
        '"the real access check").\n'
        "Resolve by either wiring it into the secret read path beside the vault-grant "
        "check, or retiring it in favour of that check and moving its tests to the "
        "semantics they were really about. This guard accepts either."
    )


def test_the_sweep_would_notice_a_reference(modules: list[Path]) -> None:
    """The assertion above passes trivially if `_references_symbol` never matches.

    Proves the finder works by pointing it at a symbol that *is* production-wired:
    `is_visible`, the shared scoping primitive `is_accessible_by` delegates to, which
    `knowledge/ownership.py` calls. If this fails, the sweep is broken and the test
    above is not evidence of anything.
    """
    root = _repo_root()
    hits = [p for p in modules if "is_visible" in p.read_text(encoding="utf-8")]
    assert len(hits) >= 2, (
        "the reference finder located fewer than 2 production modules mentioning "
        f"`is_visible`, which is wired -- the sweep is broken, not the codebase. Found: "
        f"{[p.relative_to(root).as_posix() for p in hits]}"
    )
