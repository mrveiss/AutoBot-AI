# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the OCR solver's use of the shared CAPTCHA types (#18131)."""

import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.captcha_human_loop import CaptchaHumanLoop
from services.captcha_solver import CaptchaSolver
from services.captcha_types import CaptchaSolveResult, CaptchaType


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [CaptchaType.SLIDER, CaptchaType.IMAGE_SELECT, CaptchaType.CLOUDFLARE])
async def test_human_only_kinds_are_not_ocrd(kind: CaptchaType) -> None:
    solver = CaptchaSolver()
    result = await solver.attempt_solve(_png(), captcha_type=kind)
    assert result.success is False
    assert result.requires_human is True
    assert result.captcha_type is kind


@pytest.mark.asyncio
async def test_human_loop_maps_a_recorded_text_image_value_to_text() -> None:
    loop = CaptchaHumanLoop()
    solver = MagicMock()
    solver.attempt_solve = AsyncMock(
        return_value=CaptchaSolveResult(success=True, captcha_type=CaptchaType.TEXT, solution="AB12", confidence=0.95)
    )
    loop._auto_solver = solver
    out = await loop._attempt_auto_solve(b"x", "text_image")
    assert solver.attempt_solve.await_args.kwargs["captcha_type"] is CaptchaType.TEXT
    assert out == {"success": True, "solution": "AB12", "confidence": "high", "type": "text"}
