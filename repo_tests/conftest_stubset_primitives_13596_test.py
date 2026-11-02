# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A conftest stubs modules through ``StubSet``, not by hand (#13596).

``testkit/module_stubs.py`` encodes the three primitives a conftest needs to stub a package
-- give it a real ``__path__``, execute a file under a name, and put an entry in or take it out
of ``sys.modules`` -- together with the restore that undoes them. Every conftest that wrote
those by hand lost one half of that: nothing restored what it displaced, and a mutated
``__path__`` is invisible to the ``sys.modules`` leak guard, which compares module identity.

The markers are the primitives, read from the syntax tree so prose naming them is not a
definition:

* an assignment to ``<x>.__path__``
* a call to ``spec_from_file_location``
* an assignment to, or ``del`` of, ``sys.modules[...]``

``_UNMIGRATED`` is the shrink-only list of conftests still to move. A conftest on it that no
longer uses a primitive fails too, so the line is deleted in the same change that migrates it.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend", "autobot-infrastructure", "autobot-npu-worker", "autobot-slm-backend", "repo_tests")

#: Conftests that still hand-roll the primitives. THIS LIST ONLY SHRINKS; each value is why
#: the file is not migrated yet.
_UNMIGRATED = {
    "autobot-backend/conftest.py": "ancestor of every backend test, 65 sys.modules keys; its agent_loop planting is "
    "load-bearing for other conftests (#13551), so it is its own slice (#13596)",
    "autobot-backend/llc/tests/conftest.py": "ref-counted per-collector/per-test install and restore over MagicMock "
    "stubs with catch-all __getattr__; a different lifecycle from StubSet.fixture, with the _restore() defect "
    "tracked on #13386",
    "autobot-backend/services/knowledge/conftest.py": "snapshots the pre-stub state and restores it per module "
    "(#13386); it restores what the test modules install, it does not install stubs itself",
    "autobot-slm-backend/conftest.py": "slm root conftest, a separate interpreter tree (#13084); own slice (#13596)",
    "autobot-slm-backend/tests/api/conftest.py": "installs a two-module multipart fallback only when starlette "
    "cannot import it; StubSet has no primitive for a __path__-less leaf stub yet (#13596)",
}


def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "modules"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "sys"
    )


def _targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.Assign, ast.Delete)):
        return list(node.targets)
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return [node.target]
    return []


def _called_name(node: ast.Call) -> str:
    fn = node.func
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""


def hand_rolled_primitives(source: str) -> list[str]:
    """The primitives `source` writes by hand, as ``"<kind>:<line>"`` entries."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        for tgt in _targets(node):
            if _is_sys_modules(tgt):
                found.append(f"sys.modules:{node.lineno}")
            elif isinstance(tgt, ast.Attribute) and tgt.attr == "__path__":
                found.append(f"__path__:{node.lineno}")
        if isinstance(node, ast.Call) and _called_name(node) == "spec_from_file_location":
            found.append(f"spec_from_file_location:{node.lineno}")
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a sys.modules write", "sys.modules['x'] = m\n", ["sys.modules:1"]),
        ("a sys.modules delete", "del sys.modules['x']\n", ["sys.modules:1"]),
        ("a __path__ write", "pkg.__path__ = ['/a']\n", ["__path__:1"]),
        ("an annotated __path__", "pkg.__path__: list = []\n", ["__path__:1"]),
        ("a file spec", "s = importlib.util.spec_from_file_location('a', p)\n", ["spec_from_file_location:1"]),
        ("a bare file spec", "s = spec_from_file_location('a', p)\n", ["spec_from_file_location:1"]),
        ("a read of sys.modules", "m = sys.modules.get('x')\nn = sys.modules['y']\n", []),
        ("a read of __path__", "p = pkg.__path__\n", []),
        ("a comment naming one", "# sys.modules['x'] = m\nx = 1\n", []),
        ("a StubSet call", "stubs.install_package('a', p)\nstubs.real_load('a.b', f)\n", []),
        ("another mapping", "registry['x'] = m\n", []),
    ],
)
def test_the_matcher_tells_a_hand_rolled_primitive_from_a_use(label: str, source: str, expected: list[str]) -> None:
    assert hand_rolled_primitives(source) == expected, label


def _conftests(root: Path) -> list[str]:
    """Every tracked ``conftest.py`` under the pytest roots; empty on an empty tree."""
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.rsplit("/", 1)[-1] == "conftest.py"]


REACH = declare(
    "conftest-stubset-primitives",
    discover=_conftests,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=24,  # #18811: population 29 -> window [19, 29], re-pinned mid-window
    what="conftest.py files",
    roots=_ROOTS,
    growth=10,
)


@functools.lru_cache(maxsize=1)
def _offenders() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rel in REACH.examined(repo_root()):
        hits = hand_rolled_primitives((repo_root() / rel).read_text(encoding="utf-8"))
        if hits:
            out[rel] = hits
    return out


def test_no_conftest_hand_rolls_the_stub_primitives() -> None:
    new = {rel: hits for rel, hits in _offenders().items() if rel not in _UNMIGRATED}
    assert not new, (
        f"#13596: {sorted(new)} write sys.modules / __path__ / spec_from_file_location by hand ({new}). "
        "Use testkit.module_stubs.StubSet (install_package, adopt_package, real_load, evict, import_real) "
        "and call stubs.restore() in pytest_unconfigure. Do not add to _UNMIGRATED."
    )


def test_the_unmigrated_list_only_shrinks() -> None:
    stale = sorted(rel for rel in _UNMIGRATED if rel not in _offenders())
    assert not stale, (
        f"#13596: {stale} no longer hand-roll a primitive (or no longer exist); delete the line from "
        "_UNMIGRATED in the same change that migrated it."
    )


def test_the_scan_reaches_the_conftests_it_names() -> None:
    examined = set(REACH.examined(repo_root()))
    assert set(_UNMIGRATED) <= examined, sorted(set(_UNMIGRATED) - examined)
