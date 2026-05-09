#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pre-commit hook: enforce @router.* / @with_error_handling decorator order.

In Python ``@A @B def f`` is equivalent to ``f = A(B(f))``. With
``@with_error_handling`` placed ABOVE ``@router.*``, FastAPI's router
registers the raw, un-wrapped function — the error wrapper never runs.
This was the codebase-wide dead-code pattern fixed in #6558 (1801 swaps
across 188 files).

A second variant (#6633) is two ``@with_error_handling`` decorators
stacked on the same function — the outer one wraps the inner wrapper,
producing a duplicate logging path and identical error envelope.

This hook blocks both regressions:

  * **Pattern A (decorator order)** — ``@with_error_handling(...)``
    immediately above ``@router.*(...)``.
  * **Pattern B (stacked duplicate)** — two adjacent
    ``@with_error_handling(...)`` decorators on the same function.

Scan target:
  ``autobot-backend/api/**/*.py``

Exit codes:
  0 — clean
  1 — violations found

Background: #6558 (decorator order codebase-wide fix), #6633 (stacked
duplicates), #6638 (this hook).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

HOOK_ID = "decorator-order"


def _is_target_file(path: Path, repo_root: Path) -> bool:
    """Return True if *path* should be scanned. Restricted to autobot-backend/api/**/*.py."""
    try:
        rel = path.resolve().relative_to(repo_root)
    except ValueError:
        return False
    parts = rel.parts
    if len(parts) < 3 or parts[0] != "autobot-backend" or parts[1] != "api":
        return False
    return path.suffix == ".py"


def _decorator_name(deco: ast.expr) -> str:
    """Best-effort fully-qualified name of a decorator node.

    Handles:
      @foo                          -> "foo"
      @foo.bar                      -> "foo.bar"
      @foo(...)                     -> "foo"
      @foo.bar(...)                 -> "foo.bar"
    """
    target = deco.func if isinstance(deco, ast.Call) else deco
    parts: List[str] = []
    node: ast.expr | None = target
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _is_with_error_handling(deco: ast.expr) -> bool:
    return _decorator_name(deco) == "with_error_handling"


def _is_router_decorator(deco: ast.expr) -> bool:
    name = _decorator_name(deco)
    # Matches @router.get / @router.post / @router.api_route / etc., plus
    # rarer @app.get / @app.post forms.
    if name.startswith("router."):
        return True
    if name.startswith("app.") and name.split(".", 1)[1] in {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "options",
        "api_route",
        "websocket",
    }:
        return True
    return False


def _function_violations(node: ast.AST) -> List[Tuple[int, str, str]]:
    """Return [(lineno, kind, message)] for each decorator-order issue on *node*.

    *node* is expected to be a FunctionDef / AsyncFunctionDef.
    """
    decos = getattr(node, "decorator_list", None)
    if not decos:
        return []

    hits: List[Tuple[int, str, str]] = []

    # Pattern A: @with_error_handling immediately above @router.* (or app.*).
    # In ``decorator_list`` index 0 is the OUTERMOST decorator (top-most
    # ``@`` in source). For correct order, @router.* must be at a smaller
    # index than @with_error_handling.
    for i, deco in enumerate(decos):
        if not _is_with_error_handling(deco):
            continue
        # Look for any @router.* later in the list (i.e. closer to the function).
        for j in range(i + 1, len(decos)):
            if _is_router_decorator(decos[j]):
                func_name = getattr(node, "name", "<unknown>")
                hits.append(
                    (
                        deco.lineno,
                        "order",
                        (
                            f"@with_error_handling is above @{_decorator_name(decos[j])} "
                            f"on '{func_name}'. Swap so @router.* is OUTERMOST "
                            f"(above @with_error_handling) — see #6558."
                        ),
                    )
                )
                break

    # Pattern B: two adjacent @with_error_handling decorators (stacked dup).
    for i in range(len(decos) - 1):
        if _is_with_error_handling(decos[i]) and _is_with_error_handling(decos[i + 1]):
            func_name = getattr(node, "name", "<unknown>")
            hits.append(
                (
                    decos[i].lineno,
                    "stacked",
                    (
                        f"Two adjacent @with_error_handling decorators on '{func_name}'. "
                        f"Remove the duplicate — see #6633."
                    ),
                )
            )

    return hits


def _check_file(path: Path, repo_root: Path) -> List[Tuple[int, str, str]]:
    if not _is_target_file(path, repo_root):
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    hits: List[Tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hits.extend(_function_violations(node))
    return hits


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
    total_order = 0
    total_stacked = 0
    for path in files:
        hits = _check_file(path, repo_root)
        if not hits:
            continue
        try:
            rel = path.resolve().relative_to(repo_root)
        except ValueError:
            rel = path
        for line_no, kind, message in hits:
            print(f"[{HOOK_ID}] {rel}:{line_no}: {message}", file=sys.stderr)
            if kind == "order":
                total_order += 1
            elif kind == "stacked":
                total_stacked += 1
    if total_order or total_stacked:
        print(
            f"\n[{HOOK_ID}] {total_order} decorator-order violation(s), "
            f"{total_stacked} stacked-duplicate violation(s).\n"
            f"  Fix: ensure @router.* is OUTERMOST (top-most), with "
            f"@with_error_handling immediately below it. Remove any duplicate "
            f"@with_error_handling stacks. See #6558 / #6633 for context.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
