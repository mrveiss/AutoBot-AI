# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one arithmetic-CAPTCHA evaluator (#18131).

Both CAPTCHA solvers read an expression such as ``3 + 4 = ?`` off a page or an OCR scan.
``eval()`` is never used: a regex captures two integers and an operator.
"""

from __future__ import annotations

import re
from typing import Callable

#: Matches "3 + 4", "12 - 5", "7 x 2", "8 / 2". ``x``/``X`` is multiplication. Both cases are
#: needed: ``clean_math_expression`` upper-cases, while a detector may apply it to lower-cased HTML.
MATH_EXPR_RE = re.compile(r"(\d+)\s*([+\-*/×÷xX])\s*(\d+)")
_TRAILING_EQUALS_RE = re.compile(r"\s*[=?]+\s*$")

_OPERATORS: dict[str, Callable[[int, int], int | None]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "×": lambda a, b: a * b,
    "x": lambda a, b: a * b,
    "/": lambda a, b: a // b if b != 0 else None,
    "÷": lambda a, b: a // b if b != 0 else None,
}

_SPELLED_OPERATORS = (("PLUS", "+"), ("MINUS", "-"), ("TIMES", "*"), ("DIVIDED BY", "/"))


def clean_math_expression(expression: str) -> str:
    """Upper-case, drop a trailing ``= ?`` and normalise spelled-out operators."""
    cleaned = _TRAILING_EQUALS_RE.sub("", expression.upper())
    for old, new in _SPELLED_OPERATORS:
        cleaned = cleaned.replace(old, new)
    return cleaned


def solve_math_expression(expression: str) -> int | None:
    """The integer value of the first ``a <op> b`` in `expression`, else ``None``.

    Division is floor division; division by zero and an unknown operator give ``None``.
    """
    match = MATH_EXPR_RE.search(clean_math_expression(expression))
    if not match:
        return None
    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    operation = _OPERATORS.get(op.lower()) or _OPERATORS.get(op)
    return operation(a, b) if operation else None
