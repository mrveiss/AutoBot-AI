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
            logger.warning(f"Tesseract OCR not available: {e}")
            return False

    def _check_opencv(self) -> bool:
        """Check if OpenCV is available"""
        try:
            pass

            return True
        except ImportError:
            logger.warning("OpenCV not available")
            return False

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
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))

            # Detect CAPTCHA type if unknown
            if captcha_type == CaptchaType.UNKNOWN:
                captcha_type = await self._detect_captcha_type(image)

            # Route to appropriate solver
            if captcha_type == CaptchaType.TEXT:
                result = await self._solve_text_captcha(
                    image, expected_length, char_set
                )
            elif captcha_type == CaptchaType.MATH:
                result = await self._solve_math_captcha(image)
            elif captcha_type in (
                CaptchaType.RECAPTCHA,
                CaptchaType.HCAPTCHA,
                CaptchaType.CLOUDFLARE,
            ):
                # These require human intervention
                result = CaptchaSolveResult(
                    success=False,
                    captcha_type=captcha_type,
                    confidence=SolverConfidence.NONE,
                    error_message=f"{captcha_type.value} requires human intervention",
                    requires_human=True,
                )
            else:
                # Try text solver as default
                result = await self._solve_text_captcha(
                    image, expected_length, char_set
                )

            result.processing_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.error(f"CAPTCHA solving error: {e}")
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

        # Math CAPTCHAs often contain +, -, =
        if self._tesseract_available:
            text = await self._quick_ocr(image)
            if any(op in text for op in ["+", "-", "=", "×", "÷", "*"]):
                return CaptchaType.MATH

        return CaptchaType.TEXT

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

        import pytesseract

        # Preprocess image for better OCR
        processed_images = await self._preprocess_for_ocr(image)

        best_result = None
        best_confidence = 0.0

        for processed_image in processed_images:
            try:
                # Configure Tesseract for CAPTCHA text
                config = "--psm 7 --oem 3"  # Single line of text

                if char_set == self.NUMERIC_ONLY:
                    config += " -c tessedit_char_whitelist=0123456789"
                elif char_set == self.ALPHA_ONLY:
                    config += " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                elif char_set == self.ALPHANUMERIC:
                    config += " -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

                # Get OCR result with confidence
                data = pytesseract.image_to_data(
                    processed_image, config=config, output_type=pytesseract.Output.DICT
                )

                # Extract text and confidence
                texts = []
                confidences = []
                for i, conf in enumerate(data["conf"]):
                    if int(conf) > 0:
                        texts.append(data["text"][i])
                        confidences.append(int(conf))

                if texts:
                    text = "".join(texts).strip().upper()
                    avg_confidence = sum(confidences) / len(confidences) / 100

                    # Clean up the result
                    text = self._clean_ocr_result(text, char_set)

                    # Validate length if specified
                    if expected_length and len(text) != expected_length:
                        continue

                    if avg_confidence > best_confidence:
                        best_confidence = avg_confidence
                        best_result = text

            except Exception as e:
                logger.debug(f"OCR attempt failed: {e}")
                continue

        if best_result and best_confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            confidence_level = (
                SolverConfidence.HIGH
                if best_confidence >= 0.9
                else SolverConfidence.MEDIUM if best_confidence >= 0.7 else SolverConfidence.LOW
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
            logger.debug(f"Math CAPTCHA solving failed: {e}")

        return CaptchaSolveResult(
            success=False,
            captcha_type=CaptchaType.MATH,
            error_message="Could not parse math expression",
            requires_human=True,
        )

    async def _preprocess_for_ocr(
        self, image: Image.Image
    ) -> List[Image.Image]:
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
            scaled = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
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
        # Remove spaces and special characters
        text = re.sub(r"[^A-Za-z0-9]", "", text)

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

    def _evaluate_math_expression(self, expression: str) -> Optional[int]:
        """
        Safely evaluate a simple math expression.

        Args:
            expression: Math expression string (e.g., "5 + 3 = ?")

        Returns:
            Integer result or None if can't parse
        """
        try:
            # Clean the expression
            expr = expression.upper()

            # Remove "= ?" or "= " at the end
            expr = re.sub(r"=\s*\??\s*$", "", expr)

            # Replace text operators
            expr = expr.replace("×", "*").replace("÷", "/")
            expr = expr.replace("X", "*").replace("PLUS", "+")
            expr = expr.replace("MINUS", "-").replace("TIMES", "*")

            # Extract just the math part
            match = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)", expr)
            if match:
                a = int(match.group(1))
                op = match.group(2)
                b = int(match.group(3))

                if op == "+":
                    return a + b
                elif op == "-":
                    return a - b
                elif op == "*":
                    return a * b
                elif op == "/" and b != 0:
                    return a // b

        except Exception:
            pass  # Regex parsing failed, return None below

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
