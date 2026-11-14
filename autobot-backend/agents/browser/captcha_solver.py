# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Local ML-based CAPTCHA Solving via NPU

Provides detection, image extraction, local ML inference (ONNX on NPU/CPU),
and a layered pipeline that falls back from local ML to human-in-the-loop.

Classes:
    CaptchaType          — imported from autobot_shared.captcha_types (the one taxonomy)
    CaptchaDetector      — keyword/selector detection + element screenshot extraction
    LocalCaptchaSolver   — ONNX-based OCR running on NPU/CPU; math expression eval
    CaptchaSolveResult   — shared result dataclass (autobot_shared.captcha_types)
    CaptchaSolverPipeline — orchestrates the full solve attempt

Design decisions:
    - ONNX Runtime is used for model inference; the NPU execution provider
      ("NPUExecutionProvider") is attempted first with CPU as a fallback so
      the module works on nodes without NPU hardware.
    - Heavy imports (onnxruntime, PIL) are deferred to runtime to keep cold-start
      overhead low.
    - Math evaluation uses a safe regex-based expression parser; ``eval()`` is
      never called.
    - The pipeline applies three layers in order:
        1. Local ML (ONNX model inference)
        2. Heuristic session reuse — if an identical image hash already produced a
           confirmed answer in this process lifetime the cached answer is reused.
        3. Human-in-the-loop fallback via ``services.captcha_human_loop``.

Related: Issue #1974
"""

from __future__ import annotations

import hashlib
import io
import time
from typing import TYPE_CHECKING, Any, Dict, Tuple

from autobot_shared.captcha_types import CaptchaSolveResult, CaptchaType
from autobot_shared.logging_manager import get_logger
from services.captcha_human_loop import get_captcha_human_loop
from services.captcha_math import MATH_EXPR_RE, solve_math_expression

if TYPE_CHECKING:
    pass  # Playwright Page — only needed for type annotations, imported lazily

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level compiled patterns (avoid re-compilation on every call)
# ---------------------------------------------------------------------------

# Keyword sets used by CaptchaDetector.detect()
_HTML_CAPTCHA_KEYWORDS = frozenset(
    {
        "captcha",
        "challenge",
        "verification",
        "verify you are human",
        "are you a robot",
        "i am not a robot",
        "prove you are human",
        "security check",
    }
)

_RECAPTCHA_PATTERNS = frozenset({"g-recaptcha", "recaptcha", "grecaptcha", "recaptcha/api.js"})
_HCAPTCHA_PATTERNS = frozenset({"h-captcha", "hcaptcha", "hcaptcha.com"})
_SLIDER_PATTERNS = frozenset({"slider", "slide-verify", "slidercaptcha", "drag"})

# ---------------------------------------------------------------------------
# Enumerations and result types
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CAPTCHA detection
# ---------------------------------------------------------------------------


class CaptchaDetector:
    """Detects CAPTCHA type from page HTML and extracts element screenshots.

    All methods are synchronous or async-compatible. The async ``extract_captcha_image``
    method uses Playwright's ``screenshot`` API on the matched element.
    """

    # CSS selectors checked in priority order for each CAPTCHA type
    _RECAPTCHA_SELECTORS = (
        ".g-recaptcha",
        "[data-sitekey]",
        'iframe[src*="recaptcha"]',
    )
    _HCAPTCHA_SELECTORS = (
        ".h-captcha",
        "[data-hcaptcha-widget-id]",
        'iframe[src*="hcaptcha"]',
    )
    _SLIDER_SELECTORS = (
        ".slider-verify",
        ".slide-verify",
        '[class*="slider"]',
        '[class*="captcha-slider"]',
    )
    _TEXT_IMAGE_SELECTORS = (
        "#captcha",
        ".captcha",
        'img[class*="captcha"]',
        'img[id*="captcha"]',
        'canvas[id*="captcha"]',
    )

    def detect(self, page_source: str) -> CaptchaType:
        """Classify the CAPTCHA type present in *page_source*.

        Uses keyword matching against known patterns. Checks are executed in
        specificity order: reCAPTCHA > hCaptcha > Slider > Math > Text > Unknown.

        Args:
            page_source: Raw HTML string of the page.

        Returns:
            The most specific ``CaptchaType`` found, or ``CaptchaType.UNKNOWN``.
        """
        lower = page_source.lower()

        if any(p in lower for p in _RECAPTCHA_PATTERNS):
            logger.debug("CaptchaDetector: reCAPTCHA pattern found")
            return CaptchaType.RECAPTCHA

        if any(p in lower for p in _HCAPTCHA_PATTERNS):
            logger.debug("CaptchaDetector: hCaptcha pattern found")
            return CaptchaType.HCAPTCHA

        if any(p in lower for p in _SLIDER_PATTERNS):
            logger.debug("CaptchaDetector: slider pattern found")
            return CaptchaType.SLIDER

        # Math indicator: expression-like content before the CAPTCHA keyword
        if any(kw in lower for kw in _HTML_CAPTCHA_KEYWORDS):
            if MATH_EXPR_RE.search(lower):
                logger.debug("CaptchaDetector: math CAPTCHA pattern found")
                return CaptchaType.MATH
            logger.debug("CaptchaDetector: generic text-image CAPTCHA keyword found")
            return CaptchaType.TEXT

        logger.debug("CaptchaDetector: no CAPTCHA pattern matched")
        return CaptchaType.UNKNOWN

    async def extract_captcha_image(self, page: Any, selector: str) -> bytes | None:
        """Screenshot the CAPTCHA element identified by *selector*.

        Args:
            page:     A Playwright ``Page`` object.
            selector: CSS selector pointing to the CAPTCHA element.

        Returns:
            PNG image bytes, or ``None`` if the element was not found.
        """
        try:
            element = await page.query_selector(selector)
            if element is None:
                logger.warning("extract_captcha_image: selector %r matched no element", selector)
                return None
            image_bytes: bytes = await element.screenshot()
            logger.debug(
                "extract_captcha_image: captured %d bytes for selector %r",
                len(image_bytes),
                selector,
            )
            return image_bytes
        except Exception as exc:
            logger.error("extract_captcha_image failed for selector %r: %s", selector, exc)
            return None

    def _select_text_image_selector(self, page_source: str) -> str:
        """Pick the most specific text-image selector based on page content.

        Args:
            page_source: Raw HTML string.

        Returns:
            CSS selector string most likely to match the CAPTCHA image element.
        """
        lower = page_source.lower()
        for selector in self._TEXT_IMAGE_SELECTORS:
            # Strip leading . or # to get the class/id name for a quick check
            hint = selector.lstrip(".#").split("[")[0]
            if hint in lower:
                return selector
        return self._TEXT_IMAGE_SELECTORS[0]


# ---------------------------------------------------------------------------
# Local ONNX-based solver
# ---------------------------------------------------------------------------

# Default ONNX model path; can be overridden via constructor argument.
_DEFAULT_MODEL_PATH = "models/captcha_ocr.onnx"

# Characters the OCR model outputs (alphanumeric + common symbols)
_DEFAULT_CHAR_SET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Preferred ONNX execution providers, tried in order
_PREFERRED_PROVIDERS = ["NPUExecutionProvider", "CPUExecutionProvider"]

# Minimum softmax confidence to accept a prediction
_MIN_CONFIDENCE = 0.60

# Image dimensions expected by the ONNX model (width, height)
_MODEL_INPUT_W = 200
_MODEL_INPUT_H = 64


class LocalCaptchaSolver:
    """Solves text-image and math CAPTCHAs using a local ONNX model on NPU/CPU.

    The ONNX model is loaded lazily on first use so that startup is not penalised
    when CAPTCHA solving is not needed.

    Args:
        model_path: Path to the ``captcha_ocr.onnx`` model file.
        char_set:   String of characters the model can predict.
    """

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_PATH,
        char_set: str = _DEFAULT_CHAR_SET,
    ) -> None:
        self._model_path = model_path
        self._char_set = char_set
        self._session: Any | None = None  # onnxruntime.InferenceSession
        self._input_name: str | None = None
        self._provider_used: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_solve(self, captcha_type: CaptchaType) -> bool:
        """Return True when this solver supports *captcha_type*.

        Args:
            captcha_type: The type of CAPTCHA to check.

        Returns:
            True for TEXT and MATH; False for reCAPTCHA, hCaptcha, SLIDER.
        """
        return captcha_type in (CaptchaType.TEXT, CaptchaType.MATH)

    async def solve_text_image(self, image_bytes: bytes) -> str | None:
        """Run ONNX inference on *image_bytes* and return the decoded text.

        The image is preprocessed (grayscale → resize → normalise) before being
        fed to the model. CTC-greedy decoding collapses repeated characters and
        blank tokens.

        Args:
            image_bytes: Raw PNG/JPEG bytes of the CAPTCHA image.

        Returns:
            Decoded text string, or ``None`` when inference fails or confidence
            is below ``_MIN_CONFIDENCE``.
        """
        session = self._get_session()
        if session is None:
            logger.warning("solve_text_image: ONNX session unavailable")
            return None

        try:
            tensor = self._preprocess_image(image_bytes)
            outputs = session.run(None, {self._input_name: tensor})
            text, confidence = self._decode_output(outputs[0])
            logger.debug(
                "solve_text_image: decoded=%r confidence=%.3f provider=%s",
                text,
                confidence,
                self._provider_used,
            )
            if confidence < _MIN_CONFIDENCE:
                logger.info(
                    "solve_text_image: confidence %.3f below threshold %.3f",
                    confidence,
                    _MIN_CONFIDENCE,
                )
                return None
            return text
        except Exception as exc:
            logger.error("solve_text_image: inference failed: %s", exc)
            return None

    def solve_math(self, expression: str) -> str | None:
        """Evaluate a simple arithmetic expression extracted from a CAPTCHA.

        Supports +, -, *, /, ×, ÷.  Division yields integer (floor) result.
        ``eval()`` is never used; parsing is done via regex.

        Args:
            expression: Raw string that may contain the math expression.

        Returns:
            String representation of the integer result, or ``None`` when the
            expression cannot be parsed.
        """
        result = solve_math_expression(expression)
        if result is None:
            logger.debug("solve_math: no solvable expression found in %r", expression)
            return None
        return str(result)

    # ------------------------------------------------------------------
    # ONNX session management
    # ------------------------------------------------------------------

    def _get_session(self) -> Any | None:
        """Return the cached ONNX session, initialising it on first call.

        Attempts NPU execution provider first, then falls back to CPU.

        Returns:
            An ``onnxruntime.InferenceSession`` or ``None`` on failure.
        """
        if self._session is not None:
            return self._session

        try:
            import onnxruntime as ort  # lazy import — not always installed

            available = ort.get_available_providers()
            providers = [p for p in _PREFERRED_PROVIDERS if p in available]
            if not providers:
                providers = ["CPUExecutionProvider"]

            self._session = ort.InferenceSession(self._model_path, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._provider_used = providers[0]
            logger.info(
                "LocalCaptchaSolver: ONNX session loaded from %r using provider %s",
                self._model_path,
                self._provider_used,
            )
        except FileNotFoundError:
            logger.warning(
                "LocalCaptchaSolver: model not found at %r — local ML disabled",
                self._model_path,
            )
            self._session = None
        except Exception as exc:
            logger.error("LocalCaptchaSolver: failed to load ONNX session: %s", exc)
            self._session = None

        return self._session

    # ------------------------------------------------------------------
    # Image preprocessing
    # ------------------------------------------------------------------

    def _preprocess_image(self, image_bytes: bytes) -> Any:
        """Convert raw image bytes to a normalised float32 NCHW tensor.

        Steps:
            1. Open with PIL
            2. Convert to grayscale
            3. Resize to (_MODEL_INPUT_W, _MODEL_INPUT_H)
            4. Normalise pixels to [0, 1]
            5. Add batch and channel dimensions → shape (1, 1, H, W)

        Args:
            image_bytes: Raw image bytes.

        Returns:
            numpy ndarray of shape (1, 1, H, W) dtype float32.
        """
        import numpy as np  # lazy import
        from PIL import Image  # lazy import — Issue #3016 pattern

        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image = image.resize((_MODEL_INPUT_W, _MODEL_INPUT_H))
        arr = np.array(image, dtype=np.float32) / 255.0
        # Shape: (H, W) → (1, 1, H, W)
        return arr[np.newaxis, np.newaxis, :, :]

    # ------------------------------------------------------------------
    # CTC decoding
    # ------------------------------------------------------------------

    def _decode_output(self, logits: Any) -> Tuple[str, float]:
        """Apply CTC greedy decoding to the model logits.

        Expected logits shape: (T, num_classes) where the last class is the CTC
        blank token.

        Args:
            logits: numpy array of shape (T, num_classes).

        Returns:
            Tuple of (decoded_text, mean_confidence).
        """
        import numpy as np  # lazy import

        # Shape: (1, T, C) or (T, C)
        if logits.ndim == 3:
            logits = logits[0]  # Remove batch dim → (T, C)

        # Softmax per time step
        exp_l = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp_l / exp_l.sum(axis=1, keepdims=True)

        best_indices = probs.argmax(axis=1)
        best_probs = probs[np.arange(len(best_indices)), best_indices]

        blank_idx = len(self._char_set)  # Blank is the last class
        chars: list[str] = []
        confidences: list[float] = []
        prev_idx = blank_idx

        for idx, prob in zip(best_indices, best_probs):
            if idx == blank_idx:
                prev_idx = blank_idx
                continue
            if idx == prev_idx:
                continue  # Repeated character — CTC collapse
            if idx < len(self._char_set):
                chars.append(self._char_set[idx])
                confidences.append(float(prob))
            prev_idx = int(idx)

        text = "".join(chars)
        mean_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
        return text, mean_conf


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

# In-process cache: image hash → confirmed answer (reused within the same run)
_answer_cache: Dict[str, str] = {}


def _image_hash(image_bytes: bytes) -> str:
    """Return a hex SHA-256 digest of *image_bytes* for cache keying."""
    return hashlib.sha256(image_bytes).hexdigest()


class CaptchaSolverPipeline:
    """Orchestrates layered CAPTCHA solving.

    Layers (tried in order):
        1. **Local ML** — ONNX model via ``LocalCaptchaSolver``.
        2. **Cache reuse** — prior confirmed answer for the same image hash.
        3. **Human-in-the-loop** — delegates to
           ``services.captcha_human_loop.CaptchaHumanLoop.request_human_intervention``.

    Args:
        solver:     A ``LocalCaptchaSolver`` instance (injectable for testing).
        detector:   A ``CaptchaDetector`` instance (injectable for testing).
        model_path: Forwarded to ``LocalCaptchaSolver`` when *solver* is None.
    """

    def __init__(
        self,
        solver: LocalCaptchaSolver | None = None,
        detector: CaptchaDetector | None = None,
        model_path: str = _DEFAULT_MODEL_PATH,
    ) -> None:
        self._solver = solver or LocalCaptchaSolver(model_path=model_path)
        self._detector = detector or CaptchaDetector()

    async def solve(self, page: Any, captcha_type: CaptchaType) -> CaptchaSolveResult:
        """Attempt to solve the CAPTCHA on *page* of type *captcha_type*.

        Args:
            page:         A Playwright ``Page`` object with the CAPTCHA loaded.
            captcha_type: The type of CAPTCHA to solve.

        Returns:
            A ``CaptchaSolveResult`` describing the outcome.
        """
        logger.info("CaptchaSolverPipeline.solve: type=%s", captcha_type.value)
        start = time.monotonic()

        # Fast path: math CAPTCHAs don't require an image
        if captcha_type == CaptchaType.MATH:
            result = await self._solve_math_from_page(page, captcha_type)
            if result.success:
                return result

        # Attempt local ML for types the solver can handle
        if self._solver.can_solve(captcha_type):
            image_bytes = await self._extract_image(page, captcha_type)
            if image_bytes:
                result = await self._try_local_ml(image_bytes, captcha_type)
                if result.success:
                    elapsed = time.monotonic() - start
                    logger.info(
                        "CaptchaSolverPipeline: solved in %.2fs via %s",
                        elapsed,
                        result.method_used,
                    )
                    return result

                # Layer 2: cache look-up
                cached = _answer_cache.get(_image_hash(image_bytes))
                if cached:
                    logger.info("CaptchaSolverPipeline: cache hit for image hash")
                    return CaptchaSolveResult(
                        success=True,
                        requires_human=False,
                        solution=cached,
                        method_used="cache",
                        confidence_score=1.0,
                        captcha_type=captcha_type,
                    )

        # Layer 3: human-in-the-loop
        return await self._human_fallback(page, captcha_type)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _solve_math_from_page(self, page: Any, captcha_type: CaptchaType) -> CaptchaSolveResult:
        """Extract page text and attempt math solving.

        Args:
            page:         Playwright Page.
            captcha_type: Should be CaptchaType.MATH.

        Returns:
            CaptchaSolveResult with method_used="math" on success.
        """
        try:
            content: str = await page.content()
            answer = self._solver.solve_math(content)
            if answer is not None:
                return CaptchaSolveResult(
                    success=True,
                    requires_human=False,
                    solution=answer,
                    method_used="math",
                    confidence_score=1.0,
                    captcha_type=captcha_type,
                )
        except Exception as exc:
            logger.warning("_solve_math_from_page failed: %s", exc)
        return CaptchaSolveResult(
            success=False,
            solution=None,
            method_used="math",
            confidence_score=0.0,
            captcha_type=captcha_type,
            error_message="Math expression not found in page content",
        )

    async def _extract_image(self, page: Any, captcha_type: CaptchaType) -> bytes | None:
        """Pick the right selector and extract the CAPTCHA image bytes.

        Args:
            page:         Playwright Page.
            captcha_type: Used to choose the CSS selector.

        Returns:
            PNG bytes or ``None``.
        """
        selector = self._selector_for_type(captcha_type, page)
        return await self._detector.extract_captcha_image(page, selector)

    def _selector_for_type(self, captcha_type: CaptchaType, page: Any) -> str:
        """Map a CaptchaType to the most appropriate CSS selector.

        Args:
            captcha_type: Type to look up.
            page:         Not used, reserved for future page-aware selection.

        Returns:
            CSS selector string.
        """
        mapping = {
            CaptchaType.TEXT: CaptchaDetector._TEXT_IMAGE_SELECTORS[0],
            CaptchaType.MATH: CaptchaDetector._TEXT_IMAGE_SELECTORS[0],
            CaptchaType.SLIDER: CaptchaDetector._SLIDER_SELECTORS[0],
            CaptchaType.RECAPTCHA: CaptchaDetector._RECAPTCHA_SELECTORS[0],
            CaptchaType.HCAPTCHA: CaptchaDetector._HCAPTCHA_SELECTORS[0],
        }
        return mapping.get(captcha_type, "#captcha")

    async def _try_local_ml(self, image_bytes: bytes, captcha_type: CaptchaType) -> CaptchaSolveResult:
        """Run ONNX inference and return a CaptchaSolveResult.

        Args:
            image_bytes:  Raw image bytes.
            captcha_type: Type being solved (TEXT or MATH).

        Returns:
            CaptchaSolveResult with method_used="local_ml".
        """
        answer = await self._solver.solve_text_image(image_bytes)
        if answer:
            # Store in cache for future reuse within this process
            _answer_cache[_image_hash(image_bytes)] = answer
            return CaptchaSolveResult(
                success=True,
                requires_human=False,
                solution=answer,
                method_used="local_ml",
                confidence_score=_MIN_CONFIDENCE,
                captcha_type=captcha_type,
            )
        return CaptchaSolveResult(
            success=False,
            solution=None,
            method_used="local_ml",
            confidence_score=0.0,
            captcha_type=captcha_type,
            error_message="ONNX inference returned no answer",
        )

    async def _human_fallback(self, page: Any, captcha_type: CaptchaType) -> CaptchaSolveResult:
        """Delegate to the human-in-the-loop service.

        Args:
            page:         Playwright Page.
            captcha_type: Type of CAPTCHA for logging/routing.

        Returns:
            CaptchaSolveResult with method_used="human_loop".
        """
        logger.info(
            "CaptchaSolverPipeline: falling back to human-in-the-loop for type=%s",
            captcha_type.value,
        )
        try:
            service = get_captcha_human_loop()
            url: str = page.url
            resolution = await service.request_human_intervention(
                page=page,
                url=url,
                captcha_type=captcha_type.value,
            )
            return CaptchaSolveResult(
                success=resolution.success,
                requires_human=False,
                solution=None,  # Human solves in-browser; no answer text returned
                method_used="human_loop",
                confidence_score=1.0 if resolution.success else 0.0,
                captcha_type=captcha_type,
                error_message=resolution.error_message if not resolution.success else None,
            )
        except Exception as exc:
            logger.error("_human_fallback: human-in-the-loop failed: %s", exc)
            return CaptchaSolveResult(
                success=False,
                solution=None,
                method_used="human_loop",
                confidence_score=0.0,
                captcha_type=captcha_type,
                error_message=str(exc),
            )
