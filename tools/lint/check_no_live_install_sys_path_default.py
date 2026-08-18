#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-aware regression check for #14544 — no ``sys.path`` bootstrap may
default to the live deployed install.

18 call sites across 17 files open-coded the project root instead of using
the canonical resolver::

    sys.path.insert(0, os.environ.get("AUTOBOT_PROJECT_ROOT", "/opt/autobot/code_source"))

That is ``autobot_shared.paths.project_root()`` reinvented without its walk:
with ``AUTOBOT_PROJECT_ROOT`` unset — the normal case in a checkout — it puts
the **live deployed install** first on ``sys.path``, so a script run from a
working tree silently imports the deployed copy of every first-party module
it names. #14544 fixed all 18 by routing them through
``autobot_shared.paths.project_root()`` instead.

This checker inspects the AST of every ``sys.path.insert(...)`` /
``sys.path.append(...)`` call: if any argument is a call to
``os.environ.get``/``os.getenv`` whose default string contains the live
install path, it is the same defect regrowing. There is no exemption list —
none of the 18 fixed sites needed to keep the pattern, and a fresh site
copying it forward is never legitimate.

Exit code:
  0 — clean
  1 — a live-install default found inside a ``sys.path`` mutation
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple

# tools/lint/ is not a Python package; ensure sibling module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

#: The live-install root, assembled from fragments so this checker's own
#: source (and its docstring above) does not trip the pattern it detects.
LIVE_INSTALL_ROOT = "/" + "opt/autobot"

#: The canonical replacement every finding is told to use.
RESOLVER = "autobot_shared.paths.project_root()"

ALLOWLIST: frozenset[str] = frozenset(
    {
        "tools/lint/check_no_live_install_sys_path_default.py",
        "tools/lint/check_no_live_install_sys_path_default_test.py",
    }
)


def _is_sys_path_mutation(func: ast.AST) -> bool:
    """True for ``sys.path.insert(...)`` / ``sys.path.append(...)``."""
    return (
        isinstance(func, ast.Attribute)
        and func.attr in ("insert", "append")
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "path"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "sys"
    )


def _is_env_lookup(func: ast.AST) -> bool:
    """True for ``os.environ.get(...)`` / ``os.getenv(...)``, matched exactly."""
    if isinstance(func, ast.Attribute) and func.attr == "getenv" and isinstance(func.value, ast.Name):
        return func.value.id == "os"
    if isinstance(func, ast.Attribute) and func.attr == "get" and isinstance(func.value, ast.Attribute):
        return (
            func.value.attr == "environ"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
        )
    return False


def _default_names_live_install(call: ast.Call) -> bool:
    """True if an ``os.environ.get``/``os.getenv`` call's default is the live install."""
    if len(call.args) < 2:
        return False
    default = call.args[1]
    return (
        isinstance(default, ast.Constant)
        and isinstance(default.value, str)
        and LIVE_INSTALL_ROOT in default.value
    )


def live_install_default_sites(path: Path) -> List[Tuple[int, str]]:
    """Every ``sys.path`` mutation in *path* defaulting to the live install."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_sys_path_mutation(node.func):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Call) and _is_env_lookup(arg.func) and _default_names_live_install(arg):
                hits.append((node.lineno, ast.unparse(node)))
    return sorted(hits)


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    total = 0
    for path in iter_python_files(argv[1:], repo_root):
        try:
            rel = str(path.resolve().relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        if rel in ALLOWLIST:
            continue
        try:
            hits = live_install_default_sites(path)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for line_no, text in hits:
            print(
                f"[no-live-install-sys-path-default] {rel}:{line_no}: {text} — "
                f"defaults to the live deployed install; use {RESOLVER} instead (#14544)",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"\n[no-live-install-sys-path-default] {total} sys.path bootstrap(s) "
            "still default to the live install. See per-line fix suggestions above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
