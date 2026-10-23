# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one CAPTCHA taxonomy, shared by the services and browser solvers (#18131)."""

from dataclasses import dataclass
from enum import Enum


class CaptchaType(Enum):
    """The one CAPTCHA taxonomy (#18131): union of both former solvers' kinds.

    ``TEXT`` is the single spelling for distorted-text images; the recorded legacy
    wire value ``"text_image"`` resolves to it via ``_missing_``.
    """

    TEXT = "text"  # Distorted text rendered as an image
    MATH = "math"  # Math equation to solve
    IMAGE_SELECT = "image_select"  # Select specific images
    SLIDER = "slider"  # Drag-slider challenge
    RECAPTCHA = "recaptcha"  # Google reCAPTCHA
    HCAPTCHA = "hcaptcha"  # hCaptcha
    CLOUDFLARE = "cloudflare"  # Cloudflare challenge
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> "CaptchaType | None":
        if value == "text_image":
            return cls.TEXT
        return None


#: Kinds OCR cannot attempt: routed straight to human intervention, never to auto-solve.
HUMAN_ONLY_TYPES = frozenset(
    {
        CaptchaType.RECAPTCHA,
        CaptchaType.HCAPTCHA,
        CaptchaType.CLOUDFLARE,
        CaptchaType.SLIDER,
        CaptchaType.IMAGE_SELECT,
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
    """The one result of a CAPTCHA solve attempt (#18131), for both the OCR solver and the browser pipeline.

    The OCR solver fills ``confidence`` (a band) and ``processing_time_ms``; the browser pipeline
    fills ``method_used`` ("local_ml", "cache", "human_loop", "math") and ``confidence_score``
    (a float in [0, 1], 1.0 for deterministic results). ``solution`` is ``None`` when solving
    failed or a human solved it in-browser.
    """

    success: bool
    captcha_type: CaptchaType
    solution: str | None = None
    confidence: SolverConfidence = SolverConfidence.NONE
    error_message: str | None = None
    processing_time_ms: float = 0.0
    requires_human: bool = True
    method_used: str | None = None
    confidence_score: float | None = None
