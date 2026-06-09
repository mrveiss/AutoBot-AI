# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for agents.browser.captcha_solver (Issue #1974)

Covers:
    - CaptchaDetector.detect() — all CaptchaType values
    - CaptchaDetector.extract_captcha_image() — success and element-not-found paths
    - LocalCaptchaSolver.can_solve() — supported and unsupported types
    - LocalCaptchaSolver.solve_math() — happy path, operator variants, edge cases
    - LocalCaptchaSolver.solve_text_image() — session-unavailable and low-confidence paths
    - CaptchaSolverPipeline.solve() — ML success, cache hit, human fallback, math fast-path
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.browser.captcha_solver import (
    CaptchaDetector,
    CaptchaSolverPipeline,
    CaptchaType,
    LocalCaptchaSolver,
    SolveResult,
    _answer_cache,
    _image_hash,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_answer_cache():
    """Ensure the in-process answer cache is empty before every test."""
    _answer_cache.clear()
    yield
    _answer_cache.clear()


# ---------------------------------------------------------------------------
# CaptchaDetector.detect()
# ---------------------------------------------------------------------------


class TestCaptchaDetectorDetect:
    def setup_method(self):
        self.detector = CaptchaDetector()

    def test_recaptcha_detected_by_keyword(self):
        html = '<script src="https://www.google.com/recaptcha/api.js"></script>'
        assert self.detector.detect(html) == CaptchaType.RECAPTCHA

    def test_recaptcha_detected_by_class(self):
        html = '<div class="g-recaptcha" data-sitekey="abc"></div>'
        assert self.detector.detect(html) == CaptchaType.RECAPTCHA

    def test_hcaptcha_detected(self):
        html = '<div class="h-captcha" data-sitekey="xyz"></div>'
        assert self.detector.detect(html) == CaptchaType.HCAPTCHA

    def test_hcaptcha_iframe_detected(self):
        html = '<iframe src="https://newassets.hcaptcha.com/c/xxx"></iframe>'
        assert self.detector.detect(html) == CaptchaType.HCAPTCHA

    def test_slider_detected(self):
        html = '<div class="slider-captcha">drag me</div>'
        assert self.detector.detect(html) == CaptchaType.SLIDER

    def test_math_captcha_detected(self):
        html = "<p>Please solve: 3 + 4 = ? to prove you are human</p>"
        assert self.detector.detect(html) == CaptchaType.MATH

    def test_text_image_detected_by_keyword(self):
        html = '<img id="captcha" src="/captcha.png">'
        assert self.detector.detect(html) == CaptchaType.TEXT_IMAGE

    def test_text_image_detected_verify_phrase(self):
        html = "<p>Verification required</p><img class='captcha' src='/c.png'>"
        assert self.detector.detect(html) == CaptchaType.TEXT_IMAGE

    def test_unknown_when_no_pattern(self):
        html = "<p>Hello world</p>"
        assert self.detector.detect(html) == CaptchaType.UNKNOWN

    def test_recaptcha_takes_priority_over_hcaptcha(self):
        # Both patterns present — reCAPTCHA is checked first
        html = '<div class="g-recaptcha"></div>' '<div class="h-captcha"></div>'
        assert self.detector.detect(html) == CaptchaType.RECAPTCHA

    def test_case_insensitive(self):
        html = '<SCRIPT SRC="HTTPS://WWW.GOOGLE.COM/RECAPTCHA/API.JS"></SCRIPT>'
        assert self.detector.detect(html) == CaptchaType.RECAPTCHA


# ---------------------------------------------------------------------------
# CaptchaDetector.extract_captcha_image()
# ---------------------------------------------------------------------------


class TestCaptchaDetectorExtractImage:
    def setup_method(self):
        self.detector = CaptchaDetector()

    @pytest.mark.asyncio
    async def test_returns_bytes_when_element_found(self):
        page = MagicMock()
        element = AsyncMock()
        element.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
        page.query_selector = AsyncMock(return_value=element)

        result = await self.detector.extract_captcha_image(page, "#captcha")
        assert result == b"\x89PNG\r\n"
        page.query_selector.assert_awaited_once_with("#captcha")

    @pytest.mark.asyncio
    async def test_returns_none_when_element_not_found(self):
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=None)

        result = await self.detector.extract_captcha_image(page, "#captcha")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_playwright_exception(self):
        page = MagicMock()
        page.query_selector = AsyncMock(side_effect=RuntimeError("playwright error"))

        result = await self.detector.extract_captcha_image(page, "#captcha")
        assert result is None


# ---------------------------------------------------------------------------
# LocalCaptchaSolver.can_solve()
# ---------------------------------------------------------------------------


class TestLocalCaptchaSolverCanSolve:
    def setup_method(self):
        self.solver = LocalCaptchaSolver()

    @pytest.mark.parametrize(
        "captcha_type, expected",
        [
            (CaptchaType.TEXT_IMAGE, True),
            (CaptchaType.MATH, True),
            (CaptchaType.RECAPTCHA, False),
            (CaptchaType.HCAPTCHA, False),
            (CaptchaType.SLIDER, False),
            (CaptchaType.UNKNOWN, False),
        ],
    )
    def test_can_solve(self, captcha_type, expected):
        assert self.solver.can_solve(captcha_type) is expected


# ---------------------------------------------------------------------------
# LocalCaptchaSolver.solve_math()
# ---------------------------------------------------------------------------


class TestLocalCaptchaSolverSolveMath:
    def setup_method(self):
        self.solver = LocalCaptchaSolver()

    def test_addition(self):
        assert self.solver.solve_math("3 + 4 = ?") == "7"

    def test_subtraction(self):
        assert self.solver.solve_math("10 - 3 = ?") == "7"

    def test_multiplication_asterisk(self):
        assert self.solver.solve_math("6 * 7 = ?") == "42"

    def test_multiplication_unicode_times(self):
        assert self.solver.solve_math("6 × 7 = ?") == "42"

    def test_multiplication_letter_x(self):
        assert self.solver.solve_math("4 x 5 = ?") == "20"

    def test_division(self):
        assert self.solver.solve_math("12 / 4 = ?") == "3"

    def test_division_unicode_obelus(self):
        assert self.solver.solve_math("15 ÷ 3 = ?") == "5"

    def test_division_by_zero_returns_none(self):
        assert self.solver.solve_math("5 / 0 = ?") is None

    def test_no_expression_returns_none(self):
        assert self.solver.solve_math("please enter the captcha") is None

    def test_embedded_in_html_context(self):
        html_snippet = "<p>Solve: 8 + 9 = ?</p>"
        assert self.solver.solve_math(html_snippet) == "17"

    def test_spelled_out_plus(self):
        assert self.solver.solve_math("2 PLUS 3 = ?") == "5"

    def test_spelled_out_minus(self):
        assert self.solver.solve_math("9 MINUS 4 = ?") == "5"

    def test_trailing_equals_stripped(self):
        assert self.solver.solve_math("7 + 2 =") == "9"


# ---------------------------------------------------------------------------
# LocalCaptchaSolver.solve_text_image()
# ---------------------------------------------------------------------------


class TestLocalCaptchaSolverSolveTextImage:
    def setup_method(self):
        self.solver = LocalCaptchaSolver(model_path="nonexistent_model.onnx")

    @pytest.mark.asyncio
    async def test_returns_none_when_model_missing(self):
        """When the model file does not exist, solve_text_image returns None gracefully."""
        result = await self.solver.solve_text_image(b"fake image bytes")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_low_confidence(self):
        """If inference gives below-threshold confidence, None is returned."""
        import numpy as np

        session_mock = MagicMock()
        # Simulate logits: 4 time steps, 37 classes (36 chars + 1 blank).
        # All probability mass on blank → confidence = 0 → below threshold.
        logits = np.zeros((1, 4, 37), dtype=np.float32)
        logits[0, :, 36] = 10.0  # Push all weight to blank class
        session_mock.run.return_value = [logits]
        session_mock.get_inputs.return_value = [MagicMock(name="input")]

        self.solver._session = session_mock
        self.solver._input_name = "input"
        self.solver._provider_used = "CPUExecutionProvider"

        result = await self.solver.solve_text_image(b"\x89PNG\r\nfake")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_text_on_sufficient_confidence(self):
        """With high-confidence logits the decoded text is returned."""
        import numpy as np

        # char_set "AB..." index 0 → 'A', index 1 → 'B'
        solver = LocalCaptchaSolver(char_set="AB")
        num_classes = 3  # A, B, blank(=2)
        logits = np.full((1, 2, num_classes), -10.0, dtype=np.float32)
        # Time step 0 → class 0 ('A') with high confidence
        logits[0, 0, 0] = 10.0
        # Time step 1 → class 1 ('B') with high confidence
        logits[0, 1, 1] = 10.0

        session_mock = MagicMock()
        session_mock.run.return_value = [logits]
        session_mock.get_inputs.return_value = [MagicMock(name="input")]

        solver._session = session_mock
        solver._input_name = "input"
        solver._provider_used = "NPUExecutionProvider"

        # Provide minimal valid PNG-like bytes; preprocessing is mocked via PIL stub
        with patch("agents.browser.captcha_solver.LocalCaptchaSolver._preprocess_image") as pp:
            pp.return_value = np.zeros((1, 1, 64, 200), dtype=np.float32)
            result = await solver.solve_text_image(b"fake_image_bytes")

        assert result == "AB"


# ---------------------------------------------------------------------------
# CaptchaSolverPipeline.solve()
# ---------------------------------------------------------------------------


class TestCaptchaSolverPipeline:
    def _make_pipeline(self, solver=None, detector=None):
        return CaptchaSolverPipeline(solver=solver, detector=detector)

    @pytest.mark.asyncio
    async def test_math_fast_path_returns_success(self):
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = True
        solver.solve_math.return_value = "7"

        page = MagicMock()
        page.content = AsyncMock(return_value="<p>3 + 4 = ?</p>")

        pipeline = self._make_pipeline(solver=solver)
        result = await pipeline.solve(page, CaptchaType.MATH)

        assert result.success is True
        assert result.answer == "7"
        assert result.method_used == "math"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_local_ml_success_path(self):
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = True
        solver.solve_math.return_value = None
        solver.solve_text_image = AsyncMock(return_value="ABCD12")

        detector = MagicMock(spec=CaptchaDetector)
        detector.extract_captcha_image = AsyncMock(return_value=b"image_bytes")

        page = MagicMock()
        page.content = AsyncMock(return_value="<p>no expression here</p>")

        pipeline = self._make_pipeline(solver=solver, detector=detector)
        result = await pipeline.solve(page, CaptchaType.TEXT_IMAGE)

        assert result.success is True
        assert result.answer == "ABCD12"
        assert result.method_used == "local_ml"

    @pytest.mark.asyncio
    async def test_cache_hit_path(self):
        image_bytes = b"cached_image"
        fake_hash = _image_hash(image_bytes)
        _answer_cache[fake_hash] = "CACHED"

        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = True
        solver.solve_text_image = AsyncMock(return_value=None)  # ML fails

        detector = MagicMock(spec=CaptchaDetector)
        detector.extract_captcha_image = AsyncMock(return_value=image_bytes)

        page = MagicMock()
        page.content = AsyncMock(return_value="<img class='captcha'>")

        pipeline = self._make_pipeline(solver=solver, detector=detector)
        result = await pipeline.solve(page, CaptchaType.TEXT_IMAGE)

        assert result.success is True
        assert result.answer == "CACHED"
        assert result.method_used == "cache"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_human_fallback_when_ml_and_cache_fail(self):
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = True
        solver.solve_text_image = AsyncMock(return_value=None)

        detector = MagicMock(spec=CaptchaDetector)
        detector.extract_captcha_image = AsyncMock(return_value=b"unknown_image")

        page = MagicMock()
        page.url = "https://example.com"
        page.content = AsyncMock(return_value="<img class='captcha'>")

        human_result = MagicMock()
        human_result.success = True
        human_result.error_message = None

        with patch("agents.browser.captcha_solver.get_captcha_human_loop") as mock_get_loop:
            loop_instance = AsyncMock()
            loop_instance.request_human_intervention = AsyncMock(return_value=human_result)
            mock_get_loop.return_value = loop_instance

            pipeline = self._make_pipeline(solver=solver, detector=detector)
            result = await pipeline.solve(page, CaptchaType.TEXT_IMAGE)

        assert result.success is True
        assert result.method_used == "human_loop"

    @pytest.mark.asyncio
    async def test_human_fallback_for_recaptcha(self):
        """reCAPTCHA is not solvable locally — pipeline skips to human fallback."""
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = False  # LocalCaptchaSolver can't handle reCAPTCHA

        detector = MagicMock(spec=CaptchaDetector)

        page = MagicMock()
        page.url = "https://example.com"

        human_result = MagicMock()
        human_result.success = False
        human_result.error_message = "timeout"

        with patch("agents.browser.captcha_solver.get_captcha_human_loop") as mock_get_loop:
            loop_instance = AsyncMock()
            loop_instance.request_human_intervention = AsyncMock(return_value=human_result)
            mock_get_loop.return_value = loop_instance

            pipeline = self._make_pipeline(solver=solver, detector=detector)
            result = await pipeline.solve(page, CaptchaType.RECAPTCHA)

        assert result.success is False
        assert result.method_used == "human_loop"
        assert result.error == "timeout"

    @pytest.mark.asyncio
    async def test_human_fallback_exception_returns_failure(self):
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = False

        page = MagicMock()
        page.url = "https://example.com"

        with patch(
            "agents.browser.captcha_solver.get_captcha_human_loop",
            side_effect=ImportError("no module"),
        ):
            pipeline = self._make_pipeline(solver=solver)
            result = await pipeline.solve(page, CaptchaType.HCAPTCHA)

        assert result.success is False
        assert result.method_used == "human_loop"
        assert "no module" in result.error

    @pytest.mark.asyncio
    async def test_image_extraction_failure_goes_to_human(self):
        """When image extraction fails, the pipeline still falls back to human."""
        solver = MagicMock(spec=LocalCaptchaSolver)
        solver.can_solve.return_value = True

        detector = MagicMock(spec=CaptchaDetector)
        detector.extract_captcha_image = AsyncMock(return_value=None)  # extraction fails

        page = MagicMock()
        page.url = "https://example.com"
        page.content = AsyncMock(return_value="<img class='captcha'>")

        human_result = MagicMock()
        human_result.success = True
        human_result.error_message = None

        with patch("agents.browser.captcha_solver.get_captcha_human_loop") as mock_get_loop:
            loop_instance = AsyncMock()
            loop_instance.request_human_intervention = AsyncMock(return_value=human_result)
            mock_get_loop.return_value = loop_instance

            pipeline = self._make_pipeline(solver=solver, detector=detector)
            result = await pipeline.solve(page, CaptchaType.TEXT_IMAGE)

        assert result.success is True
        assert result.method_used == "human_loop"

    @pytest.mark.asyncio
    async def test_solve_result_dataclass_fields(self):
        """SolveResult has all required fields."""
        r = SolveResult(
            success=True,
            answer="TEST",
            method_used="local_ml",
            confidence=0.95,
            captcha_type=CaptchaType.TEXT_IMAGE,
        )
        assert r.success is True
        assert r.answer == "TEST"
        assert r.method_used == "local_ml"
        assert r.confidence == 0.95
        assert r.captcha_type == CaptchaType.TEXT_IMAGE
        assert r.error is None
