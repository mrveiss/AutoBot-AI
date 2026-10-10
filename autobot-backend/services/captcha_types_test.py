# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared CAPTCHA vocabulary and math evaluator (#18131)."""

import pytest

from services.captcha_math import solve_math_expression
from services.captcha_types import HUMAN_ONLY_TYPES, CaptchaSolveResult, CaptchaType, SolverConfidence


def test_the_enum_is_the_union_of_both_former_enums() -> None:
    old_services = {"text", "math", "image_select", "recaptcha", "hcaptcha", "cloudflare", "unknown"}
    old_browser = {"text_image", "math", "slider", "recaptcha", "hcaptcha", "unknown"}
    values = {t.value for t in CaptchaType}
    assert values >= old_services
    assert values >= old_browser - {"text_image"}


def test_a_recorded_text_image_value_is_text() -> None:
    assert CaptchaType("text_image") is CaptchaType.TEXT
    assert CaptchaType.parse("TEXT_IMAGE") is CaptchaType.TEXT


@pytest.mark.parametrize("raw", [None, "", "nonsense", "captcha"])
def test_parse_degrades_to_unknown(raw: object) -> None:
    assert CaptchaType.parse(raw) is CaptchaType.UNKNOWN  # type: ignore[arg-type]


def test_every_kind_is_either_solvable_locally_or_human_only() -> None:
    assert CaptchaType.TEXT not in HUMAN_ONLY_TYPES
    assert CaptchaType.MATH not in HUMAN_ONLY_TYPES
    assert {CaptchaType.SLIDER, CaptchaType.CLOUDFLARE, CaptchaType.IMAGE_SELECT} <= HUMAN_ONLY_TYPES


@pytest.mark.parametrize(
    ("confidence", "level"),
    [
        (0.95, SolverConfidence.HIGH),
        (0.75, SolverConfidence.MEDIUM),
        (0.55, SolverConfidence.LOW),
        (0.1, SolverConfidence.NONE),
    ],
)
def test_confidence_level_follows_the_float(confidence: float, level: SolverConfidence) -> None:
    result = CaptchaSolveResult(success=True, captcha_type=CaptchaType.TEXT, confidence=confidence)
    assert result.confidence_level is level


def test_requires_human_is_the_inverse_of_success() -> None:
    assert CaptchaSolveResult(success=False, captcha_type=CaptchaType.TEXT).requires_human is True
    assert CaptchaSolveResult(success=True, captcha_type=CaptchaType.TEXT).requires_human is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5 + 3 = ?", 8),
        ("12 - 5 =", 7),
        ("7 × 2", 14),
        ("4 x 5 = ?", 20),
        ("9 ÷ 3", 3),
        ("what is 6 TIMES 7", 42),
        ("8 / 0", None),
        ("no sum here", None),
    ],
)
def test_math_expressions(text: str, expected: int | None) -> None:
    assert solve_math_expression(text) == expected


# Every value either enum emitted before the merge, frozen as literals from origin/main (#18131):
# `CaptchaType` in services/captcha_solver.py and in agents/browser/captcha_solver.py.
_OLD_SERVICES = {
    "text": CaptchaType.TEXT,
    "math": CaptchaType.MATH,
    "image_select": CaptchaType.IMAGE_SELECT,
    "recaptcha": CaptchaType.RECAPTCHA,
    "hcaptcha": CaptchaType.HCAPTCHA,
    "cloudflare": CaptchaType.CLOUDFLARE,
    "unknown": CaptchaType.UNKNOWN,
}
_OLD_BROWSER = {
    "text_image": CaptchaType.TEXT,
    "math": CaptchaType.MATH,
    "slider": CaptchaType.SLIDER,
    "recaptcha": CaptchaType.RECAPTCHA,
    "hcaptcha": CaptchaType.HCAPTCHA,
    "unknown": CaptchaType.UNKNOWN,
}
_OLD_VALUES = {**_OLD_SERVICES, **_OLD_BROWSER}


@pytest.mark.parametrize("old", sorted(_OLD_VALUES))
def test_every_old_value_maps_to_its_member_in_any_case(old: str) -> None:
    expected = _OLD_VALUES[old]
    for variant in (old, old.upper(), old.title(), f"  {old} "):
        assert CaptchaType(variant) is expected, variant
        assert CaptchaType.parse(variant) is expected, variant


@pytest.mark.parametrize("raw", ["captcha", "text image", "recaptcha_v3", "image-select", 7, None])
def test_an_unknown_value_degrades_in_parse_and_is_refused_by_the_constructor(raw: object) -> None:
    assert CaptchaType.parse(raw) is CaptchaType.UNKNOWN  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CaptchaType(raw)
