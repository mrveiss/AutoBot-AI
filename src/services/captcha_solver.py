# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated CAPTCHA Solver Service

This module provides automated CAPTCHA recognition using OCR and image processing.
It attempts to solve simple CAPTCHAs automatically before falling back to
human-in-the-loop intervention.

Supported CAPTCHA Types:
- Simple text CAPTCHAs (distorted letters/numbers)
- Basic math CAPTCHAs (addition, subtraction)
- Image selection hints (text-based guidance)

For complex CAPTCHAs (reCAPTCHA v2/v3, hCaptcha, Cloudflare):
Falls back to human-in-the-loop system (captcha_human_loop.py)

Usage:
    from src.services.captcha_solver import CaptchaSolver

    solver = CaptchaSolver()
    result = await solver.attempt_solve(page, captcha_type="text")
    if result.success:
        # CAPTCHA solved automatically
        await page.fill("#captcha-input", result.solution)
    else:
        # Fall back to human intervention
        ...

Related: Issue #206
"""

import io
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for CAPTCHA type detection
_MATH_OPERATORS = frozenset({"+", "-", "=", "×", "÷", "*"})

# Issue #380: Pre-compiled regex patterns for CAPTCHA processing
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
_TRAILING_EQUALS_RE = re.compile(r"=\s*\??\s*$")
_MATH_EXPR_RE = re.compile(r"(\d+)\s*([+\-*/])\s*(\d+)")


class CaptchaType(Enum):
    """Types of CAPTCHAs that can be encountered"""

    TEXT = "text"  # Simple distorted text
    MATH = "math"  # Math equation to solve
    IMAGE_SELECT = "image_select"  # Select specific images
    RECAPTCHA = "recaptcha"  # Google reCAPTCHA
    HCAPTCHA = "hcaptcha"  # hCaptcha
    CLOUDFLARE = "cloudflare"  # Cloudflare challenge
    UNKNOWN = "unknown"


class SolverConfidence(Enum):
    """Confidence levels for CAPTCHA solutions"""

    HIGH = "high"  # >90% confident
    MEDIUM = "medium"  # 70-90% confident
    LOW = "low"  # 50-70% confident
    NONE = "none"  # <50% or unable to solve


@dataclass
class CaptchaSolveResult:
    """Result of a CAPTCHA solving attempt"""

    success: bool
    captcha_type: CaptchaType
    solution: Optional[str] = None
    confidence: SolverConfidence = SolverConfidence.NONE
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    requires_human: bool = True


class CaptchaSolver:
    """
    Automated CAPTCHA solving using OCR and image processing.

    Attempts to solve simple CAPTCHAs automatically before falling back
    to human intervention for complex challenges.
    """

    # Minimum confidence to accept a solution
    MIN_CONFIDENCE_THRESHOLD = 0.7

    # Common CAPTCHA character sets
    ALPHANUMERIC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    NUMERIC_ONLY = "0123456789"
    ALPHA_ONLY = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def __init__(self, use_gpu: bool = False):
        """
        Initialize the CAPTCHA solver.

        Args:
            use_gpu: Whether to use GPU acceleration for inference
        """
        self.use_gpu = use_gpu
        self._tesseract_available = self._check_tesseract()
        self._opencv_available = self._check_opencv()

    def _check_tesseract(self) -> bool:
        """Check if pytesseract is available"""
        try:
            import pytesseract

            # Quick test to verify tesseract binary is accessible
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.warning("Tesseract OCR not available: %s", e)
            return False

    def _check_opencv(self) -> bool:
        """Check if OpenCV is available"""
        try:
            pass

            return True
        except ImportError:
            logger.warning("OpenCV not available")
            return False

    async def _route_to_solver(
        self,
        image: Image.Image,
        captcha_type: CaptchaType,
        expected_length: Optional[int],
        char_set: Optional[str],
    ) -> CaptchaSolveResult:
        """
        Route CAPTCHA to appropriate solver based on type.

        Args:
            image: PIL Image of the CAPTCHA
            captcha_type: Detected or specified CAPTCHA type
            expected_length: Expected solution length
            char_set: Expected character set

        Returns:
            CaptchaSolveResult from the appropriate solver

        Issue #620.
        """
        if captcha_type == CaptchaType.TEXT:
            return await self._solve_text_captcha(image, expected_length, char_set)
        if captcha_type == CaptchaType.MATH:
            return await self._solve_math_captcha(image)
        if captcha_type in (
            CaptchaType.RECAPTCHA,
            CaptchaType.HCAPTCHA,
            CaptchaType.CLOUDFLARE,
        ):
            return CaptchaSolveResult(
                success=False,
                captcha_type=captcha_type,
                confidence=SolverConfidence.NONE,
                error_message=f"{captcha_type.value} requires human intervention",
                requires_human=True,
            )
        # Default: try text solver
        return await self._solve_text_captcha(image, expected_length, char_set)

    async def attempt_solve(
        self,
        image_data: bytes,
        captcha_type: CaptchaType = CaptchaType.UNKNOWN,
        expected_length: Optional[int] = None,
        char_set: Optional[str] = None,
    ) -> CaptchaSolveResult:
        """
        Attempt to automatically solve a CAPTCHA.

        Args:
            image_data: Raw image bytes of the CAPTCHA
            captcha_type: Type of CAPTCHA if known
            expected_length: Expected solution length (if known)
            char_set: Expected character set (alphanumeric, numeric, etc.)

        Returns:
            CaptchaSolveResult with solution or indication to use human fallback
        """
        import time

        start_time = time.time()

        try:
            image = Image.open(io.BytesIO(image_data))

            if captcha_type == CaptchaType.UNKNOWN:
                captcha_type = await self._detect_captcha_type(image)

            result = await self._route_to_solver(
                image, captcha_type, expected_length, char_set
            )
            result.processing_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.error("CAPTCHA solving error: %s", e)
            return CaptchaSolveResult(
                success=False,
                captcha_type=captcha_type,
                error_message=str(e),
                requires_human=True,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def _detect_captcha_type(self, image: Image.Image) -> CaptchaType:
        """
        Detect the type of CAPTCHA from the image.

        Args:
            image: PIL Image of the CAPTCHA

        Returns:
            Detected CaptchaType
        """
        # Simple heuristics for type detection
        width, height = image.size

        # reCAPTCHA typically has specific dimensions
        if 300 <= width <= 320 and 70 <= height <= 80:
            return CaptchaType.RECAPTCHA

        # hCaptcha checkbox
        if width == height and 70 <= width <= 80:
            return CaptchaType.HCAPTCHA

        # Most simple CAPTCHAs are wider than tall
        if width > height * 2:
            return CaptchaType.TEXT

        # Math CAPTCHAs often contain +, -, = - Issue #380: Use module-level frozenset
        if self._tesseract_available:
            text = await self._quick_ocr(image)
            if any(op in text for op in _MATH_OPERATORS):
                return CaptchaType.MATH

        return CaptchaType.TEXT

    def _get_tesseract_config(self, char_set: Optional[str]) -> str:
        """Get Tesseract config based on character set (Issue #315: extracted helper)."""
        config = "--psm 7 --oem 3"  # Single line of text
        if char_set == self.NUMERIC_ONLY:
            config += " -c tessedit_char_whitelist=0123456789"
        elif char_set == self.ALPHA_ONLY:
            config += " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        elif char_set == self.ALPHANUMERIC:
            config += " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return config

    def _process_ocr_result(
        self,
        image,
        config: str,
        char_set: Optional[str],
        expected_length: Optional[int],
    ) -> tuple:
        """Process single OCR attempt (Issue #315: extracted helper).

        Returns:
            Tuple of (text, confidence) or (None, 0) on failure
        """
        import pytesseract

        try:
            data = pytesseract.image_to_data(
                image, config=config, output_type=pytesseract.Output.DICT
            )

            texts = []
            confidences = []
            for i, conf in enumerate(data["conf"]):
                if int(conf) > 0:
                    texts.append(data["text"][i])
                    confidences.append(int(conf))

            if not texts:
                return None, 0.0

            text = "".join(texts).strip().upper()
            avg_confidence = sum(confidences) / len(confidences) / 100
            text = self._clean_ocr_result(text, char_set)

            if expected_length and len(text) != expected_length:
                return None, 0.0

            return text, avg_confidence
        except Exception as e:
            logger.debug("OCR attempt failed: %s", e)
            return None, 0.0

    async def _solve_text_captcha(
        self,
        image: Image.Image,
        expected_length: Optional[int] = None,
        char_set: Optional[str] = None,
    ) -> CaptchaSolveResult:
        """
        Solve a simple text-based CAPTCHA using OCR.

        Args:
            image: PIL Image of the CAPTCHA
            expected_length: Expected solution length
            char_set: Expected character set

        Returns:
            CaptchaSolveResult
        """
        if not self._tesseract_available:
            return CaptchaSolveResult(
                success=False,
                captcha_type=CaptchaType.TEXT,
                error_message="Tesseract OCR not available",
                requires_human=True,
            )

        # Preprocess image for better OCR
        processed_images = await self._preprocess_for_ocr(image)
        config = self._get_tesseract_config(char_set)

        best_result = None
        best_confidence = 0.0

        # Process each image variant (Issue #315: reduced nesting)
        for processed_image in processed_images:
            text, confidence = self._process_ocr_result(
                processed_image, config, char_set, expected_length
            )
            if text and confidence > best_confidence:
                best_confidence = confidence
                best_result = text

        if best_result and best_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            confidence_level = (
                SolverConfidence.HIGH
                if best_confidence >= 0.9
                else SolverConfidence.MEDIUM
                if best_confidence >= 0.7
                else SolverConfidence.LOW
            )

            return CaptchaSolveResult(
                success=True,
                captcha_type=CaptchaType.TEXT,
                solution=best_result,
                confidence=confidence_level,
                requires_human=False,
            )

        return CaptchaSolveResult(
            success=False,
            captcha_type=CaptchaType.TEXT,
            confidence=SolverConfidence.LOW if best_result else SolverConfidence.NONE,
            error_message="OCR confidence too low",
            requires_human=True,
        )

    async def _solve_math_captcha(self, image: Image.Image) -> CaptchaSolveResult:
        """
        Solve a math-based CAPTCHA.

        Args:
            image: PIL Image of the CAPTCHA

        Returns:
            CaptchaSolveResult
        """
        if not self._tesseract_available:
            return CaptchaSolveResult(
                success=False,
                captcha_type=CaptchaType.MATH,
                error_message="Tesseract OCR not available",
                requires_human=True,
            )

        try:
            # Get the math expression
            text = await self._quick_ocr(image)

            # Parse and solve the expression
            solution = self._evaluate_math_expression(text)

            if solution is not None:
                return CaptchaSolveResult(
                    success=True,
                    captcha_type=CaptchaType.MATH,
                    solution=str(solution),
                    confidence=SolverConfidence.HIGH,
                    requires_human=False,
                )

        except Exception as e:
            logger.debug("Math CAPTCHA solving failed: %s", e)

        return CaptchaSolveResult(
            success=False,
            captcha_type=CaptchaType.MATH,
            error_message="Could not parse math expression",
            requires_human=True,
        )

    async def _preprocess_for_ocr(self, image: Image.Image) -> List[Image.Image]:
        """
        Apply various preprocessing techniques to improve OCR accuracy.

        Args:
            image: Original PIL Image

        Returns:
            List of preprocessed images to try
        """
        results = []

        # Convert to grayscale
        gray = image.convert("L")

        # 1. Basic threshold
        threshold = gray.point(lambda x: 255 if x > 128 else 0)
        results.append(threshold)

        # 2. Enhanced contrast
        enhancer = ImageEnhance.Contrast(gray)
        high_contrast = enhancer.enhance(2.0)
        results.append(high_contrast.point(lambda x: 255 if x > 128 else 0))

        # 3. Sharpened
        sharpened = gray.filter(ImageFilter.SHARPEN)
        results.append(sharpened.point(lambda x: 255 if x > 128 else 0))

        # 4. Inverted (for dark background CAPTCHAs)
        inverted = Image.eval(gray, lambda x: 255 - x)
        results.append(inverted.point(lambda x: 255 if x > 128 else 0))

        # 5. Scaled up (2x) for small CAPTCHAs
        if image.width < 200:
            scaled = gray.resize(
                (gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS
            )
            results.append(scaled.point(lambda x: 255 if x > 128 else 0))

        # 6. Denoised with median filter
        denoised = gray.filter(ImageFilter.MedianFilter(3))
        results.append(denoised.point(lambda x: 255 if x > 128 else 0))

        return results

    async def _quick_ocr(self, image: Image.Image) -> str:
        """
        Quick OCR scan of an image.

        Args:
            image: PIL Image

        Returns:
            Extracted text
        """
        import pytesseract

        gray = image.convert("L")
        return pytesseract.image_to_string(gray, config="--psm 7").strip()

    def _clean_ocr_result(self, text: str, char_set: Optional[str]) -> str:
        """
        Clean up OCR result by fixing common misrecognitions.

        Args:
            text: Raw OCR text
            char_set: Expected character set

        Returns:
            Cleaned text
        """
        # Remove spaces and special characters (Issue #380: use pre-compiled pattern)
        text = _NON_ALNUM_RE.sub("", text)

        # Common OCR mistakes
        replacements = {
            "0": "O",  # Zero/O confusion (context dependent)
            "1": "I",  # One/I confusion
            "5": "S",  # Five/S confusion
            "8": "B",  # Eight/B confusion
        }

        # Apply fixes based on character set
        if char_set == self.ALPHA_ONLY:
            for wrong, right in replacements.items():
                text = text.replace(wrong, right)
        elif char_set == self.NUMERIC_ONLY:
            # Reverse replacements for numeric
            for right, wrong in replacements.items():
                text = text.replace(wrong, right)

        return text.upper()

    # Math operation lookup table (Issue #315: extracted to reduce nesting)
    _MATH_OPS = {
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
        "/": lambda a, b: a // b if b != 0 else None,
    }

    def _clean_math_expression(self, expression: str) -> str:
        """Clean and normalize a math expression (Issue #315: extracted).

        Args:
            expression: Raw math expression

        Returns:
            Cleaned expression with normalized operators
        """
        expr = expression.upper()
        # Remove "= ?" or "= " at the end (Issue #380: use pre-compiled pattern)
        expr = _TRAILING_EQUALS_RE.sub("", expr)
        # Replace text/symbol operators with standard operators
        replacements = [
            ("×", "*"),
            ("÷", "/"),
            ("X", "*"),
            ("PLUS", "+"),
            ("MINUS", "-"),
            ("TIMES", "*"),
        ]
        for old, new in replacements:
            expr = expr.replace(old, new)
        return expr

    def _apply_math_operation(self, a: int, op: str, b: int) -> Optional[int]:
        """Apply a math operation to two operands (Issue #315: extracted).

        Args:
            a: First operand
            op: Operator (+, -, *, /)
            b: Second operand

        Returns:
            Result of operation, or None if invalid
        """
        operation = self._MATH_OPS.get(op)
        return operation(a, b) if operation else None

    def _evaluate_math_expression(self, expression: str) -> Optional[int]:
        """Safely evaluate a simple math expression.

        Issue #315: Refactored to use helpers for reduced nesting.

        Args:
            expression: Math expression string (e.g., "5 + 3 = ?")

        Returns:
            Integer result or None if can't parse
        """
        try:
            expr = self._clean_math_expression(expression)
            # Issue #380: use pre-compiled pattern
            match = _MATH_EXPR_RE.search(expr)
            if not match:
                return None

            a = int(match.group(1))
            op = match.group(2)
            b = int(match.group(3))
            return self._apply_math_operation(a, op, b)

        except Exception:
            return None


# Global solver instance (thread-safe)
import threading

_captcha_solver: Optional[CaptchaSolver] = None
_captcha_solver_lock = threading.Lock()


def get_captcha_solver() -> CaptchaSolver:
    """Get or create the global CaptchaSolver instance (thread-safe)."""
    global _captcha_solver
    if _captcha_solver is None:
        with _captcha_solver_lock:
            # Double-check after acquiring lock
            if _captcha_solver is None:
                _captcha_solver = CaptchaSolver()
    return _captcha_solver
