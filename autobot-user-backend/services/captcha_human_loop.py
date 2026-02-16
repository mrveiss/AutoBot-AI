# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CAPTCHA Human-in-the-Loop Service

This module provides a hybrid CAPTCHA handling mechanism:
1. First attempts automatic OCR-based solving for simple CAPTCHAs
2. Falls back to human-in-the-loop for complex CAPTCHAs (reCAPTCHA, hCaptcha, etc.)

Features:
- Automatic OCR solving for text/math CAPTCHAs
- WebSocket notifications when human intervention needed
- Screenshot capture for CAPTCHA display
- Async wait mechanism with configurable timeout
- Resolution confirmation handling
- Graceful timeout fallback

Usage:
    from backend.services.captcha_human_loop import CaptchaHumanLoop

    captcha_service = CaptchaHumanLoop(timeout_seconds=120)
    result = await captcha_service.request_human_intervention(
        page=page,
        url="https://example.com"
    )
    if result.success:
        # Continue with page interaction
        ...
    else:
        # Skip this source
        ...

Related: Issue #206
"""

import asyncio
import base64
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from backend.constants.network_constants import NetworkConstants
from backend.constants.threshold_constants import TimingConstants
from event_manager import event_manager
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for unsupported CAPTCHA types (require human intervention)
_UNSUPPORTED_CAPTCHA_TYPES = ("recaptcha", "hcaptcha", "cloudflare")


class CaptchaResolutionStatus(Enum):
    """Status of CAPTCHA resolution attempt"""

    PENDING = "pending"
    SOLVED = "solved"
    AUTO_SOLVED = "auto_solved"  # Solved automatically via OCR
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CaptchaResolutionResult:
    """Result of a CAPTCHA resolution attempt"""

    success: bool
    status: CaptchaResolutionStatus
    captcha_id: str
    url: str
    duration_seconds: float
    error_message: Optional[str] = None
    auto_solution: Optional[str] = None  # Solution from automatic solver
    auto_confidence: Optional[str] = None  # Confidence level (high/medium/low)


class CaptchaHumanLoop:
    """
    Hybrid CAPTCHA handling service.

    First attempts automatic OCR-based solving for simple CAPTCHAs,
    then falls back to WebSocket-based human intervention for complex ones.
    """

    # Store pending CAPTCHA resolutions
    _pending_resolutions: Dict[str, asyncio.Event] = {}
    _resolution_results: Dict[str, CaptchaResolutionStatus] = {}

    def __init__(
        self,
        timeout_seconds: float = 120.0,
        auto_skip_on_timeout: bool = True,
        vnc_url: Optional[str] = None,
        enable_auto_solve: bool = True,
    ):
        """
        Initialize the CAPTCHA handling service.

        Args:
            timeout_seconds: Maximum time to wait for human resolution (default: 120s)
            auto_skip_on_timeout: Whether to skip source on timeout (default: True)
            vnc_url: URL for VNC desktop interface (auto-detected if not provided)
            enable_auto_solve: Whether to attempt automatic solving first (default: True)
        """
        self.timeout_seconds = timeout_seconds
        self.auto_skip_on_timeout = auto_skip_on_timeout
        # Use environment variable or NetworkConstants for VNC URL
        vnc_host = os.getenv("AUTOBOT_VNC_HOST", NetworkConstants.LOCALHOST_IP)
        vnc_port = os.getenv("AUTOBOT_VNC_PORT", str(NetworkConstants.VNC_PORT))
        self.vnc_url = vnc_url or f"http://{vnc_host}:{vnc_port}/vnc.html"
        self.enable_auto_solve = enable_auto_solve
        self._auto_solver = None

    def _get_auto_solver(self):
        """Lazy load the automatic CAPTCHA solver."""
        if self._auto_solver is None and self.enable_auto_solve:
            try:
                from backend.services.captcha_solver import get_captcha_solver

                self._auto_solver = get_captcha_solver()
            except ImportError as e:
                logger.warning("Auto CAPTCHA solver not available: %s", e)
                self.enable_auto_solve = False
        return self._auto_solver

    def _can_auto_solve(self, captcha_type: str) -> bool:
        """Check if auto-solving should be attempted (Issue #315: extracted).

        Args:
            captcha_type: Type of CAPTCHA detected

        Returns:
            True if auto-solving is enabled and type is supported
        """
        return (
            self.enable_auto_solve and captcha_type not in _UNSUPPORTED_CAPTCHA_TYPES
        )  # Issue #380

    async def _try_auto_fill(
        self,
        page: Page,
        captcha_input_selector: str,
        solution: str,
    ) -> bool:
        """Try to auto-fill CAPTCHA solution (Issue #315: extracted).

        Args:
            page: Playwright page
            captcha_input_selector: CSS selector for input
            solution: Solution to fill

        Returns:
            True if fill succeeded, False otherwise
        """
        try:
            await page.fill(captcha_input_selector, solution)
            await page.keyboard.press("Enter")
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)  # Wait for response
            return True
        except Exception as e:
            logger.warning("Auto-fill failed, falling back: %s", e)
            return False

    def _build_auto_solve_result(
        self,
        captcha_id: str,
        url: str,
        start_time: datetime,
        solution: str,
        confidence: str,
    ) -> CaptchaResolutionResult:
        """
        Build result for successful auto-solve.

        Issue #620.
        """
        duration = (datetime.utcnow() - start_time).total_seconds()
        return CaptchaResolutionResult(
            success=True,
            status=CaptchaResolutionStatus.AUTO_SOLVED,
            captcha_id=captcha_id,
            url=url,
            duration_seconds=duration,
            auto_solution=solution,
            auto_confidence=confidence,
        )

    async def _handle_auto_solve(
        self,
        page: Page,
        screenshot: bytes,
        captcha_type: str,
        captcha_input_selector: Optional[str],
        captcha_id: str,
        url: str,
        start_time: datetime,
    ) -> Optional[CaptchaResolutionResult]:
        """
        Attempt automatic CAPTCHA solving.

        Issue #620: Refactored to use _build_auto_solve_result helper.

        Returns:
            CaptchaResolutionResult if solved, None to continue to human fallback
        """
        if not self._can_auto_solve(captcha_type):
            return None

        auto_result = await self._attempt_auto_solve(screenshot, captcha_type)
        if not auto_result or not auto_result.get("success"):
            return None

        solution = auto_result.get("solution")
        confidence = auto_result.get("confidence", "medium")
        logger.info("CAPTCHA auto-solved with %s confidence: %s", confidence, solution)

        if captcha_input_selector and solution:
            if await self._try_auto_fill(page, captcha_input_selector, solution):
                return self._build_auto_solve_result(
                    captcha_id, url, start_time, solution, confidence
                )

        if solution:
            return self._build_auto_solve_result(
                captcha_id, url, start_time, solution, confidence
            )

        return None

    async def _wait_for_human_resolution(
        self, captcha_id: str, url: str, resolution_event: asyncio.Event
    ) -> tuple[CaptchaResolutionStatus, bool]:
        """Wait for human resolution with timeout handling."""
        try:
            await asyncio.wait_for(
                resolution_event.wait(),
                timeout=self.timeout_seconds,
            )

            status = self._resolution_results.get(
                captcha_id, CaptchaResolutionStatus.ERROR
            )
            success = status == CaptchaResolutionStatus.SOLVED

            if success:
                logger.info("CAPTCHA %s solved by user", captcha_id)
            else:
                logger.info("CAPTCHA %s skipped by user", captcha_id)

            return status, success

        except asyncio.TimeoutError:
            logger.warning("CAPTCHA resolution timeout after %ss", self.timeout_seconds)
            await self._notify_captcha_timeout(captcha_id, url)
            return CaptchaResolutionStatus.TIMEOUT, False

    def _build_error_result(
        self,
        captcha_id: str,
        url: str,
        start_time: datetime,
        error_message: str,
    ) -> CaptchaResolutionResult:
        """Build error result for CAPTCHA intervention failures.

        Args:
            captcha_id: Unique identifier for the CAPTCHA
            url: URL where CAPTCHA was encountered
            start_time: When the intervention started
            error_message: Description of the error

        Returns:
            CaptchaResolutionResult with error status. Issue #620.
        """
        return CaptchaResolutionResult(
            success=False,
            status=CaptchaResolutionStatus.ERROR,
            captcha_id=captcha_id,
            url=url,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            error_message=error_message,
        )

    async def _setup_human_intervention(
        self, captcha_id: str, url: str, captcha_type: str, screenshot_b64: str
    ) -> asyncio.Event:
        """Set up tracking and notify frontend for human intervention.

        Args:
            captcha_id: Unique identifier for the CAPTCHA
            url: URL where CAPTCHA was encountered
            captcha_type: Type of CAPTCHA detected
            screenshot_b64: Base64 encoded screenshot

        Returns:
            Event to wait on for resolution. Issue #620.
        """
        resolution_event = asyncio.Event()
        self._pending_resolutions[captcha_id] = resolution_event
        self._resolution_results[captcha_id] = CaptchaResolutionStatus.PENDING

        await self._notify_captcha_detected(
            captcha_id=captcha_id,
            url=url,
            captcha_type=captcha_type,
            screenshot_b64=screenshot_b64,
        )
        return resolution_event

    async def _capture_screenshot_b64(self, page: Page) -> str:
        """Capture page screenshot and encode as base64.

        Args:
            page: Playwright page to capture

        Returns:
            Base64-encoded screenshot string. Issue #620.
        """
        screenshot = await page.screenshot(full_page=False)
        return base64.b64encode(screenshot).decode("utf-8")

    def _cleanup_captcha_tracking(self, captcha_id: str) -> None:
        """Remove CAPTCHA from pending tracking dictionaries.

        Args:
            captcha_id: ID of CAPTCHA to clean up. Issue #620.
        """
        self._pending_resolutions.pop(captcha_id, None)
        self._resolution_results.pop(captcha_id, None)

    def _build_final_result(
        self,
        success: bool,
        status: CaptchaResolutionStatus,
        captcha_id: str,
        url: str,
        start_time: datetime,
    ) -> CaptchaResolutionResult:
        """Build final CAPTCHA resolution result.

        Args:
            success: Whether resolution was successful
            status: Resolution status
            captcha_id: CAPTCHA identifier
            url: URL where CAPTCHA was encountered
            start_time: When intervention started

        Returns:
            CaptchaResolutionResult with final status. Issue #620.
        """
        return CaptchaResolutionResult(
            success=success,
            status=status,
            captcha_id=captcha_id,
            url=url,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
        )

    async def _try_auto_solve_flow(
        self,
        page: Page,
        captcha_type: str,
        captcha_input_selector: Optional[str],
        captcha_id: str,
        url: str,
        start_time: datetime,
    ) -> tuple[Optional[CaptchaResolutionResult], str]:
        """Attempt auto-solve and return result with screenshot base64.

        Args:
            page: Playwright page with CAPTCHA
            captcha_type: Type of CAPTCHA detected
            captcha_input_selector: CSS selector for input field
            captcha_id: Unique CAPTCHA identifier
            url: URL where CAPTCHA was encountered
            start_time: When intervention started

        Returns:
            Tuple of (auto_result or None, screenshot_b64). Issue #620.
        """
        screenshot_b64 = await self._capture_screenshot_b64(page)
        screenshot = base64.b64decode(screenshot_b64)

        auto_result = await self._handle_auto_solve(
            page,
            screenshot,
            captcha_type,
            captcha_input_selector,
            captcha_id,
            url,
            start_time,
        )
        return auto_result, screenshot_b64

    async def _human_intervention_flow(
        self,
        captcha_id: str,
        url: str,
        captcha_type: str,
        screenshot_b64: str,
    ) -> tuple[CaptchaResolutionStatus, bool]:
        """Execute human intervention flow and return status.

        Args:
            captcha_id: Unique CAPTCHA identifier
            url: URL where CAPTCHA was encountered
            captcha_type: Type of CAPTCHA detected
            screenshot_b64: Base64-encoded screenshot

        Returns:
            Tuple of (status, success). Issue #620.
        """
        logger.info("Requesting human intervention for CAPTCHA at %s", url)
        resolution_event = await self._setup_human_intervention(
            captcha_id, url, captcha_type, screenshot_b64
        )
        return await self._wait_for_human_resolution(captcha_id, url, resolution_event)

    async def request_human_intervention(
        self,
        page: Page,
        url: str,
        captcha_type: str = "unknown",
        captcha_input_selector: Optional[str] = None,
    ) -> CaptchaResolutionResult:
        """Handle CAPTCHA with automatic solving attempt, then human fallback.

        Args:
            page: Playwright page with CAPTCHA
            url: URL where CAPTCHA was encountered
            captcha_type: Type of CAPTCHA (recaptcha, hcaptcha, cloudflare, etc.)
            captcha_input_selector: CSS selector for CAPTCHA input field (if known)

        Returns:
            CaptchaResolutionResult with success status and details.
        """
        captcha_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        logger.info("Handling CAPTCHA at %s (type: %s)", url, captcha_type)

        try:
            auto_result, screenshot_b64 = await self._try_auto_solve_flow(
                page,
                captcha_type,
                captcha_input_selector,
                captcha_id,
                url,
                start_time,
            )
            if auto_result:
                return auto_result

            status, success = await self._human_intervention_flow(
                captcha_id, url, captcha_type, screenshot_b64
            )

        except Exception as e:
            logger.error("Error requesting CAPTCHA intervention: %s", e)
            return self._build_error_result(captcha_id, url, start_time, str(e))

        finally:
            self._cleanup_captcha_tracking(captcha_id)

        return self._build_final_result(success, status, captcha_id, url, start_time)

    async def mark_captcha_resolved(
        self,
        captcha_id: str,
        status: CaptchaResolutionStatus = CaptchaResolutionStatus.SOLVED,
    ) -> bool:
        """
        Mark a CAPTCHA as resolved (called from frontend via API).

        Args:
            captcha_id: ID of the CAPTCHA to mark as resolved
            status: Resolution status (SOLVED or SKIPPED)

        Returns:
            bool: True if CAPTCHA was found and marked, False otherwise
        """
        if captcha_id not in self._pending_resolutions:
            logger.warning("Unknown CAPTCHA ID: %s", captcha_id)
            return False

        self._resolution_results[captcha_id] = status
        self._pending_resolutions[captcha_id].set()

        logger.info("CAPTCHA %s marked as %s", captcha_id, status.value)
        return True

    async def _notify_captcha_detected(
        self,
        captcha_id: str,
        url: str,
        captcha_type: str,
        screenshot_b64: str,
    ) -> None:
        """Send WebSocket notification that CAPTCHA was detected."""
        await event_manager.publish(
            "captcha_detected",
            {
                "captcha_id": captcha_id,
                "url": url,
                "captcha_type": captcha_type,
                "screenshot": screenshot_b64,
                "vnc_url": self.vnc_url,
                "timeout_seconds": self.timeout_seconds,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"CAPTCHA detected at {url}. Please solve manually via VNC.",
            },
        )

    async def _notify_captcha_timeout(self, captcha_id: str, url: str) -> None:
        """Send WebSocket notification that CAPTCHA resolution timed out."""
        await event_manager.publish(
            "captcha_timeout",
            {
                "captcha_id": captcha_id,
                "url": url,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"CAPTCHA resolution timed out for {url}. Source will be skipped.",
            },
        )

    async def _notify_captcha_resolved(
        self, captcha_id: str, url: str, status: CaptchaResolutionStatus
    ) -> None:
        """Send WebSocket notification that CAPTCHA was resolved."""
        await event_manager.publish(
            "captcha_resolved",
            {
                "captcha_id": captcha_id,
                "url": url,
                "status": status.value,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def get_pending_captchas(self) -> Dict[str, Any]:
        """Get list of pending CAPTCHA resolutions (for API status endpoint)."""
        return {
            captcha_id: {
                "status": self._resolution_results.get(
                    captcha_id, CaptchaResolutionStatus.PENDING
                ).value
            }
            for captcha_id in self._pending_resolutions.keys()
        }

    async def _attempt_auto_solve(
        self, screenshot: bytes, captcha_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to automatically solve the CAPTCHA using OCR.

        Args:
            screenshot: Raw screenshot bytes
            captcha_type: Type of CAPTCHA detected

        Returns:
            Dict with 'success', 'solution', 'confidence' or None if failed
        """
        solver = self._get_auto_solver()
        if not solver:
            return None

        try:
            from backend.services.captcha_solver import CaptchaType

            # Map string type to enum
            type_map = {
                "text": CaptchaType.TEXT,
                "math": CaptchaType.MATH,
                "recaptcha": CaptchaType.RECAPTCHA,
                "hcaptcha": CaptchaType.HCAPTCHA,
                "cloudflare": CaptchaType.CLOUDFLARE,
                "unknown": CaptchaType.UNKNOWN,
            }
            captcha_type_enum = type_map.get(captcha_type, CaptchaType.UNKNOWN)

            result = await solver.attempt_solve(
                image_data=screenshot,
                captcha_type=captcha_type_enum,
            )

            if result.success:
                return {
                    "success": True,
                    "solution": result.solution,
                    "confidence": result.confidence.value,
                    "type": result.captcha_type.value,
                }

            return {
                "success": False,
                "requires_human": result.requires_human,
                "error": result.error_message,
            }

        except Exception as e:
            logger.warning("Auto-solve attempt failed: %s", e)
            return None


# Global singleton instance (thread-safe)
import threading

_captcha_human_loop: Optional[CaptchaHumanLoop] = None
_captcha_human_loop_lock = threading.Lock()


def get_captcha_human_loop(
    timeout_seconds: float = 120.0,
    auto_skip_on_timeout: bool = True,
) -> CaptchaHumanLoop:
    """
    Get or create the global CaptchaHumanLoop instance (thread-safe).

    Args:
        timeout_seconds: Timeout for human resolution
        auto_skip_on_timeout: Whether to skip on timeout

    Returns:
        CaptchaHumanLoop: Global instance
    """
    global _captcha_human_loop

    if _captcha_human_loop is None:
        with _captcha_human_loop_lock:
            # Double-check after acquiring lock
            if _captcha_human_loop is None:
                _captcha_human_loop = CaptchaHumanLoop(
                    timeout_seconds=timeout_seconds,
                    auto_skip_on_timeout=auto_skip_on_timeout,
                )

    return _captcha_human_loop
