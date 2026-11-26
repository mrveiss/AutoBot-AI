# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical AST detector for a top-level ``if __name__ == "__main__":`` block (#22199).

One implementation for every guard, audit and test that asks "is this module launchable?".
"""

from __future__ import annotations

import ast


def is_name_eq_main(test: ast.expr) -> bool:
    """True only for ``__name__ == "__main__"`` -- not ``!=``, ``in``, or another constant."""
    if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    return isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__"


def is_main_guard(node: ast.stmt) -> bool:
    """True when ``node`` is an ``if __name__ == "__main__":`` statement."""
    return isinstance(node, ast.If) and is_name_eq_main(node.test)


def has_main_guard(tree: ast.Module) -> bool:
    """True when a top-level statement is the main guard (a docstring example is not)."""
    return any(is_main_guard(n) for n in tree.body)


def source_has_main_guard(source: str) -> bool:
    """``has_main_guard`` for source text; an unparsable file has no guard that could be read."""
    try:
        return has_main_guard(ast.parse(source))
    except (SyntaxError, ValueError):
        return False
