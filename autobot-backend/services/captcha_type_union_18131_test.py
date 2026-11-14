# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18131 -- a kind from each former CaptchaType resolves in the one canonical enum."""

import dataclasses

import pytest

from agents.browser.captcha_solver import CaptchaSolveResult as BrowserResult
from agents.browser.captcha_solver import CaptchaType as BrowserCaptchaType
from autobot_shared.captcha_types import CaptchaSolveResult, CaptchaType, SolverConfidence
from services.captcha_solver import CaptchaSolveResult as ServicesResult
from services.captcha_solver import CaptchaType as ServicesCaptchaType


def test_both_solver_modules_use_the_canonical_enum() -> None:
    assert BrowserCaptchaType is CaptchaType
    assert ServicesCaptchaType is CaptchaType


@pytest.mark.parametrize("value", ["image_select", "cloudflare"])  # services-only kinds
def test_services_only_kinds_resolve(value: str) -> None:
    assert CaptchaType(value).value == value


def test_browser_only_slider_resolves() -> None:
    assert CaptchaType("slider") is CaptchaType.SLIDER


def test_text_image_legacy_value_maps_to_text() -> None:
    assert CaptchaType("text_image") is CaptchaType.TEXT


def test_both_solvers_share_the_one_result_type() -> None:
    assert ServicesResult is CaptchaSolveResult
    assert BrowserResult is CaptchaSolveResult


def test_ocr_solver_style_result_round_trips() -> None:
    r = CaptchaSolveResult(
        success=True,
        captcha_type=CaptchaType.TEXT,
        solution="AB12",
        confidence=SolverConfidence.HIGH,
        processing_time_ms=12.5,
        requires_human=False,
    )
    assert dataclasses.replace(r) == r
    assert r.method_used is None and r.confidence_score is None


def test_pipeline_style_result_round_trips() -> None:
    r = CaptchaSolveResult(
        success=False,
        captcha_type=CaptchaType.SLIDER,
        method_used="human_loop",
        confidence_score=0.0,
        error_message="timeout",
    )
    assert dataclasses.replace(r) == r
    assert r.solution is None and r.confidence is SolverConfidence.NONE and r.requires_human is True
