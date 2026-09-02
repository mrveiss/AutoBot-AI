# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A meta-path import guard cannot catch a module its conftest already cached (#14913).

Several tests prove a package does not eagerly import something heavy by
installing a `sys.meta_path` finder that raises on the forbidden prefix, then
importing the package. The reasoning is sound in isolation and stated in those
files: intercepting the *attempt* does not depend on what an earlier test
imported, whereas a `sys.modules` presence check would.

It has one hole, and it is fatal rather than partial. If a conftest puts the
forbidden prefix into `sys.modules` before any test runs, Python short-circuits
on the cache and **never consults the finder at all**. The guard cannot fire, so
it passes — and it passes in every run, not merely in some orders. That is worse
than an order-dependent check, because nothing ever reveals it.

Demonstrated on `llc/scheduler/lazy_import_test.py`: reintroducing the eager
`#13332` import chain leaves its meta-path assertion **green**, because
`autobot-backend/conftest.py` caches `llm_shared` at import time.

This guard finds the pairing statically — a blocked prefix that some conftest on
the importing package's path pre-caches — so a new one cannot be written into
the same hole.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIP_PARTS = {"node_modules", ".worktrees", "__pycache__", "venv", ".venv"}

#: A prefix installed into sys.modules, e.g. `sys.modules["llm_shared"] = stub`.
_CACHES = re.compile(r"""sys\.modules\[\s*["']([\w.]+)["']\s*\]\s*=""")
#: The same via setdefault.
_CACHES_DEFAULT = re.compile(r"""sys\.modules\.setdefault\(\s*["']([\w.]+)["']""")


def _tracked(pattern: str) -> List[Path]:
    out = subprocess.run(
        ["git", "ls-files", pattern], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [
        REPO_ROOT / p
        for p in out
        if not _SKIP_PARTS & set(Path(p).parts)
    ]


def _meta_path_guards() -> List[Path]:
    """Test files that install a `sys.meta_path` finder."""
    found = []
    for path in _tracked("*_test.py") + _tracked("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        if "sys.meta_path" in text:
            found.append(path)
    return sorted(set(found))


def _blocked_prefixes(path: Path) -> Set[str]:
    """String literals handed to a finder constructed in this file.

    Derived from the call, not from a hand-written list: a guard added later
    with a different class name is still covered.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):  # pragma: no cover
        return set()
    prefixes: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if "reject" not in name.lower() and "block" not in name.lower():
            continue
        for arg in node.args:
            for literal in ast.walk(arg):
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                    prefixes.add(literal.value)
    return prefixes


def _precached_by_conftests_above(path: Path) -> Dict[str, Path]:
    """Prefixes any conftest between the repo root and *path* puts in sys.modules."""
    cached: Dict[str, Path] = {}
    directory = path.parent
    while True:
        conftest = directory / "conftest.py"
        if conftest.is_file():
            text = conftest.read_text(encoding="utf-8")
            for name in _CACHES.findall(text) + _CACHES_DEFAULT.findall(text):
                cached.setdefault(name, conftest)
        if directory == REPO_ROOT:
            break
        directory = directory.parent
    return cached


def _neutralised() -> List[Tuple[Path, str, Path]]:
    out: List[Tuple[Path, str, Path]] = []
    for guard in _meta_path_guards():
        cached = _precached_by_conftests_above(guard)
        for prefix in sorted(_blocked_prefixes(guard)):
            # A cached parent neutralises a child prefix too: `llm_shared` in
            # sys.modules stops any attempt at `llm_shared.types`.
            for name, conftest in cached.items():
                if prefix == name or prefix.startswith(name + "."):
                    out.append((guard, prefix, conftest))
                    break
    return out


_GUARDS = _meta_path_guards()
_NEUTRALISED = _neutralised()

#: Known instances, with the issue tracking each. Shrink-only: an entry goes when
#: its issue closes, and a NEW pairing fails below. These are not fixed here
#: because the fix lives in files whose suites cannot run on a sub-floor
#: interpreter (`llc/scheduler/base.py` raises at import below Python 3.11 by
#: deliberate design, #13369), so the change cannot be verified where it is made.
KNOWN_NEUTRALISED: Dict[str, str] = {
    "autobot-backend/llc/scheduler/lazy_import_test.py": "#14913",
    "autobot-backend/llc/services/lazy_import_test.py": "#14913",
}


def test_the_sweep_found_the_guards() -> None:
    """Guard the guard: no guards found means every assertion below is vacuous."""
    assert len(_GUARDS) >= 3, (
        f"only {len(_GUARDS)} meta-path guards found — the sweep broke. "
        f"Found: {[str(p.relative_to(REPO_ROOT)) for p in _GUARDS]}"
    )


@pytest.mark.parametrize(
    "guard,prefix,conftest",
    _NEUTRALISED,
    ids=lambda v: str(v.name) if isinstance(v, Path) else str(v),
)
def test_no_new_guard_blocks_a_prefix_its_conftest_precaches(guard: Path, prefix: str, conftest: Path) -> None:
    rel = str(guard.relative_to(REPO_ROOT))
    if rel in KNOWN_NEUTRALISED:
        pytest.skip(f"{rel}: known, tracked by {KNOWN_NEUTRALISED[rel]}")

    pytest.fail(
        f"{rel} blocks {prefix!r} with a sys.meta_path finder, but "
        f"{conftest.relative_to(REPO_ROOT)} puts it in sys.modules before any test runs. "
        "Python short-circuits on the cache, so the finder is never consulted and the "
        "guard passes whatever the code does. Assert presence/absence in sys.modules "
        "for a module nothing pre-caches instead."
    )


def test_every_known_entry_is_still_neutralised() -> None:
    """The exemption table shrinks. An entry whose guard now works — or which no
    longer exists — is indistinguishable from one still needed, which is how a
    temporary allowance becomes permanent."""
    live = {str(g.relative_to(REPO_ROOT)) for g, _, _ in _NEUTRALISED}
    stale = sorted(set(KNOWN_NEUTRALISED) - live)

    assert not stale, (
        f"these are recorded as neutralised but no longer are: {stale}. "
        "Remove their KNOWN_NEUTRALISED entries in the commit that fixed them."
    )
