#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

``--fix`` mode (opt-in):
  Pass ``--fix`` to auto-correct violations in place using libcst.
  Requires ``pip install libcst``.  The pre-commit hook entry stays
  check-only (no ``--fix``) so CI never silently mutates files.

Background: #6558 (decorator order codebase-wide fix), #6633 (stacked
duplicates), #6638 (this hook), #6787 (--fix mode).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

try:
    import libcst as cst

    _LIBCST_AVAILABLE = True
except ImportError:
    _LIBCST_AVAILABLE = False

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


# ---------------------------------------------------------------------------
# libcst-based fix helpers
# ---------------------------------------------------------------------------


def _cst_decorator_name(deco: "cst.Decorator") -> str:
    """Best-effort fully-qualified name of a libcst Decorator node."""
    node = deco.decorator
    if isinstance(node, cst.Call):
        node = node.func
    parts: List[str] = []
    while isinstance(node, cst.Attribute):
        parts.append(node.attr.value)
        node = node.value
    if isinstance(node, cst.Name):
        parts.append(node.value)
        return ".".join(reversed(parts))
    return ""


def _cst_is_with_error_handling(deco: "cst.Decorator") -> bool:
    return _cst_decorator_name(deco) == "with_error_handling"


def _cst_is_router_decorator(deco: "cst.Decorator") -> bool:
    name = _cst_decorator_name(deco)
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


if _LIBCST_AVAILABLE:

    class _DecoratorOrderFixer(cst.CSTTransformer):
        """CST transformer that fixes Pattern A (order) and Pattern B (stacked)."""

        def __init__(self) -> None:
            self.fix_count = 0

        def _fix_decorator_list(
            self,
            decorators: Sequence["cst.Decorator"],
        ) -> Tuple[Sequence["cst.Decorator"], int]:
            """Return (new_decorators, fixes_applied) after correcting violations."""
            decos = list(decorators)
            fixes = 0
            changed = True

            while changed:
                changed = False

                # Pattern B first: remove the outer (earlier) duplicate @with_error_handling.
                for i in range(len(decos) - 1):
                    if _cst_is_with_error_handling(decos[i]) and _cst_is_with_error_handling(decos[i + 1]):
                        removed = decos.pop(i)
                        survivor = decos[i]
                        # Transfer leading_lines from removed (outer) to survivor so
                        # any blank lines before the block are preserved.
                        combined = tuple(removed.leading_lines) + tuple(survivor.leading_lines)
                        decos[i] = survivor.with_changes(leading_lines=combined)
                        fixes += 1
                        changed = True
                        break

                # Pattern A: swap @with_error_handling (at i) with @router.* (at j > i).
                for i, deco in enumerate(decos):
                    if not _cst_is_with_error_handling(deco):
                        continue
                    for j in range(i + 1, len(decos)):
                        if _cst_is_router_decorator(decos[j]):
                            weh = decos[i]
                            router = decos[j]
                            # Router moves to position i — inherits weh's leading_lines.
                            decos[i] = router.with_changes(leading_lines=weh.leading_lines)
                            # weh moves to position j — inherits router's leading_lines.
                            decos[j] = weh.with_changes(leading_lines=router.leading_lines)
                            fixes += 1
                            changed = True
                            break
                    if changed:
                        break

            return tuple(decos), fixes

        def leave_FunctionDef(
            self,
            original_node: "cst.FunctionDef",
            updated_node: "cst.FunctionDef",
        ) -> "cst.FunctionDef":
            new_decos, count = self._fix_decorator_list(updated_node.decorators)
            self.fix_count += count
            if count:
                return updated_node.with_changes(decorators=new_decos)
            return updated_node

        def leave_AsyncFunctionDef(
            self,
            original_node: "cst.AsyncFunctionDef",
            updated_node: "cst.AsyncFunctionDef",
        ) -> "cst.AsyncFunctionDef":
            new_decos, count = self._fix_decorator_list(updated_node.decorators)
            self.fix_count += count
            if count:
                return updated_node.with_changes(decorators=new_decos)
            return updated_node


def _fix_file(path: Path, repo_root: Path) -> int:
    """Fix decorator-order violations in *path* using libcst.

    Returns the number of fixes applied (0 if none).
    Exits with code 1 if libcst is not installed.
    """
    if not _LIBCST_AVAILABLE:
        print(
            f"[{HOOK_ID}] --fix requires libcst.  Install with: pip install libcst",
            file=sys.stderr,
        )
        sys.exit(1)

    if not _is_target_file(path, repo_root):
        return 0

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return 0

    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return 0

    fixer = _DecoratorOrderFixer()
    new_module = module.visit(fixer)

    if fixer.fix_count == 0:
        return 0

    path.write_text(new_module.code, encoding="utf-8")

    # Verify no violations remain after the fix.
    remaining = _check_file(path, repo_root)
    if remaining:
        print(
            f"[{HOOK_ID}] WARNING: {len(remaining)} violation(s) remain in {path} "
            f"after auto-fix — manual review needed.",
            file=sys.stderr,
        )

    return fixer.fix_count


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description="Check (or fix) @router.* / @with_error_handling decorator order.",
        add_help=False,
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix violations in place using libcst (requires: pip install libcst).",
    )
    args, remaining = parser.parse_known_args(argv[1:])
    files = list(iter_python_files(remaining, repo_root))

    if args.fix:
        total_fixes = 0
        for path in files:
            total_fixes += _fix_file(path, repo_root)
        if total_fixes:
            print(
                f"[{HOOK_ID}] Applied {total_fixes} fix(es).",
                file=sys.stderr,
            )
        # Final validation pass — exit 1 only if violations couldn't be fixed.
        unfixed = sum(len(_check_file(p, repo_root)) for p in files)
        return 1 if unfixed else 0

    # Check-only path (default, used by pre-commit hook).
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
            f"@with_error_handling stacks. See #6558 / #6633 for context.\n"
            f"  Auto-fix: run with --fix (requires pip install libcst).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
