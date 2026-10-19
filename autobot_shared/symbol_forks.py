# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The symbol-fork detector, importable by both its callers (#18067, #17312).

``tools/lint/check_symbol_forks.py`` (the CI ratchet) and the codebase-analytics
cross-file pass both ask the same question -- *which names are bound at module
level in two or more files?* -- and must give the same number. They used to be
unable to: the detector lived in a lint script that the backend cannot import
(``autobot-backend/tools/__init__.py`` pins ``tools`` to its own directory), so
the dashboard had no fork count at all and a second implementation would have
been the very defect being measured.

This module is the pure half: no argparse, no baseline, no printing, no
repo-root global. Everything takes the ``root`` it reads from. The boundary
(population, predicate, blind spots) is documented in ``check_symbol_forks``,
which keeps the CLI, the baseline and the ratchet.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

#: Top-level directories of AutoBot's own tree that the ratchet counts.
FORK_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")

#: Directory parts that take a file out of the population entirely.
FORK_EXCLUDED_PARTS = frozenset({"__pycache__", "node_modules", "venv", ".venv", "migrations", "alembic"})

#: Names whose repetition across modules is the intended design, not a fork.
FORK_EXCLUDED_NAMES = frozenset({"main", "upgrade", "downgrade", "migrate"})

_GIT_LS_FILES_TIMEOUT_SECONDS = 60


@dataclass
class ForkDefinition:
    """One module-level binding of a name."""

    path: str
    lineno: int
    kind: str
    body_statements: int
    #: True for ``class N(<shared N>)``: a binding of the shared definition, not a second one.
    binds_shared: bool = False


@dataclass
class ForkCluster:
    """One name, defined at module level in two or more files."""

    name: str
    definitions: list[ForkDefinition] = field(default_factory=list)

    @property
    def kinds(self) -> set[str]:
        return {d.kind for d in self.definitions}

    @property
    def drifted(self) -> bool:
        """Different body sizes mean the copies are not the same text any more."""
        return len({d.body_statements for d in self.definitions}) > 1


@dataclass
class ForkScan:
    """What a sweep saw, so a zero can be told from "did not look".

    ``listed`` is what git enumerated, ``parsed`` is what was actually read.
    ``clusters`` is only a claim about the ``parsed`` files.
    """

    clusters: dict[str, ForkCluster]
    parsed: int
    listed: int


def fork_is_test_file(path: Path) -> bool:
    """Tests legitimately redefine names: fixtures, fakes, back-compat shims."""
    name = path.name
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py" or "tests" in path.parts


def fork_in_population(path: Path) -> bool:
    """The declared boundary, in one place so every caller shares it."""
    if FORK_EXCLUDED_PARTS & set(path.parts):
        return False
    return not fork_is_test_file(path)


def fork_is_route_handler(node: ast.AST) -> bool:
    """True for ``@router.get(...)``-style decorators (a route name is router-local)."""
    for dec in getattr(node, "decorator_list", []):
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in ("router", "app", "api_router"):
                return True
    return False


#: The package whose definitions a same-name subclass is a binding of.
FORK_SHARED_PACKAGE = "autobot_shared"


def _fork_import_targets(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted target for every module-level import (aliases resolved)."""
    targets: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                targets[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                targets[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
    return targets


def _fork_dotted(expr: ast.expr, targets: dict[str, str]) -> str:
    """Dotted path ``expr`` refers to through the file's imports, or ``""``."""
    if isinstance(expr, ast.Name):
        return targets.get(expr.id, "")
    if isinstance(expr, ast.Attribute):
        head = _fork_dotted(expr.value, targets)
        return f"{head}.{expr.attr}" if head else ""
    return ""


def fork_binds_shared(node: ast.ClassDef, targets: dict[str, str]) -> bool:
    """True if ``node`` subclasses the SAME-NAMED class imported from ``autobot_shared``.

    A subclass of the shared definition is a binding of it, not a second
    definition (#17312): ``class UserService(SharedUserService)`` adds hooks to
    the one implementation. A same-name class with any other base, or with a
    same-name base from outside the shared package, is still a fork.
    """
    for base in node.bases:
        dotted = _fork_dotted(base, targets)
        if dotted.startswith(f"{FORK_SHARED_PACKAGE}.") and dotted.rsplit(".", 1)[-1] == node.name:
            return True
    return False


_BINDINGS = {ast.FunctionDef: "function", ast.AsyncFunctionDef: "function", ast.ClassDef: "class"}


def fork_definitions_in(path: Path, root: Path) -> "list[tuple[str, ForkDefinition]] | None":
    """Module-level class/def bindings of ``root/path``; ``None`` if unreadable.

    ``None`` is "could not read this file", a different fact from ``[]`` ("read
    it and it defines nothing"): the reach count below counts successful parses.
    """
    try:
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
    except (SyntaxError, OSError, ValueError):
        return None
    targets = _fork_import_targets(tree)
    found = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_") or node.name in FORK_EXCLUDED_NAMES or fork_is_route_handler(node):
            continue
        kind = _BINDINGS[type(node)]
        binds = isinstance(node, ast.ClassDef) and fork_binds_shared(node, targets)
        found.append((node.name, ForkDefinition(str(path), node.lineno, kind, len(node.body), binds)))
    return found


def fork_find_clusters(paths: list[Path], root: Path) -> ForkScan:
    """Group module-level definitions by name; keep those bound in >=2 files.

    Reports the number of files successfully PARSED as well, because a floor on
    what git listed would clear even if every parse failed.
    """
    by_name: dict[str, list[ForkDefinition]] = defaultdict(list)
    parsed = 0
    for path in paths:
        if not fork_in_population(path):
            continue
        found = fork_definitions_in(path, root)
        if found is None:
            continue
        parsed += 1
        for name, definition in found:
            if definition.binds_shared:
                continue
            by_name[name].append(definition)
    clusters = {
        name: ForkCluster(name, sorted(defs, key=lambda d: (d.path, d.lineno)))
        for name, defs in by_name.items()
        if len({d.path for d in defs}) > 1
    }
    return ForkScan(clusters=clusters, parsed=parsed, listed=len(paths))


def fork_tracked_python_files(root: Path, roots: tuple[str, ...] = FORK_ROOTS) -> list[Path]:
    """Git-tracked ``.py`` files under ``roots`` of ``root``, repo-relative.

    ``git ls-files`` rather than a walk (untracked scratch is not the tree),
    anchored with ``cwd=root`` and run under ``scrubbed_git_env`` so an ambient
    ``GIT_DIR`` cannot make it answer for another checkout (#14896, #15176).
    The pathspecs are the roots only: a ``<root>/**/*.py`` glob misses files
    sitting directly in a root, so the extension is filtered here.

    Raises:
        RuntimeError: git failed or listed nothing -- an empty list would read
            downstream as a clean tree.
    """
    proc = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "-z", "--", *roots],
        cwd=root,
        env=scrubbed_git_env(),
        capture_output=True,
        timeout=_GIT_LS_FILES_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git ls-files failed (exit {proc.returncode}): {detail}")
    names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n.endswith(".py")]
    if not names:
        raise RuntimeError(f"git ls-files listed no .py files under {list(roots)}")
    return [Path(n) for n in names]


def scan_symbol_forks(root: Path, roots: tuple[str, ...] = FORK_ROOTS) -> ForkScan:
    """Enumerate and sweep ``root`` -- the one entry point both callers use."""
    return fork_find_clusters(fork_tracked_python_files(root, roots), root)
