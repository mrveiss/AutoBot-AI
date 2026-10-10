# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one CAPTCHA vocabulary: kinds, confidence levels and the solve result (#18131).

Two solvers classify and report CAPTCHAs -- the OCR service in ``services.captcha_solver``
and the page pipeline in ``agents.browser.captcha_solver``. Each used to carry its own
``CaptchaType`` and result dataclass, and the enums disagreed on which kinds exist, so a
kind one could classify was silently ``UNKNOWN`` to the other. Both now import from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CaptchaType(Enum):
    """Every CAPTCHA kind either solver can classify. Values are wire values."""

    TEXT = "text"  # Distorted text rendered as an image
    MATH = "math"  # Arithmetic expression to evaluate
    IMAGE_SELECT = "image_select"  # Select specific images
    SLIDER = "slider"  # Drag-slider challenge
    RECAPTCHA = "recaptcha"  # Google reCAPTCHA v2 / v3
    HCAPTCHA = "hcaptcha"  # hCaptcha
    CLOUDFLARE = "cloudflare"  # Cloudflare challenge
    UNKNOWN = "unknown"  # Could not be classified

    @classmethod
    def _missing_(cls, value: object) -> "CaptchaType | None":
        """Accept a case or whitespace variant, and ``text_image`` (the browser's old ``TEXT``)."""
        if not isinstance(value, str):
            return None
        key = value.strip().lower()
        if key in _LEGACY_VALUES:
            return _LEGACY_VALUES[key]
        return next((member for member in cls if member.value == key), None)

    @classmethod
    def parse(cls, raw: str | None) -> "CaptchaType":
        """The member for a wire string, ``UNKNOWN`` for anything unrecognised."""
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


#: Values the browser pipeline emitted before the enums were merged.
_LEGACY_VALUES = {"text_image": CaptchaType.TEXT}

#: Kinds no local solver can answer; they go straight to a human.
HUMAN_ONLY_TYPES = frozenset(
    {
        CaptchaType.IMAGE_SELECT,
        CaptchaType.SLIDER,
        CaptchaType.RECAPTCHA,
        CaptchaType.HCAPTCHA,
        CaptchaType.CLOUDFLARE,
    }
)


class SolverConfidence(Enum):
    """Confidence levels for CAPTCHA solutions"""

    HIGH = "high"  # >90% confident
    MEDIUM = "medium"  # 70-90% confident
    LOW = "low"  # 50-70% confident
    NONE = "none"  # <50% or unable to solve


@dataclass
class CaptchaSolveResult:
    """Outcome of a CAPTCHA solve attempt, from either solver.

    Attributes:
        success:            Whether the CAPTCHA was (or is expected to be) solved.
        captcha_type:       The kind that was processed.
        solution:           The answer text, or ``None`` (a human solves in-browser).
        confidence:         Float in [0, 1]; 1.0 for deterministic results (math, cache).
        method_used:        "ocr", "local_ml", "cache", "human_loop", "math", or "" if unset.
        error_message:      Description when ``success`` is False.
        processing_time_ms: Wall time of the attempt, when measured.
    """

    success: bool
    captcha_type: CaptchaType
    solution: str | None = None
    confidence: float = 0.0
    method_used: str = ""
    error_message: str | None = None
    processing_time_ms: float = 0.0

    @property
    def requires_human(self) -> bool:
        """A failed attempt always needs a human; a successful one never does."""
        return not self.success

    @property
    def confidence_level(self) -> SolverConfidence:
        """The coarse level for ``confidence``."""
        if self.confidence >= 0.9:
            return SolverConfidence.HIGH
        if self.confidence >= 0.7:
            return SolverConfidence.MEDIUM
        if self.confidence >= 0.5:
            return SolverConfidence.LOW
        return SolverConfidence.NONE
