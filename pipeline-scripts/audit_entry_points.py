#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Entry-point predicates for the unwired-tracker audit (#22199).

A module that is launched (``python -m pkg.mod``, ``__main__.py``, a benchmark) is reached in
production without ever being imported, so the import-grep in ``audit_unwired_trackers`` reports it
as unwired. These predicates are deliberately narrow: a bare ``if __name__ == "__main__"`` block does
NOT qualify, because many libraries carry a demo block and are still unwired.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

# Repo-root directories searched for callers but never scanned for findings.
CALLER_ONLY_DIRS = ("scripts",)
BENCHMARK_DIR_NAME = "benchmarks"
BENCHMARK_FILE_SUFFIXES = ("_benchmark.py", "_benchmarks.py")
MAIN_BLOCK_RE = re.compile(r"^if\s+__name__\s*==\s*[\"']__main__[\"']\s*:", re.MULTILINE)
MODULE_RUN_RE = re.compile(r"\bpython(?:3(?:\.\d+)?)?\s+-m\s+([A-Za-z_][\w.]*)")


def is_package_main(path: Path) -> bool:
    """``__main__.py`` is run by ``python -m <package>``, never imported."""
    return path.name == "__main__.py"


def is_benchmark(path: Path) -> bool:
    """A file under a ``benchmarks/`` segment, or named ``*_benchmark(s).py``."""
    if path.suffix != ".py":
        return False
    return BENCHMARK_DIR_NAME in path.parts[:-1] or path.name.endswith(BENCHMARK_FILE_SUFFIXES)


def _read_module(path: Path) -> tuple[str, str]:
    """Return ``(module docstring, source)``; both empty when the file cannot be read or parsed."""
    try:
        source = path.read_text(encoding="utf-8")
        return ast.get_docstring(ast.parse(source)) or "", source
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return "", ""


def documents_own_module_run(path: Path, module_path: Optional[str]) -> bool:
    """True when the docstring documents ``python -m <own dotted path>`` AND the module has a main block.

    The main-block requirement keeps a documented-but-not-runnable module counted as unwired.
    """
    if not module_path or path.suffix != ".py":
        return False
    doc, source = _read_module(path)
    return module_path in MODULE_RUN_RE.findall(doc) and bool(MAIN_BLOCK_RE.search(source))


def is_launched_module(path: Path, module_path: Optional[str]) -> bool:
    """Any of the launcher forms: ``__main__.py``, a benchmark, or a self-documented ``python -m``."""
    return is_package_main(path) or is_benchmark(path) or documents_own_module_run(path, module_path)
