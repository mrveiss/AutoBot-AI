# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Research Browser Manager
Handles Playwright browser automation for research tasks with user interaction support
"""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import aiofiles
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.config import UnifiedConfigManager
from src.constants.network_constants import ServiceURLs
from src.constants.security_constants import SecurityConstants
from src.constants.threshold_constants import TimingConstants
from src.source_attribution import SourceType, track_source
from src.utils.display_utils import get_playwright_config

logger = logging.getLogger(__name__)

# Create singleton config instance
config = UnifiedConfigManager()

# Issue #665: JavaScript snippets for content extraction
_JS_EXTRACT_TEXT = """
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

_JS_EXTRACT_STRUCTURED = """
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

# Issue #620: JavaScript snippet for CAPTCHA and interaction detection
_JS_INTERACTION_DETECTION = """
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


class ResearchBrowserSession:
    """Manages a single research browser session with user interaction capability"""

    def __init__(self, session_id: str, conversation_id: str):
        """Initialize research browser session with IDs."""
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.status = (
            "initializing"  # initializing, active, waiting_for_user, error, closed
        )
        self.current_url = None
        self.interaction_required = False
        self.interaction_message = ""
        self.research_data = {}
        self.mhtml_files = []

    async def _connect_or_launch_browser(
        self, headless: bool, browser_args: list
    ) -> None:
        """
        Connect to existing browser via CDP or launch a new one.

        Tries CDP connection first, falls back to launching new browser. Issue #620.
        """
        try:
            self.browser = await self.playwright.chromium.connect_over_cdp(
                config.get_service_url("chrome", "/devtools")
                or ServiceURLs.CHROME_DEBUGGER_LOCAL
            )
            logger.info(
                "Connected to existing browser via CDP for session %s",
                self.session_id,
            )
        except Exception:
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=browser_args,
            )
            logger.info("Launched new browser for session %s", self.session_id)

    async def _create_browser_context(self, viewport: dict) -> None:
        """
        Create browser context and page with specified viewport.

        Sets up context with viewport and user agent, creates initial page. Issue #620.
        """
        self.context = await self.browser.new_context(
            viewport=viewport,
            user_agent=SecurityConstants.DEFAULT_USER_AGENT,
        )
        self.page = await self.context.new_page()
        self.status = "active"

    async def initialize(self, headless: bool = False):
        """Initialize the browser session."""
        try:
            self.playwright = await async_playwright().start()

            pw_config = get_playwright_config()
            viewport = pw_config["viewport"]
            browser_args = pw_config["browser_args"]

            logger.info(
                "Using dynamic resolution: %dx%d (detected: %dx%d)",
                viewport["width"],
                viewport["height"],
                pw_config["detected_resolution"]["width"],
                pw_config["detected_resolution"]["height"],
            )

            await self._connect_or_launch_browser(headless, browser_args)
            await self._create_browser_context(viewport)
            await self._setup_interaction_detection()

            logger.info("Browser session %s initialized successfully", self.session_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to initialize browser session %s: %s", self.session_id, e
            )
            self.status = "error"
            return False

    async def _setup_interaction_detection(self):
        """
        Set up detection for CAPTCHAs and other user interactions.

        Injects JavaScript to detect common CAPTCHA patterns and verification
        prompts, setting window.autobot_interaction_required when found. Issue #620.
        """
        if not self.page:
            return

        await self.page.add_init_script(_JS_INTERACTION_DETECTION)

    async def _check_interaction_required(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Check if user interaction is required after navigation.

        Returns response dict if interaction needed, None otherwise. Issue #620.
        """
        interaction_data = await self.page.evaluate(
            "window.autobot_interaction_required"
        )
        if interaction_data:
            self.interaction_required = True
            self.interaction_message = interaction_data.get(
                "message", "User interaction required"
            )
            self.status = "waiting_for_user"
            return {
                "success": True,
                "url": url,
                "title": await self.page.title(),
                "interaction_required": True,
                "interaction_message": self.interaction_message,
                "session_id": self.session_id,
            }
        return None

    def _track_navigation_source(self, url: str, title: str) -> None:
        """
        Track navigation as a source for attribution. Issue #620.
        """
        track_source(
            SourceType.WEB_SEARCH,
            f"Navigated to {title}",
            reliability="medium",
            metadata={
                "url": url,
                "title": title,
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def navigate_to(self, url: str, wait_for_load: bool = True) -> Dict[str, Any]:
        """Navigate to a URL and return page information."""
        if not self.page:
            return {"success": False, "error": "Browser not initialized"}

        try:
            self.current_url = url
            self.last_activity = datetime.now()
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if wait_for_load:
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

            interaction_response = await self._check_interaction_required(url)
            if interaction_response:
                return interaction_response

            title = await self.page.title()
            content_length = len(await self.page.content())
            self._track_navigation_source(url, title)

            return {
                "success": True,
                "url": url,
                "title": title,
                "content_length": content_length,
                "interaction_required": False,
                "session_id": self.session_id,
            }

        except Exception as e:
            logger.error("Navigation failed for session %s: %s", self.session_id, e)
            return {"success": False, "error": str(e)}

    async def extract_content(self) -> Dict[str, Any]:
        """
        Extract content from current page.

        Issue #665: Refactored to use module-level JS constants.
        """
        if not self.page:
            return {"success": False, "error": "Browser not initialized"}

        try:
            # Issue #665: Use module-level JS constants
            text_content = await self.page.evaluate(_JS_EXTRACT_TEXT)
            structured_data = await self.page.evaluate(_JS_EXTRACT_STRUCTURED)

            return {
                "success": True,
                "url": self.current_url,
                "title": await self.page.title(),
                "text_content": text_content[:5000],
                "structured_data": structured_data,
                "content_length": len(text_content),
            }

        except Exception as e:
            logger.error(
                f"Content extraction failed for session {self.session_id}: {e}"
            )
            return {"success": False, "error": str(e)}

    async def save_mhtml(self) -> Optional[str]:
        """Save current page as MHTML file"""
        if not self.page:
            return None

        try:
            # Create temp directory for MHTML files
            temp_dir = os.path.join(tempfile.gettempdir(), "autobot_mhtml")
            os.makedirs(temp_dir, exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_{self.session_id}_{timestamp}.mhtml"
            filepath = os.path.join(temp_dir, filename)

            # Save as MHTML using CDP
            cdp_session = await self.page.context.new_cdp_session(self.page)
            result = await cdp_session.send("Page.captureSnapshot", {"format": "mhtml"})

            try:
                async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                    await f.write(result["data"])
            except OSError as e:
                logger.error("Failed to write MHTML file %s: %s", filepath, e)
                return None

            self.mhtml_files.append(filepath)
            logger.info("Saved MHTML file: %s", filepath)

            return filepath

        except Exception as e:
            logger.error("Failed to save MHTML for session %s: %s", self.session_id, e)
            return None

    async def wait_for_user_interaction(self, timeout_seconds: int = 300) -> bool:
        """Wait for user to complete interaction"""
        if not self.page or not self.interaction_required:
            return True

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            try:
                # Check if interaction is still required
                interaction_data = await self.page.evaluate(
                    "window.autobot_interaction_required"
                )
                if not interaction_data:
                    self.interaction_required = False
                    self.status = "active"
                    return True

                await asyncio.sleep(
                    TimingConstants.STANDARD_DELAY
                )  # Check every 2 seconds

            except Exception as e:
                logger.error("Error checking interaction status: %s", e)
                break

        return False

    async def close(self):
        """Close the browser session"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, "playwright"):
                await self.playwright.stop()

            # Clean up MHTML files in parallel - eliminates N+1 sequential I/O
            async def cleanup_mhtml_file(mhtml_file: str) -> None:
                """Remove a single MHTML file asynchronously."""
                try:
                    if await asyncio.to_thread(os.path.exists, mhtml_file):
                        await asyncio.to_thread(os.remove, mhtml_file)
                except Exception as e:
                    logger.warning(
                        "Failed to clean up MHTML file %s: %s", mhtml_file, e
                    )

            if self.mhtml_files:
                await asyncio.gather(
                    *[cleanup_mhtml_file(f) for f in self.mhtml_files],
                    return_exceptions=True,
                )

            self.status = "closed"
            logger.info("Browser session %s closed", self.session_id)

        except Exception as e:
            logger.error("Error closing browser session %s: %s", self.session_id, e)


class ResearchBrowserManager:
    """Manages multiple research browser sessions"""

    def __init__(self):
        """Initialize research browser manager with session tracking."""
        self.sessions: Dict[str, ResearchBrowserSession] = {}
        self.conversation_sessions: Dict[str, str] = {}  # conversation_id -> session_id
        self.max_sessions = 10

    async def create_session(self, conversation_id: str, headless: bool = False) -> str:
        """Create a new research browser session"""
        session_id = str(uuid.uuid4())

        # Clean up old sessions if at limit
        if len(self.sessions) >= self.max_sessions:
            await self._cleanup_oldest_session()

        session = ResearchBrowserSession(session_id, conversation_id)

        if await session.initialize(headless=headless):
            self.sessions[session_id] = session
            self.conversation_sessions[conversation_id] = session_id

            logger.info(
                f"Created research session {session_id} for conversation {conversation_id}"
            )
            return session_id
        else:
            logger.error(
                f"Failed to create research session for conversation {conversation_id}"
            )
            return None

    def get_session(self, session_id: str) -> Optional[ResearchBrowserSession]:
        """Get a research session by ID"""
        return self.sessions.get(session_id)

    def get_session_by_conversation(
        self, conversation_id: str
    ) -> Optional[ResearchBrowserSession]:
        """Get the research session for a conversation"""
        session_id = self.conversation_sessions.get(conversation_id)
        if session_id:
            return self.sessions.get(session_id)
        return None

    async def _get_or_create_session(
        self, conversation_id: str
    ) -> Optional[ResearchBrowserSession]:
        """
        Get existing session or create a new one for the conversation.

        Extracted from research_url() to reduce function length. Issue #620.

        Args:
            conversation_id: The conversation identifier

        Returns:
            ResearchBrowserSession if successful, None otherwise
        """
        session = self.get_session_by_conversation(conversation_id)
        if not session:
            session_id = await self.create_session(conversation_id)
            if not session_id:
                return None
            session = self.sessions[session_id]
        return session

    def _build_interaction_required_response(
        self, nav_result: Dict[str, Any], session: ResearchBrowserSession
    ) -> Dict[str, Any]:
        """
        Build response dict when user interaction is required.

        Extracted from research_url() to reduce function length. Issue #620.

        Args:
            nav_result: Navigation result containing interaction details
            session: The browser session

        Returns:
            Response dict indicating interaction is required
        """
        return {
            "success": True,
            "status": "interaction_required",
            "message": nav_result["interaction_message"],
            "session_id": session.session_id,
            "browser_url": f"/browser/{session.session_id}",
            "actions": ["wait", "manual_intervention", "save_mhtml"],
        }

    async def _extract_and_build_success_response(
        self,
        session: ResearchBrowserSession,
        nav_result: Dict[str, Any],
        extract_content: bool,
    ) -> Dict[str, Any]:
        """
        Extract content and build success response.

        Extracted from research_url() to reduce function length. Issue #620.

        Args:
            session: The browser session
            nav_result: Navigation result
            extract_content: Whether to extract page content

        Returns:
            Success response dict with content and navigation results
        """
        content_result = {}
        if extract_content:
            content_result = await session.extract_content()
            mhtml_path = await session.save_mhtml()
            if mhtml_path:
                content_result["mhtml_backup"] = mhtml_path

        return {
            "success": True,
            "status": "completed",
            "navigation": nav_result,
            "content": content_result,
            "session_id": session.session_id,
            "browser_url": f"/browser/{session.session_id}",
        }

    async def research_url(
        self, conversation_id: str, url: str, extract_content: bool = True
    ) -> Dict[str, Any]:
        """
        Research a URL with automatic fallbacks.

        Issue #620: Refactored to use extracted helper methods.
        """
        try:
            session = await self._get_or_create_session(conversation_id)
            if not session:
                return {"success": False, "error": "Failed to create browser session"}

            nav_result = await session.navigate_to(url)
            if not nav_result["success"]:
                return await self._try_mhtml_fallback(session, url)

            if nav_result.get("interaction_required"):
                return self._build_interaction_required_response(nav_result, session)

            return await self._extract_and_build_success_response(
                session, nav_result, extract_content
            )

        except Exception as e:
            logger.error("Research failed for URL %s: %s", url, e)
            return {"success": False, "error": str(e)}

    async def _try_mhtml_fallback(
        self, session: ResearchBrowserSession, url: str
    ) -> Dict[str, Any]:
        """Try to crawl using MHTML fallback"""
        try:
            logger.info("Attempting MHTML fallback for %s", url)

            # Create a simple page to load the URL and save MHTML
            await session.page.goto("about:blank")

            # Try to navigate and immediately save MHTML
            try:
                await session.page.goto(url, timeout=10000)
                mhtml_path = await session.save_mhtml()

                if mhtml_path:
                    # Extract content from MHTML file
                    content = await self._extract_from_mhtml(mhtml_path)

                    return {
                        "success": True,
                        "status": "mhtml_fallback",
                        "content": content,
                        "mhtml_path": mhtml_path,
                        "message": "Content extracted from MHTML backup",
                    }
            except Exception as e:
                logger.error("MHTML fallback also failed: %s", e)

            return {
                "success": False,
                "error": "Both direct access and MHTML fallback failed",
            }

        except Exception as e:
            logger.error("MHTML fallback error: %s", e)
            return {"success": False, "error": f"MHTML fallback error: {str(e)}"}

    async def _extract_from_mhtml(self, mhtml_path: str) -> Dict[str, Any]:
        """Extract content from MHTML file"""
        try:
            # For now, return basic file info
            # In production, you'd want to parse the MHTML format
            # Issue #358 - avoid blocking
            file_size = await asyncio.to_thread(os.path.getsize, mhtml_path)

            return {
                "success": True,
                "source": "mhtml_file",
                "file_path": mhtml_path,
                "file_size": file_size,
                "text_content": (
                    "Content extracted from MHTML backup (parsing not yet implemented)"
                ),
                "content_length": file_size,
            }

        except Exception as e:
            logger.error("Failed to extract from MHTML %s: %s", mhtml_path, e)
            return {"success": False, "error": str(e)}

    async def _cleanup_oldest_session(self):
        """Clean up the oldest inactive session"""
        if not self.sessions:
            return

        oldest_session_id = min(
            self.sessions.keys(), key=lambda sid: self.sessions[sid].last_activity
        )

        await self.cleanup_session(oldest_session_id)

    async def cleanup_session(self, session_id: str):
        """Clean up a specific session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            await session.close()

            # Remove from mappings
            del self.sessions[session_id]
            if session.conversation_id in self.conversation_sessions:
                del self.conversation_sessions[session.conversation_id]

            logger.info("Cleaned up research session %s", session_id)

    async def cleanup_all(self):
        """Clean up all sessions"""
        for session_id in list(self.sessions.keys()):
            await self.cleanup_session(session_id)


# Global research browser manager
research_browser_manager = ResearchBrowserManager()
