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
    from src.services.captcha_human_loop import CaptchaHumanLoop

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
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from playwright.async_api import Page

from src.event_manager import event_manager

logger = logging.getLogger(__name__)


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
        self.vnc_url = vnc_url or "http://127.0.0.1:6080/vnc.html"
        self.enable_auto_solve = enable_auto_solve
        self._auto_solver = None

    def _get_auto_solver(self):
        """Lazy load the automatic CAPTCHA solver."""
        if self._auto_solver is None and self.enable_auto_solve:
            try:
                from src.services.captcha_solver import get_captcha_solver

                self._auto_solver = get_captcha_solver()
            except ImportError as e:
                logger.warning(f"Auto CAPTCHA solver not available: {e}")
                self.enable_auto_solve = False
        return self._auto_solver

    async def request_human_intervention(
        self,
        page: Page,
        url: str,
        captcha_type: str = "unknown",
        captcha_input_selector: Optional[str] = None,
    ) -> CaptchaResolutionResult:
        """
        Handle CAPTCHA with automatic solving attempt, then human fallback.

        First attempts OCR-based automatic solving for simple CAPTCHAs.
        Falls back to WebSocket notification for human intervention if needed.

        Args:
            page: Playwright page with CAPTCHA
            url: URL where CAPTCHA was encountered
            captcha_type: Type of CAPTCHA (recaptcha, hcaptcha, cloudflare, etc.)
            captcha_input_selector: CSS selector for CAPTCHA input field (if known)

        Returns:
            CaptchaResolutionResult with success status and details
        """
        captcha_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        logger.info(f"Handling CAPTCHA at {url} (type: {captcha_type})")

        try:
            # Take screenshot of CAPTCHA
            screenshot = await page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

            # === STEP 1: Attempt automatic solving ===
            if self.enable_auto_solve and captcha_type not in (
                "recaptcha",
                "hcaptcha",
                "cloudflare",
            ):
                auto_result = await self._attempt_auto_solve(
                    screenshot, captcha_type
                )

                if auto_result and auto_result.get("success"):
                    solution = auto_result.get("solution")
                    confidence = auto_result.get("confidence", "medium")

                    logger.info(
                        f"CAPTCHA auto-solved with {confidence} confidence: {solution}"
                    )

                    # If we have an input selector, try to fill it
                    if captcha_input_selector and solution:
                        try:
                            await page.fill(captcha_input_selector, solution)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(1)  # Wait for response

                            # Check if CAPTCHA was accepted
                            # (simple check - more sophisticated needed for production)
                            duration = (
                                datetime.utcnow() - start_time
                            ).total_seconds()

                            return CaptchaResolutionResult(
                                success=True,
                                status=CaptchaResolutionStatus.AUTO_SOLVED,
                                captcha_id=captcha_id,
                                url=url,
                                duration_seconds=duration,
                                auto_solution=solution,
                                auto_confidence=confidence,
                            )
                        except Exception as e:
                            logger.warning(f"Auto-fill failed, falling back: {e}")

                    # Return solution for caller to handle
                    if solution:
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

            # === STEP 2: Fall back to human intervention ===
            logger.info(f"Requesting human intervention for CAPTCHA at {url}")

            # Create pending resolution event
            resolution_event = asyncio.Event()
            self._pending_resolutions[captcha_id] = resolution_event
            self._resolution_results[captcha_id] = CaptchaResolutionStatus.PENDING

            # Send WebSocket notification
            await self._notify_captcha_detected(
                captcha_id=captcha_id,
                url=url,
                captcha_type=captcha_type,
                screenshot_b64=screenshot_b64,
            )

            # Wait for resolution or timeout
            try:
                await asyncio.wait_for(
                    resolution_event.wait(),
                    timeout=self.timeout_seconds,
                )

                # Check result
                status = self._resolution_results.get(
                    captcha_id, CaptchaResolutionStatus.ERROR
                )
                success = status == CaptchaResolutionStatus.SOLVED

                if success:
                    logger.info(f"CAPTCHA {captcha_id} solved by user")
                else:
                    logger.info(f"CAPTCHA {captcha_id} skipped by user")

            except asyncio.TimeoutError:
                status = CaptchaResolutionStatus.TIMEOUT
                success = False
                logger.warning(
                    f"CAPTCHA resolution timeout after {self.timeout_seconds}s"
                )

                # Notify frontend of timeout
                await self._notify_captcha_timeout(captcha_id, url)

        except Exception as e:
            status = CaptchaResolutionStatus.ERROR
            success = False
            logger.error(f"Error requesting CAPTCHA intervention: {e}")

            return CaptchaResolutionResult(
                success=False,
                status=status,
                captcha_id=captcha_id,
                url=url,
                duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
                error_message=str(e),
            )

        finally:
            # Cleanup
            self._pending_resolutions.pop(captcha_id, None)
            self._resolution_results.pop(captcha_id, None)

        duration = (datetime.utcnow() - start_time).total_seconds()

        return CaptchaResolutionResult(
            success=success,
            status=status,
            captcha_id=captcha_id,
            url=url,
            duration_seconds=duration,
        )

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
            logger.warning(f"Unknown CAPTCHA ID: {captcha_id}")
            return False

        self._resolution_results[captcha_id] = status
        self._pending_resolutions[captcha_id].set()

        logger.info(f"CAPTCHA {captcha_id} marked as {status.value}")
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
            from src.services.captcha_solver import CaptchaType

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
            logger.warning(f"Auto-solve attempt failed: {e}")
            return None


# Global singleton instance
_captcha_human_loop: Optional[CaptchaHumanLoop] = None


def get_captcha_human_loop(
    timeout_seconds: float = 120.0,
    auto_skip_on_timeout: bool = True,
) -> CaptchaHumanLoop:
    """
    Get or create the global CaptchaHumanLoop instance.

    Args:
        timeout_seconds: Timeout for human resolution
        auto_skip_on_timeout: Whether to skip on timeout

    Returns:
        CaptchaHumanLoop: Global instance
    """
    global _captcha_human_loop

    if _captcha_human_loop is None:
        _captcha_human_loop = CaptchaHumanLoop(
            timeout_seconds=timeout_seconds,
            auto_skip_on_timeout=auto_skip_on_timeout,
        )

    return _captcha_human_loop
