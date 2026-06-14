# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot Browser Worker - Playwright automation service.

Deploys to: 10.0.0.6 (Browser VM)

Phase 2+ refactoring: Extracted browser automation code to src/automation/ module.
Provides core Playwright-based browser automation capabilities for workflow integration.
"""

import logging

from src.automation import BrowserAutomationSession

logger = logging.getLogger(__name__)

__all__ = ["main"]


def main():
    """Browser worker entry point."""
    logger.info("Browser Worker starting...")
    logger.info("Browser automation module loaded: %s", BrowserAutomationSession.__name__)
    # Browser automation code extracted to src/automation/ module
    # See src/automation/browser_session.py for BrowserAutomationSession implementation


if __name__ == "__main__":
    main()
