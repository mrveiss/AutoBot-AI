# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18131 -- MATH captchas are solved through the one evaluator, ``services.captcha_math``.

Before, each solver carried its own copy (operator table, cleaner, regex). They disagreed:
the OCR solver's copy had no ``DIVIDED BY`` handling, so ``8 DIVIDED BY 2 = ?`` returned
``None`` there while the browser solver answered ``4``. These tests pin the routing (a spy on
the one function) and the agreement (both solvers, same answers), keyed on ``CaptchaType.MATH``
from ``autobot_shared.captcha_types``.
"""

import ast
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from agents.browser import captcha_solver as browser_solver
from autobot_shared.captcha_types import CaptchaType
from services import captcha_math
from services import captcha_solver as ocr_solver

_BACKEND = Path(__file__).resolve().parents[1]
_SOLVER_FILES = ("services/captcha_solver.py", "agents/browser/captcha_solver.py")
#: Per-solver copies of the evaluator that must not come back.
_FORKED_NAMES = {"_MATH_OPS", "_MATH_EXPR_RE", "_TRAILING_EQUALS_RE", "_clean_math_expression"}
_FORKED_NAMES |= {"_apply_math_operation", "_apply_operator", "_evaluate_math_expression"}

CASES = [
    ("3 + 4 = ?", 7),
    ("10 - 3 = ?", 7),
    ("6 x 7 = ?", 42),
    ("6 × 7 = ?", 42),
    ("12 / 4 = ?", 3),
    ("15 ÷ 3 =", 5),
    ("2 PLUS 3 = ?", 5),
    ("8 DIVIDED BY 2 = ?", 4),  # the old OCR-solver copy returned None here
    ("5 / 0 = ?", None),
    ("enter the captcha", None),
    ("1234567890 + 1 = ?", None),  # #18476: 10-digit operand is rejected, not truncated
    ("1 + 1234567890 = ?", None),
    ("123456789 + 1 = ?", 123456790),  # 9 digits is the cap
]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 60), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_the_evaluator_answers(text: str, expected: int | None) -> None:
    assert captcha_math.solve_math_expression(text) == expected


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_both_solvers_agree_with_the_evaluator(text: str, expected: int | None) -> None:
    browser = browser_solver.LocalCaptchaSolver().solve_math(text)
    assert browser == (None if expected is None else str(expected))


@pytest.mark.asyncio
async def test_the_ocr_solver_solves_the_math_kind_through_the_evaluator() -> None:
    solver = ocr_solver.CaptchaSolver()
    solver._tesseract_available = True
    with (
        patch.object(solver, "_quick_ocr", new=AsyncMock(return_value="8 DIVIDED BY 2 = ?")),
        patch.object(ocr_solver, "solve_math_expression", wraps=captcha_math.solve_math_expression) as spy,
    ):
        result = await solver.attempt_solve(_png(), captcha_type=CaptchaType.MATH)
    spy.assert_called_once_with("8 DIVIDED BY 2 = ?")
    assert result.captcha_type is CaptchaType.MATH
    assert result.success is True and result.solution == "4"


def test_the_browser_solver_solves_the_math_kind_through_the_evaluator() -> None:
    solver = browser_solver.LocalCaptchaSolver()
    with patch.object(browser_solver, "solve_math_expression", return_value=99) as spy:
        assert solver.solve_math("anything") == "99"
    spy.assert_called_once_with("anything")


def test_the_browser_detector_reads_math_with_the_evaluators_pattern() -> None:
    assert browser_solver.MATH_EXPR_RE is captcha_math.MATH_EXPR_RE


@pytest.mark.parametrize("rel", _SOLVER_FILES)
def test_no_solver_carries_its_own_copy_of_the_evaluator(rel: str) -> None:
    tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
    defined = {n.id for node in ast.walk(tree) for n in ast.walk(node) if isinstance(n, ast.Name)}
    defined |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not defined & _FORKED_NAMES, f"{rel} re-grew a private math evaluator: {defined & _FORKED_NAMES}"
