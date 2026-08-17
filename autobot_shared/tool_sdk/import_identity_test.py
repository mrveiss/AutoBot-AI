# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import-identity guard for the tool SDK (#14373).

``autobot_shared/tool_sdk/``'s internals used to import each other by a bare
top-level name (``from tool_sdk.base import ...``), which raised
``ModuleNotFoundError: No module named 'tool_sdk'`` the moment the package was
reached through its real, importable path — ``autobot_shared.tool_sdk`` — as
it was when an LLC service added a module-level import and took the whole
feature router down.

The bare name is also dangerous in a way an ImportError is not: reached
through a namespace-package fallback (this suite's own ``pytest.ini`` puts
``autobot_shared/`` itself on ``sys.path`` for unrelated legacy reasons), it
loads the SAME files a second time under a SECOND module identity, and
``get_tool_registry()``'s module-level singleton is per-identity. A tool
registered through one identity is invisible through the other, and every
lookup silently reports "unknown tool" while the real registry is healthy —
far harder to notice than an ImportError.

The fix converts every internal import to relative (``from .base import``)
and every call site in the repository from the bare ``tool_sdk`` name to the
fully-qualified ``autobot_shared.tool_sdk`` path. The bare name is not kept as
a supported alias. These tests guard both halves of that: nothing may
reintroduce the bare import (static scan), and the singleton stays reachable
through exactly one identity even in a clean process shaped like production,
not like this test suite (subprocess).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from autobot_shared.paths import project_root
from autobot_shared.tool_sdk import get_tool_registry as reexported_get_tool_registry
from autobot_shared.tool_sdk.registry import get_tool_registry

# Directories that never hold first-party source under review here: other
# agents' worktrees, VCS internals, caches, and vendored/build output. Mirrors
# pytest.ini's `norecursedirs` plus this repo's own worktree convention.
_EXCLUDED_DIR_NAMES = {
    ".git",
    ".worktrees",
    ".claude",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}


def _iter_repo_python_files(root: Path):
    """Yield every first-party ``.py`` file under *root*, skipping non-source dirs.

    Checks exclusions against the path *relative to root*, not the absolute
    path: this repo's whole workflow runs from `.worktrees/<name>/` checkouts,
    so an absolute-path check would match `.worktrees` on every single file
    here and exclude the entire tree, silently turning the scan into a no-op
    that always reports zero offenders.
    """
    for path in root.rglob("*.py"):
        if _EXCLUDED_DIR_NAMES.intersection(path.relative_to(root).parts):
            continue
        yield path


def _bare_tool_sdk_imports(path: Path) -> List[str]:
    """Return every bare ``tool_sdk`` import statement found in *path*.

    Parses with ``ast`` rather than matching text, so a comment or docstring
    mentioning ``tool_sdk`` — this package's own module docstrings do, by
    necessity, explaining exactly why the bare form is unsupported — is never
    mistaken for an import statement.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tool_sdk" or alias.name.startswith("tool_sdk."):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module == "tool_sdk" or module.startswith("tool_sdk."):
                hits.append(module)
    return hits


class TestNoBareTopLevelImport:
    """Regression guard: nothing in the repo may import the bare ``tool_sdk`` name."""

    def test_no_bare_tool_sdk_imports_in_repo(self) -> None:
        offenders: Dict[str, List[str]] = {}
        for path in _iter_repo_python_files(project_root()):
            hits = _bare_tool_sdk_imports(path)
            if hits:
                offenders[str(path)] = hits

        assert not offenders, (
            "Bare `tool_sdk` imports reintroduce the #14373 dual-identity "
            f"hazard — use `autobot_shared.tool_sdk` instead: {offenders}"
        )


class TestSingleImportIdentity:
    """The registry singleton is reachable through exactly one module identity."""

    def test_singleton_identical_via_module_and_package_reexport(self) -> None:
        """`autobot_shared.tool_sdk.get_tool_registry` re-exports the exact same
        function object as `autobot_shared.tool_sdk.registry.get_tool_registry`
        — not merely an equal one — because `__init__.py` now imports it with a
        relative (`from .registry import ...`), which binds a second name to the
        same module rather than loading a second copy.
        """
        assert reexported_get_tool_registry is get_tool_registry
        assert reexported_get_tool_registry() is get_tool_registry()

    def test_clean_process_shaped_like_production_has_no_bare_identity(self) -> None:
        """Reproduces production's import shape: repo root on `PYTHONPATH`, NOT
        `autobot_shared/` itself (this suite's `pytest.ini` adds the latter for
        unrelated legacy bare-name tests — see its own comment). That gap is
        exactly what raised `ModuleNotFoundError: No module named 'tool_sdk'`
        for the LLC router in PR #14357 (#14373), so the regression check has to
        run in a process that does not have pytest's convenience path.
        """
        root = project_root()
        script = (
            "import sys\n"
            "import autobot_shared.tool_sdk.registry as m\n"
            "import autobot_shared.tool_sdk as pkg\n"
            "assert pkg.get_tool_registry() is m.get_tool_registry(), 'registry forked'\n"
            "bare = [n for n in sys.modules if n == 'tool_sdk' or n.startswith('tool_sdk.')]\n"
            "assert not bare, f'bare tool_sdk identity leaked into sys.modules: {bare}'\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(root),
            env={**os.environ, "PYTHONPATH": str(root)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "OK"
