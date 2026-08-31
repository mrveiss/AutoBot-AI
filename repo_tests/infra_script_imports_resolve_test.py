# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An import under shared/scripts must name a module that actually resolves (#14518).

pyflakes never checks that an import *target* exists. It reports F401 for an
unused import and F821 for an undefined name, so a script can be completely
F821-clean — which every script in this tree became after #14405 / PR #14504 —
and still die with ``ModuleNotFoundError`` on its own import block, before
reaching a single line of the repaired code. "0 findings" is not "runs".

The sweep behind #14518 found 11 distinct unresolvable targets across 44 import
sites, in three shapes:

* a stale ``backend.`` prefix over the ``autobot-backend/`` tree (22 sites),
  plus the legacy ``src.``, ``llm_interface`` and ``chat_history_manager``
  names left behind by earlier layouts;
* a target that exists but is not on the importing script's path;
* a third-party target declared in no requirements file.

This is the ``autobot-infrastructure/shared/scripts/`` counterpart of
``repo_tests/first_party_imports_resolve_test.py`` (#14839), and deliberately
shares its policy decisions: resolve the **module**, never the imported name
(resolving names means importing, which drags in the whole dependency graph);
and exempt an import inside a ``try`` that catches ``ImportError`` /
``ModuleNotFoundError``, because that is a genuine optional dependency.

Scope note: this lives in ``repo_tests/`` because ``autobot-infrastructure/`` is
in no pytest ``testpaths`` entry and in no CI pytest invocation. A test placed
next to the scripts would never run — which is the same class of silence the
test exists to remove.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"
# ``.claude`` for the same reason as ``.worktrees`` (#14985): agent worktrees are
# checked out under it, and a requirements file belonging to another branch would
# widen _DECLARED below — an import this repo never declares would then read as
# declared, which is the under-reporting direction.
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"}

# Roots an import may legitimately resolve against: the repo root (installed
# first-party packages such as autobot_shared), the two backends, and the
# scripts tree itself. The importing file's own directory is added per file.
_ROOTS = (
    _REPO_ROOT,
    _REPO_ROOT / "autobot-backend",
    _REPO_ROOT / "autobot-slm-backend",
    _SCRIPTS,
)

# Import name -> distribution name, where the two differ. Only entries actually
# needed by this tree; an unknown alias produces a finding, never a silent pass.
_DIST_ALIASES = {
    "yaml": "pyyaml",
    "dotenv": "python_dotenv",
    "jose": "python_jose",
    "dateutil": "python_dateutil",
    "PIL": "pillow",
    "cv2": "opencv_python",
    "sklearn": "scikit_learn",
    "psycopg2": "psycopg2_binary",
    "jwt": "pyjwt",
    "OpenSSL": "pyopenssl",
    "git": "gitpython",
    "attr": "attrs",
    "pkg_resources": "setuptools",
    "docx": "python_docx",
    "pptx": "python_pptx",
    "fitz": "pymupdf",
    "magic": "python_magic",
    "bs4": "beautifulsoup4",
    "zmq": "pyzmq",
}

# Imports whose target genuinely does not resolve, each with the issue tracking
# it. Kept small on purpose: an entry here is a live bug, not an accepted
# exception. The parametrized test below asserts every entry is *still* broken,
# so a fix forces its exemption out rather than leaving this file quietly
# guarding one path less than it claims.
#
# EMPTY, which is the goal state #14518 asked for ("add the resolution check
# with no allowlist, once the count is zero"). The three #14870 entries went
# when their scripts were repointed at symbols that exist; the three #14871
# entries went when langchain-redis was declared in
# ``autobot-infrastructure/shared/scripts/requirements.txt``.
#
# An empty allowlist costs this file its positive control: the parametrized
# test below now collects zero cases, so "the sweep found nothing" can no
# longer be told apart from "the sweep looks at nothing". That is what
# ``test_the_detector_still_fires_on_a_synthetic_import`` replaces it with —
# see its docstring.
_KNOWN_BROKEN: dict[tuple[str, str], str] = {}


def _declared_distributions() -> tuple[set[str], int]:
    """Every distribution named by a requirements file or pyproject in the repo."""
    names: set[str] = set()
    files = 0
    candidates = list(_REPO_ROOT.rglob("requirements*.txt")) + list(
        _REPO_ROOT.rglob("pyproject.toml")
    )
    for path in candidates:
        # Relative parts, never the absolute path — see the note in
        # first_party_imports_resolve_test.py about a checkout that itself sits
        # under a directory named `venv` or `.worktrees`.
        if any(part in _SKIP_PARTS for part in path.relative_to(_REPO_ROOT).parts):
            continue
        files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^["\']?([A-Za-z0-9][A-Za-z0-9._-]*)', line)
            if match:
                names.add(match.group(1).lower().replace("-", "_"))
    return names, files


_DECLARED, _REQUIREMENTS_FILES = _declared_distributions()
_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _is_declared(top: str) -> bool:
    """Is this top-level import name covered by a declared distribution?"""
    normalised = top.lower().replace("-", "_")
    if normalised in _DECLARED:
        return True
    alias = _DIST_ALIASES.get(top)
    return alias is not None and alias in _DECLARED


def _resolves(module: str, own_dir: Path) -> bool:
    """Does this dotted module exist under a first-party root or beside its importer?"""
    parts = module.split(".")
    for root in (*_ROOTS, own_dir):
        base = root.joinpath(*parts)
        if base.with_suffix(".py").exists() or (base / "__init__.py").exists():
            return True
    return False


def _optional_import_nodes(tree: ast.AST) -> set[int]:
    """Nodes inside a try/except that catches an import error.

    Deliberately NOT including bare ``Exception``, for the reason spelled out in
    first_party_imports_resolve_test.py: a broad handler is not a declaration
    that an import is optional, and it is the single most common wrapper around
    a first-party import in this repo. Treating it as an exemption would make
    this guard blind at exactly the places it exists to watch.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        caught: set[str] = set()
        for handler in node.handlers:
            for sub in ast.walk(handler.type) if handler.type else []:
                if isinstance(sub, ast.Name):
                    caught.add(sub.id)
        if {"ImportError", "ModuleNotFoundError"} & caught:
            guarded.update(id(child) for child in ast.walk(node))
    return guarded


def _unresolvable_in_source(source: str, own_dir: Path) -> list[tuple[str, int]]:
    """((module, lineno)) for every import in one source string that resolves to nothing.

    Split out of the tree walk so the detector can be driven against a
    synthetic sample. With ``_KNOWN_BROKEN`` empty there is no longer a live
    defect to prove the matcher still works, and a matcher that quietly stops
    matching reports the whole tree clean.
    """
    tree = ast.parse(source)
    guarded = _optional_import_nodes(tree)
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            module = node.module
        elif isinstance(node, ast.Import):
            module = node.names[0].name
        else:
            continue
        top = module.split(".")[0]
        if top in _STDLIB or id(node) in guarded:
            continue
        if _resolves(module, own_dir) or _is_declared(top):
            continue
        found.append((module, node.lineno))
    return found


def _unresolvable() -> tuple[list[tuple[str, str, int]], int]:
    """((relative path, module, lineno) list, files scanned)."""
    found: list[tuple[str, str, int]] = []
    scanned = 0
    for path in sorted(_SCRIPTS.rglob("*.py")):
        if any(part in _SKIP_PARTS for part in path.relative_to(_SCRIPTS).parts):
            continue
        scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
            hits = _unresolvable_in_source(source, path.parent)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(_SCRIPTS))
        found.extend((rel, module, lineno) for module, lineno in hits)
    return found, scanned


def test_the_sweep_actually_reached_the_tree() -> None:
    """Discovery floors. An empty walk reports clean having asserted nothing.

    Every floor here guards a different way the sweep can go quietly blind: the
    file count catches a skip list eating the tree, the requirements count
    catches a declaration oracle that found nothing (which would make *every*
    third-party import a finding), and the roots catch a layout rename.
    """
    _, scanned = _unresolvable()
    assert scanned > 200, f"only walked {scanned} python files — the skip list is eating the tree"
    assert _REQUIREMENTS_FILES >= 15, (
        f"only read {_REQUIREMENTS_FILES} requirements/pyproject files — the "
        "declaration oracle has gone blind and would report false findings"
    )
    assert len(_DECLARED) > 100, f"only {len(_DECLARED)} declared distributions found"
    for root in _ROOTS:
        assert root.is_dir(), f"first-party root {root} no longer exists — resolution is wrong"


def test_every_import_under_shared_scripts_resolves() -> None:
    """The #14518 defect: an F821-clean script that dies on its own import block."""
    found, scanned = _unresolvable()
    assert scanned > 200, f"only walked {scanned} python files — this would pass vacuously"
    offenders = [
        f"{rel}:{line}  {module}"
        for rel, module, line in found
        if (rel, module) not in _KNOWN_BROKEN
    ]
    assert not offenders, (
        "these imports name a module that does not resolve against any "
        "first-party root, the stdlib, the declared requirements, or the "
        "importing file's own directory. The script cannot run at all — it "
        "raises ModuleNotFoundError before reaching its first statement "
        "(#14518):\n  " + "\n  ".join(offenders)
    )


# A name no distribution and no first-party module can plausibly carry. Kept as
# one constant so the positive controls below cannot drift apart from each other.
_NEVER_EXISTS = "autobot_module_that_does_not_exist_14518"


@pytest.mark.parametrize(
    "source,expected",
    [
        (f"from {_NEVER_EXISTS} import thing\n", _NEVER_EXISTS),
        (f"import {_NEVER_EXISTS}\n", _NEVER_EXISTS),
        (f"from {_NEVER_EXISTS}.sub.pkg import thing\n", f"{_NEVER_EXISTS}.sub.pkg"),
    ],
)
def test_the_detector_still_fires_on_a_synthetic_import(source: str, expected: str) -> None:
    """Positive control, replacing the emptied ``_KNOWN_BROKEN`` parametrization.

    While that allowlist held live defects, "the sweep still reports these six"
    proved the matcher worked. It is empty now — the goal state — so nothing in
    this file would notice a matcher that stopped matching: the sweep counts
    findings, and zero findings is exactly what a clean tree looks like too.

    Both import spellings are driven, because the tree contains both and a
    branch that silently stops matching one of them halves this guard's reach
    without changing a single assertion's outcome.
    """
    hits = _unresolvable_in_source(source, _SCRIPTS)
    assert hits, f"the detector no longer flags {source.strip()!r}"
    assert hits[0][0] == expected
    assert hits[0][1] == 1


@pytest.mark.parametrize(
    "source",
    [
        "import json\n",
        "from autobot_shared.logging_manager import get_logger\n",
        "import redis\n",
        f"try:\n    import {_NEVER_EXISTS}\nexcept ImportError:\n    pass\n",
    ],
)
def test_the_detector_does_not_fire_on_a_legitimate_import(source: str) -> None:
    """Negative control: stdlib, first-party, declared third-party, and guarded-optional.

    Without this a detector that flagged *everything* would satisfy the positive
    control above while making the sweep useless — and the pressure would then
    be to switch the guard off rather than fix it.
    """
    assert not _unresolvable_in_source(source, _SCRIPTS), f"{source.strip()!r} is legitimate and must not be flagged"


@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_BROKEN.items()))
def test_each_exemption_is_still_broken(entry: tuple[str, str], issue: str) -> None:
    """An exemption that no longer applies exempts nothing, silently.

    This is also the positive control for the whole file. If the sweep stopped
    finding these six known-bad sites, every test above would go green while
    checking nothing — so "the detector still fires" is asserted here rather
    than assumed.
    """
    rel, module = entry
    path = _SCRIPTS / rel
    assert path.is_file(), f"{rel} moved or was deleted — update or drop this exemption ({issue})"
    assert not _resolves(module, path.parent), (
        f"{module} now resolves for {rel}, so the exemption ({issue}) is obsolete — "
        "remove it from _KNOWN_BROKEN so the import is guarded again"
    )
    found, _ = _unresolvable()
    assert any(r == rel and m == module for r, m, _ in found), (
        f"the sweep no longer reports {rel} -> {module}, but the module still does "
        f"not resolve. The detector has regressed and is now reporting clean on a "
        f"live defect ({issue})"
    )
