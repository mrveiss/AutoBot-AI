# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A checker may not re-declare what `_scan_helpers` already exports (#13916).

`configure_logging` existed thirteen times under `tools/lint/`, byte-identical
in every one -- measured by comparing ASTs with docstrings excluded: 13
definitions, 1 distinct body. None imported another. Each new checker copied
the nearest neighbour because that was easier than discovering the shared
module, and nothing failed when it did.

The specific duplication is now gone. This guard is for the general case,
because the next one will not be `configure_logging`: `repo_root` and
`_is_test_file` have the same shape today, and the copy after that has not
been written yet.

## Why it keys on NAME, not on body

The first version of this guard compared function bodies and was **vacuous**.
It could not catch the regression it was written for, because the canonical
`configure_logging` takes its logger as a PARAMETER while every private copy
used the module global -- so the bodies necessarily differ and the comparison
could never match. Proved by reintroducing a copy and watching the guard pass.

So it keys on a curated list of names that `_scan_helpers` deliberately owns.
That is defensible precisely because the list is curated: these are not
generic words like `main` or `audit`, they are the canonical spellings, and a
`tools/lint` module defining one of them locally is copying rather than
coinciding.

The list is explicit rather than "everything `_scan_helpers` exports" so that
adding a helper there cannot silently start failing unrelated checkers that
happen to share a name.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_CANONICAL = "tools/lint/_scan_helpers.py"


#: Names `_scan_helpers` owns. A `tools/lint` or `pipeline-scripts` module
#: defining one of these locally is a private copy, whatever its body says.
#: Curated, not derived from the module's exports: a derived list would make
#: adding a helper there retroactively fail unrelated modules.
#:
#: `repo_root` is deliberately absent. It is owned by `repo_tests/_paths.py`,
#: not by this module -- the guard's own self-check caught me listing it here,
#: which is what that check is for.
_OWNED = ("configure_logging", "tracked_paths", "logical_lines")


def _delegates_to(fn: ast.FunctionDef, name: str) -> bool:
    """True if *fn* is a thin wrapper that just calls *name*.

    A wrapper is the OPPOSITE of a fork: it has one implementation behind it.
    `check_no_root_clutter._tracked_paths` is `return tracked_paths(repo_root)`,
    kept as a named function solely so the suite can monkeypatch it by name --
    and the first version of this guard flagged it. A guard with false
    positives gets muted, which costs more than the copy it would have caught.
    """
    body = [st for st in fn.body if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    call = body[0].value
    if not isinstance(call, ast.Call):
        return False
    callee = call.func
    target = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)
    return target == name


def _locally_defined(path: Path) -> set[str]:
    """Top-level function names a module implements itself, leading `_` ignored.

    A function that merely delegates to the canonical helper of the same name
    is excluded -- it is a seam, not a second implementation.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bare = node.name.lstrip("_")
        if _delegates_to(node, bare):
            continue
        found.add(bare)
    return found


def test_no_checker_redeclares_a_shared_helper() -> None:
    """The invariant: one definition per concept, in the module that owns it."""
    root = repo_root()
    canonical = _locally_defined(root / _CANONICAL)
    missing = [n for n in _OWNED if n not in canonical]
    assert not missing, (
        f"{_CANONICAL} does not define {missing} -- the owned list names something that is not "
        "there, so the guard would police a helper that does not exist"
    )

    candidates = tracked_paths(root, "tools/lint/*.py", "pipeline-scripts/*.py")
    # Non-vacuity: an empty sweep satisfies the assertion by looking at nothing.
    assert len(candidates) > 40, f"only {len(candidates)} files swept -- the patterns or the root are wrong"

    offenders: list[str] = []
    for rel in candidates:
        if rel == _CANONICAL:
            continue
        for name in sorted(_locally_defined(root / rel) & set(_OWNED)):
            offenders.append(f"{rel}: defines {name}() locally")

    assert not offenders, (
        f"{len(offenders)} private copy/copies of a helper `_scan_helpers` owns:\n  "
        + "\n  ".join(offenders)
        + "\n\nImport it from `tools.lint._scan_helpers` instead. `configure_logging` reached "
        "THIRTEEN identical copies before anything noticed, because copying the neighbouring "
        "checker is easier than finding the shared module and nothing failed when you did (#13916)."
    )


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("a plain copy", "def configure_logging():\n    pass\n", {"configure_logging"}),
        ("an underscore-prefixed copy", "def _configure_logging():\n    pass\n", {"configure_logging"}),
        ("an unrelated helper", "def summarise():\n    pass\n", {"summarise"}),
        ("a nested function is not a definition", "def outer():\n    def repo_root():\n        pass\n", {"outer"}),
        ("a thin wrapper that delegates", "def _tracked_paths(r):\n    return tracked_paths(r)\n", set()),
        (
            "a wrapper that does more than delegate",
            "def _tracked_paths(r):\n    x = 1\n    return tracked_paths(r)\n",
            {"tracked_paths"},
        ),
    ],
)
def test_the_detector_sees_top_level_definitions_only(label: str, source: str, expected: set, tmp_path: Path) -> None:
    """The contrast set.

    The underscore row matters: the thirteenth copy was `_configure_logging`,
    and a search for `def configure_logging` missed it entirely -- it was found
    only because a later check noticed a call the migration had not rewritten.

    The nested row matters the other way: a helper defined INSIDE a function is
    local scope, not a competing definition, and flagging it would be noise.
    """
    f = tmp_path / "m.py"
    f.write_text(source, encoding="utf-8")
    assert _locally_defined(f) == expected, label
