# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend-only top-level import names, derived from the tree (#18288).

Shared by the infrastructure import guards (``infra_scripts_no_backend_imports_18288_test`` and
``infra_monitoring_import_path_15643_test``) so both judge "backend-only" by one derivation: every
top-level module or package tracked under ``autobot-backend/``, minus the standard library and minus
any name the repository root also provides (``tools``, ``scripts``, ...), because an infra import of
those may mean the root's.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path, PurePosixPath

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

BACKEND_ROOT = "autobot-backend"


def tracked_py(root: Path, *trees: str) -> list[str]:
    """Tracked ``.py`` paths under *trees*, or ``[]`` on an empty tree (never raises)."""
    try:
        return [rel for rel in tracked_paths(root, *trees) if rel.endswith(".py")]
    except EmptyEnumeration:
        return []


def top_level_names(paths: list[str], prefix: str) -> set[str]:
    """First path component under *prefix* of each python file: a module stem or a package dir."""
    names = set()
    for rel in paths:
        parts = PurePosixPath(rel).relative_to(prefix).parts if prefix else PurePosixPath(rel).parts
        names.add(parts[0].removesuffix(".py"))
    return names


def dir_names(directory: Path) -> set[str]:
    """What *directory* provides on ``sys.path``: its modules and its python-bearing subdirectories."""
    if not directory.is_dir():
        return set()
    packages = {
        d.name for d in directory.iterdir() if d.is_dir() and not d.name.startswith(".") and any(d.glob("*.py"))
    }
    return packages | {p.stem for p in directory.glob("*.py")}


@functools.lru_cache(maxsize=1)
def backend_only_names() -> frozenset[str]:
    """Top-level backend names an infra module cannot resolve without the backend on its path."""
    root = repo_root()
    backend = top_level_names(tracked_py(root, BACKEND_ROOT), BACKEND_ROOT)
    return frozenset(backend - dir_names(root) - set(sys.stdlib_module_names) - {"__init__"})
