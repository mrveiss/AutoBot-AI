# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CAPTCHA Human-in-the-Loop Service

This module provides a human-in-the-loop mechanism for CAPTCHA handling during
web research operations. When automated CAPTCHA solving fails, users are notified
via WebSocket and can manually solve CAPTCHAs through the VNC desktop interface.

Features:
- WebSocket notifications when CAPTCHA encountered
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


class CaptchaHumanLoop:
    """
    Service for handling CAPTCHAs through human intervention.

    Provides WebSocket-based notification to frontend when CAPTCHA is detected,
    allowing users to manually solve CAPTCHAs through VNC desktop streaming.
    """

    # Store pending CAPTCHA resolutions
    _pending_resolutions: Dict[str, asyncio.Event] = {}
    _resolution_results: Dict[str, CaptchaResolutionStatus] = {}

    def __init__(
        self,
        timeout_seconds: float = 120.0,
        auto_skip_on_timeout: bool = True,
        vnc_url: Optional[str] = None,
    ):
        """
        Initialize the CAPTCHA human-in-the-loop service.

        Args:
            timeout_seconds: Maximum time to wait for human resolution (default: 120s)
            auto_skip_on_timeout: Whether to skip source on timeout (default: True)
            vnc_url: URL for VNC desktop interface (auto-detected if not provided)
        """
        self.timeout_seconds = timeout_seconds
        self.auto_skip_on_timeout = auto_skip_on_timeout
        self.vnc_url = vnc_url or "http://127.0.0.1:6080/vnc.html"

    async def request_human_intervention(
        self,
        page: Page,
        url: str,
        captcha_type: str = "unknown",
    ) -> CaptchaResolutionResult:
        """
        Request human intervention to solve a CAPTCHA.

        Sends a WebSocket notification to the frontend with CAPTCHA details
        and screenshot, then waits for user resolution or timeout.

        Args:
            page: Playwright page with CAPTCHA
            url: URL where CAPTCHA was encountered
            captcha_type: Type of CAPTCHA (recaptcha, hcaptcha, cloudflare, etc.)

        Returns:
            CaptchaResolutionResult with success status and details
        """
        captcha_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        logger.info(f"Requesting human intervention for CAPTCHA at {url}")

        try:
            # Take screenshot of CAPTCHA
            screenshot = await page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

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
