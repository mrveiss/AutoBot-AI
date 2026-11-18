# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Randomised browser fingerprints for the web researcher's Playwright contexts.

Moved out of agents/web_researcher.py (#19226) so that module can take the live settings
apply without growing past its size ceiling.
"""

import random
from typing import Any, Dict

from constants.security_constants import SecurityConstants


class BrowserFingerprint:
    """Manages browser fingerprinting and randomization."""

    USER_AGENTS = SecurityConstants.USER_AGENT_POOL

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1920, "height": 1080},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1280, "height": 720},
    ]

    def __init__(self):
        """Initialize with randomized browser fingerprint."""
        self.current_fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """Generate randomized browser fingerprint."""
        return {
            # Browser fingerprint sampling, not cryptographic.
            "user_agent": random.choice(self.USER_AGENTS),  # nosec B311
            "viewport": random.choice(self.VIEWPORTS),  # nosec B311  # non-crypto viewport selection
            "timezone": random.choice(  # nosec B311  # non-crypto timezone selection
                [
                    "America/New_York",
                    "America/Los_Angeles",
                    "Europe/London",
                    "Europe/Berlin",
                ]
            ),
            # Non-crypto language selection.
            "language": random.choice(["en-US,en", "en-GB,en", "en-CA,en"]),  # nosec B311
            # Non-crypto platform selection.
            "platform": random.choice(["Win32", "MacIntel", "Linux x86_64"]),  # nosec B311
            # Non-crypto vendor selection.
            "webgl_vendor": random.choice(["Intel Inc.", "NVIDIA Corporation", "AMD"]),  # nosec B311
            "hardware_concurrency": random.choice([4, 8, 12, 16]),  # nosec B311  # non-crypto concurrency selection
        }

    def get_fingerprint(self) -> Dict[str, Any]:
        """Get current fingerprint."""
        return self.current_fingerprint

    def randomize(self):
        """Generate new random fingerprint."""
        self.current_fingerprint = self._generate_fingerprint()
