# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Browser Automation Session

Extracted from autobot-backend/research_browser_manager.py for Phase 2+ refactoring.
Provides core browser session management for Playwright-based automation.

Issue #665: JavaScript snippets for content extraction
Issue #620: CAPTCHA and interaction detection
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# JavaScript snippets for content extraction
JS_EXTRACT_TEXT = """
() => {
    const scripts = document.querySelectorAll('script, style');
    scripts.forEach(el => el.remove());

    const contentSelectors = [
        'main', 'article', '[role="main"]', '.content',
        '#content', '.main-content', 'body'
    ];

    for (const selector of contentSelectors) {
        const element = document.querySelector(selector);
        if (element) {
            return element.innerText.trim();
        }
    }
    return document.body.innerText.trim();
}
"""

JS_EXTRACT_STRUCTURED = """
() => {
    const data = {};
    data.headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
        .map(h => ({ level: h.tagName.toLowerCase(), text: h.innerText.trim() }))
        .filter(h => h.text.length > 0);
    data.links = Array.from(document.querySelectorAll('a[href]'))
        .map(a => ({ text: a.innerText.trim(), href: a.href }))
        .filter(l => l.text.length > 0).slice(0, 20);
    const metaDesc = document.querySelector('meta[name="description"]');
    data.description = metaDesc ? metaDesc.getAttribute('content') : '';
    return data;
}
"""

JS_INTERACTION_DETECTION = """
// Detect common CAPTCHA patterns
const captchaSelectors = [
    'iframe[src*="recaptcha"]',
    '.g-recaptcha',
    '[data-testid="captcha"]',
    '.captcha',
    '.hcaptcha',
    '.cf-challenge-form',
    '[class*="captcha"]'
];

function checkForInteraction() {
    const hasCaptcha = captchaSelectors.some(selector =>
        document.querySelector(selector) !== null
    );

    if (hasCaptcha) {
        window.autobot_interaction_required = {
            type: 'captcha',
            message: 'CAPTCHA detected - user interaction required',
            timestamp: Date.now()
        };
    }

    // Check for other common interaction patterns
    const commonInteractionTexts = [
        'verify you are human',
        'click to continue',
        'press and hold',
        'solve the puzzle',
        'complete the challenge'
    ];

    const bodyText = document.body.innerText.toLowerCase();
    for (const text of commonInteractionTexts) {
        if (bodyText.includes(text)) {
            window.autobot_interaction_required = {
                type: 'verification',
                message: `Interaction required: ${text}`,
                timestamp: Date.now()
            };
            break;
        }
    }
}

// Check immediately and on DOM changes
checkForInteraction();
new MutationObserver(checkForInteraction).observe(document.body, {
    childList: true,
    subtree: true
});
"""


class BrowserAutomationSession:
    """
    Core browser automation session manager.

    Extracted from research_browser_manager.ResearchBrowserSession.
    Manages browser initialization, navigation, and content extraction.
    """

    def __init__(self, session_id: str):
        """Initialize automation session."""
        self.session_id = session_id
        self.browser = None
        self.context = None
        self.page = None
        self.created_at = datetime.now(tz=timezone.utc)
        self.last_activity = datetime.now(tz=timezone.utc)
        self.status = "initialized"
        self.current_url: Optional[str] = None
        self.interaction_required = False
        self.interaction_message = ""
        self.playwright = None

    async def close(self) -> None:
        """Close the browser session."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.status = "closed"
            logger.info("Browser session %s closed", self.session_id)
        except Exception as e:
            logger.error("Error closing browser session %s: %s", self.session_id, e)

    def get_status(self) -> Dict[str, Any]:
        """Get current session status."""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "current_url": self.current_url,
            "interaction_required": self.interaction_required,
        }
