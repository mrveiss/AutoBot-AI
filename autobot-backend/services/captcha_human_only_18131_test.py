# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18131 -- SLIDER and IMAGE_SELECT are human-only: no OCR is ever attempted for them."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from autobot_shared.captcha_types import HUMAN_ONLY_TYPES, CaptchaType
from services.captcha_human_loop import _UNSUPPORTED_CAPTCHA_TYPES, CaptchaHumanLoop
from services.captcha_solver import CaptchaSolver

KINDS = [CaptchaType.SLIDER, CaptchaType.IMAGE_SELECT]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 60), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_human_loop_list_is_derived_from_the_one_definition() -> None:
    assert _UNSUPPORTED_CAPTCHA_TYPES == {t.value for t in HUMAN_ONLY_TYPES}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_solver_returns_requires_human_without_any_ocr(kind: CaptchaType) -> None:
    solver = CaptchaSolver()
    with (
        patch.object(solver, "_solve_text_captcha", new=AsyncMock()) as text,
        patch.object(solver, "_solve_math_captcha", new=AsyncMock()) as math,
        patch.object(solver, "_quick_ocr", new=AsyncMock()) as ocr,
    ):
        result = await solver.attempt_solve(_png(), captcha_type=kind)
    assert result.success is False and result.requires_human is True
    text.assert_not_called()
    math.assert_not_called()
    ocr.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_human_loop_never_calls_the_auto_solver(kind: CaptchaType) -> None:
    loop = CaptchaHumanLoop(vnc_url="vnc://test", enable_auto_solve=True)
    loop._auto_solver = MagicMock(attempt_solve=AsyncMock())
    assert loop._can_auto_solve(kind.value) is False
    out = await loop._handle_auto_solve(MagicMock(), b"x", kind.value, None, "id", "http://t", 0.0)
    assert out is None
    loop._auto_solver.attempt_solve.assert_not_called()
