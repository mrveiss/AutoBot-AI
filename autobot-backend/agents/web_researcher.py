# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Consolidated Web Research Module for AutoBot

Combines browser automation (Playwright), anti-detection, CAPTCHA handling,
circuit breakers, rate limiting, caching, and KB integration into a single
module. Replaces: advanced_web_research.py, research_agent.py,
web_research_assistant.py, web_research_integration.py (Issue #1443).
"""

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.parse import urlparse

from constants.security_constants import SecurityConstants
from constants.threshold_constants import TimingConstants
from pydantic import BaseModel
from services.captcha_human_loop import get_captcha_human_loop

# Issue #380: Module-level frozenset for CAPTCHA detection keywords
_CAPTCHA_KEYWORDS: FrozenSet[str] = frozenset({"captcha", "challenge", "verification"})

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = Any
    Page = Any
    BrowserContext = Any
    async_playwright = None
    logging.warning("Playwright not available. Install with: pip install playwright")

try:
    from autobot_shared.http_client import get_http_client

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp not available. Install with: pip install aiohttp")
    get_http_client = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models (from research_agent.py)
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    query: str
    focus: str = "general"
    max_results: int = 5
    include_installation: bool = False


class ResearchResult(BaseModel):
    title: str
    url: str
    content: str
    relevance_score: float
    source_type: str  # "documentation", "tutorial", "forum", "official"


class ResearchResponse(BaseModel):
    success: bool
    query: str
    results: List[ResearchResult]
    summary: str
    execution_time: float
    sources_count: int


@dataclass
class WebPage:
    url: str
    title: str
    content: str
    links: List[str]
    source_type: str


# ---------------------------------------------------------------------------
# Enums (from web_research_integration.py)
# ---------------------------------------------------------------------------


class ResearchType(Enum):
    """Types of research methods available."""

    BASIC = "basic"
    ADVANCED = "advanced"
    API_BASED = "api_based"


class CircuitBreakerState(Enum):
    """Circuit breaker states for research services."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Tool reference data (from research_agent.py)
# ---------------------------------------------------------------------------

_TOOL_REFERENCE_DATA: Dict[str, Dict[str, Any]] = {
    "nmap": {
        "installation": "sudo apt-get install nmap",
        "usage": "nmap -sS -O target_ip",
        "verification": "nmap --version",
        "prerequisites": ["sudo privileges", "network access"],
    },
    "masscan": {
        "installation": "sudo apt-get install masscan",
        "usage": "masscan -p1-65535 <target_network> --rate=1000",
        "verification": "masscan --version",
        "prerequisites": [
            "sudo privileges",
            "build-essential (if compiling from source)",
        ],
    },
    "zmap": {
        "installation": "sudo apt-get install zmap",
        "usage": "zmap -p 443 -o results.txt",
        "verification": "zmap --version",
        "prerequisites": [
            "sudo privileges",
            "libgmp3-dev libpcap-dev",
        ],
    },
}


# ---------------------------------------------------------------------------
# Support classes
# ---------------------------------------------------------------------------


class CaptchaSolver:
    """Integration with CAPTCHA solving services."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize CAPTCHA solver with API key and service config."""
        self.api_key = config.get("api_key")
        self.service = config.get("service", "2captcha")
        self.timeout = config.get("timeout", 120)

    async def solve_recaptcha(
        self, site_key: str, page_url: str, invisible: bool = False
    ) -> Optional[str]:
        """Solve reCAPTCHA using solving service."""
        if not self.api_key:
            logger.warning("No CAPTCHA API key configured")
            return None
        try:
            if self.service == "2captcha":
                return await self._solve_2captcha(site_key, page_url, invisible)
            elif self.service == "anticaptcha":
                return await self._solve_anticaptcha(site_key, page_url, invisible)
            else:
                logger.error("Unsupported CAPTCHA service: %s", self.service)
                return None
        except Exception as e:
            logger.error("CAPTCHA solving failed: %s", str(e))
            return None

    async def _solve_2captcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Solve reCAPTCHA using 2captcha service."""
        if not AIOHTTP_AVAILABLE:
            return None

        submit_url = "http://2captcha.com/in.php"
        result_url = "http://2captcha.com/res.php"
        submit_data = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "invisible": 1 if invisible else 0,
            "json": 1,
        }

        http_client = get_http_client()
        submit_result = await http_client.post_json(submit_url, json_data=submit_data)
        if submit_result.get("status") != 1:
            logger.error("CAPTCHA submit failed: %s", submit_result)
            return None

        captcha_id = submit_result["request"]
        logger.info("CAPTCHA submitted, ID: %s", captcha_id)

        for _attempt in range(self.timeout // 5):
            await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)
            result = await http_client.get_json(
                f"{result_url}?key={self.api_key}" f"&action=get&id={captcha_id}&json=1"
            )
            if result.get("status") == 1:
                logger.info("CAPTCHA solved successfully")
                return result["request"]
            elif result.get("error_text") == "CAPCHA_NOT_READY":
                continue
            else:
                logger.error("CAPTCHA solving failed: %s", result)
                return None

        logger.error("CAPTCHA solving timeout")
        return None

    async def _solve_anticaptcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Solve reCAPTCHA using AntiCaptcha service (placeholder)."""
        logger.info("AntiCaptcha integration not implemented yet")
        return None


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
            "user_agent": random.choice(self.USER_AGENTS),
            "viewport": random.choice(self.VIEWPORTS),
            "timezone": random.choice(
                [
                    "America/New_York",
                    "America/Los_Angeles",
                    "Europe/London",
                    "Europe/Berlin",
                ]
            ),
            "language": random.choice(["en-US,en", "en-GB,en", "en-CA,en"]),
            "platform": random.choice(["Win32", "MacIntel", "Linux x86_64"]),
            "webgl_vendor": random.choice(["Intel Inc.", "NVIDIA Corporation", "AMD"]),
            "hardware_concurrency": random.choice([4, 8, 12, 16]),
        }

    def get_fingerprint(self) -> Dict[str, Any]:
        """Get current fingerprint."""
        return self.current_fingerprint

    def randomize(self):
        """Generate new random fingerprint."""
        self.current_fingerprint = self._generate_fingerprint()


class CircuitBreaker:
    """Circuit breaker for web research services (thread-safe)."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = TimingConstants.STANDARD_TIMEOUT,
    ):
        """Initialize with failure threshold and recovery timeout."""
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()

    def call_succeeded(self):
        """Record successful call (thread-safe)."""
        with self._lock:
            self.failure_count = 0
            self.state = CircuitBreakerState.CLOSED

    def call_failed(self):
        """Record failed call (thread-safe)."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(
                    "Circuit breaker opened after %s failures",
                    self.failure_count,
                )

    def can_execute(self) -> bool:
        """Check if a call can execute (thread-safe)."""
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True
            if self.state == CircuitBreakerState.OPEN:
                elapsed = time.time() - self.last_failure_time
                if elapsed > self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to half-open")
                    return True
                return False
            return True  # HALF_OPEN

    def reset(self):
        """Reset circuit breaker (thread-safe)."""
        with self._lock:
            self.failure_count = 0
            self.last_failure_time = None
            self.state = CircuitBreakerState.CLOSED


class RateLimiter:
    """Rate limiter for web research requests (async-safe)."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """Initialize with request limit and time window."""
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire permission for a request (async-safe)."""
        async with self._lock:
            return await self._acquire_internal()

    async def _acquire_internal(self) -> bool:
        """Internal acquire (called when lock is already held)."""
        now = time.time()
        self.requests = [t for t in self.requests if now - t < self.window_seconds]
        if len(self.requests) >= self.max_requests:
            oldest = min(self.requests)
            wait_time = self.window_seconds - (now - oldest)
            if wait_time > 0:
                logger.info("Rate limit reached, waiting %.2fs", wait_time)
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()
                return await self._acquire_internal()
        self.requests.append(now)
        return True


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class WebResearcher:
    """
    Unified web researcher with Playwright browser engine,
    circuit breakers, rate limiting, caching, and KB integration.

    Consolidates: AdvancedWebResearcher, ResearchAgent,
    WebResearchAssistant, WebResearchIntegration (Issue #1443).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize web researcher with all subsystems."""
        self.config = config or {}

        # Browser engine
        self.fingerprint = BrowserFingerprint()
        self.captcha_solver = CaptchaSolver(self.config.get("captcha", {}))
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._domain_rate_limiter: Dict[str, float] = {}
        self._domain_rate_lock = asyncio.Lock()

        # Circuit breaker for search operations
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=TimingConstants.STANDARD_TIMEOUT,
        )

        # Global rate limiter
        self.rate_limiter = RateLimiter(
            max_requests=self.config.get("rate_limit_requests", 5),
            window_seconds=self.config.get("rate_limit_window", 60),
        )

        # Cache (TTL-based)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = self.config.get("cache_ttl", 3600)
        self._cache_lock = asyncio.Lock()

        # Settings
        self.enabled = self.config.get("enabled", False)
        self.timeout_seconds = self.config.get("timeout_seconds", 30)
        self.max_results_default = self.config.get("max_results", 5)
        self.quality_threshold = 0.7

    # -------------------------------------------------------------------
    # Browser lifecycle
    # -------------------------------------------------------------------

    async def initialize(self):
        """Initialize browser automation."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. "
                "Run: pip install playwright && playwright install"
            )
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.config.get("headless", True),
            args=self._get_browser_args(),
        )
        await self._create_context()

    def _get_browser_args(self) -> List[str]:
        """Get anti-detection browser launch args."""
        return [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=VizDisplayCompositor",
            "--disable-ipc-flooding-protection",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-field-trial-config",
            "--disable-back-forward-cache",
            "--disable-hang-monitor",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--force-fieldtrials=*BackgroundTracing/default/",
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic",
            "--use-mock-keychain",
            "--hide-scrollbars",
            "--mute-audio",
        ]

    async def _create_context(self):
        """Create browser context with anti-detection."""
        fp = self.fingerprint.get_fingerprint()
        self.context = await self.browser.new_context(
            user_agent=fp["user_agent"],
            viewport=fp["viewport"],
            timezone_id=fp["timezone"],
            locale=fp["language"].split(",")[0],
            extra_http_headers={
                "Accept-Language": fp["language"],
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/webp,*/*;q=0.8"
                ),
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        await self.context.add_init_script(self._stealth_script())

    def _stealth_script(self) -> str:
        """Return JS stealth script for anti-detection."""
        return """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """

    async def close(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def __aenter__(self):
        """Initialize browser for context manager usage."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up browser resources when exiting context."""
        await self.close()

    # -------------------------------------------------------------------
    # Web search (core engine)
    # -------------------------------------------------------------------

    async def search_web(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Perform web search with anti-detection. Issue #620."""
        logger.info("Starting web search for: %s", query)
        if not self.browser:
            await self.initialize()
        try:
            all_results = await self._search_all_engines(query, max_results)
            unique = self._deduplicate_results(all_results)
            ranked = self._rank_results(unique, query)[:max_results]
            enhanced = await self._enhance_results_with_content(ranked)
            return self._build_search_response(
                query, enhanced, len(all_results), len(unique), 3
            )
        except Exception as e:
            logger.error("Web search failed: %s", str(e))
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "results": [],
                "timestamp": datetime.now().isoformat(),
            }

    async def _search_all_engines(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Execute search across all configured engines. Issue #620."""
        engines = [
            ("duckduckgo", self._search_duckduckgo),
            ("bing", self._search_bing),
            ("google", self._search_google),
        ]
        all_results: List[Dict[str, Any]] = []
        per_engine = max_results // len(engines) + 1

        for name, func in engines:
            try:
                logger.info("Searching %s for: %s", name, query)
                results = await func(query, per_engine)
                for r in results:
                    r["search_engine"] = name
                    r["timestamp"] = datetime.now().isoformat()
                all_results.extend(results)
                await self._random_delay(2, 5)
            except Exception as e:
                logger.error("Search engine %s failed: %s", name, e)
                continue
        return all_results

    def _build_search_response(
        self,
        query: str,
        results: List[Dict[str, Any]],
        total_found: int,
        unique_count: int,
        engine_count: int,
    ) -> Dict[str, Any]:
        """Build successful search response dict. Issue #620."""
        return {
            "status": "success",
            "query": query,
            "results": results,
            "total_found": total_found,
            "unique_results": unique_count,
            "search_engines_used": engine_count,
            "timestamp": datetime.now().isoformat(),
        }

    # -------------------------------------------------------------------
    # Search engine implementations
    # -------------------------------------------------------------------

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search DuckDuckGo with anti-detection."""
        page = await self.context.new_page()
        results: List[Dict[str, Any]] = []
        try:
            await page.goto("https://duckduckgo.com/", wait_until="networkidle")
            if await self._detect_captcha(page):
                if not await self._handle_captcha(page):
                    logger.warning("CAPTCHA not solved, skipping DDG")
                    return results
            await page.fill('[name="q"]', query)
            await page.press('[name="q"]', "Enter")
            await page.wait_for_load_state("networkidle")

            elements = await page.query_selector_all('[data-result="result"]')
            for el in elements[:max_results]:
                result = await self._extract_ddg_result(el)
                if result:
                    results.append(result)
        finally:
            await page.close()
        return results

    async def _extract_ddg_result(self, element) -> Optional[Dict]:
        """Extract a single DuckDuckGo search result."""
        try:
            title_el = await element.query_selector("h2 a")
            snippet_el = await element.query_selector('[data-result="snippet"]')
            if not (title_el and snippet_el):
                return None
            title = await title_el.inner_text()
            url = await title_el.get_attribute("href")
            snippet = await snippet_el.inner_text()
            return {
                "title": title.strip(),
                "url": url,
                "snippet": snippet.strip(),
                "domain": urlparse(url).netloc if url else "",
            }
        except Exception as e:
            logger.error("Error extracting DDG result: %s", e)
            return None

    async def _search_bing(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search Bing with anti-detection."""
        page = await self.context.new_page()
        results: List[Dict[str, Any]] = []
        try:
            await page.goto("https://www.bing.com/", wait_until="networkidle")
            if await self._detect_captcha(page):
                if not await self._handle_captcha(page):
                    logger.warning("CAPTCHA not solved, skipping Bing")
                    return results
            await page.fill('[name="q"]', query)
            await page.press('[name="q"]', "Enter")
            await page.wait_for_load_state("networkidle")

            elements = await page.query_selector_all(".b_algo")
            for el in elements[:max_results]:
                result = await self._extract_bing_result(el)
                if result:
                    results.append(result)
        finally:
            await page.close()
        return results

    async def _extract_bing_result(self, element) -> Optional[Dict]:
        """Extract a single Bing search result."""
        try:
            title_el = await element.query_selector("h2 a")
            snippet_el = await element.query_selector(".b_caption p")
            if not (title_el and snippet_el):
                return None
            title = await title_el.inner_text()
            url = await title_el.get_attribute("href")
            snippet = await snippet_el.inner_text()
            return {
                "title": title.strip(),
                "url": url,
                "snippet": snippet.strip(),
                "domain": urlparse(url).netloc if url else "",
            }
        except Exception as e:
            logger.error("Error extracting Bing result: %s", e)
            return None

    async def _accept_cookies(self, page) -> None:
        """Accept cookies dialog if present (Issue #334)."""
        try:
            btn = await page.query_selector('button[id*="accept"], button[id*="agree"]')
            if btn:
                await btn.click()
                await page.wait_for_timeout(1000)
        except Exception as e:
            logger.debug("Cookie dialog not found: %s", e)

    async def _extract_google_result(self, element) -> Optional[Dict[str, Any]]:
        """Extract single Google search result (Issue #334)."""
        parent = await element.evaluate('el => el.closest("div[data-ved]")')
        if not parent:
            return None
        title_el = await parent.query_selector("h3")
        link_el = await parent.query_selector("a[href]")
        if not title_el or not link_el:
            return None
        snippet_el = await parent.query_selector('[data-content-feature="1"]')
        title = await title_el.inner_text()
        url = await link_el.get_attribute("href")
        snippet = await snippet_el.inner_text() if snippet_el else ""
        return {
            "title": title.strip(),
            "url": url,
            "snippet": snippet.strip(),
            "domain": urlparse(url).netloc if url else "",
        }

    async def _search_google(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search Google with anti-detection."""
        page = await self.context.new_page()
        results: List[Dict[str, Any]] = []
        try:
            await page.goto("https://www.google.com/", wait_until="networkidle")
            if await self._detect_captcha(page):
                if not await self._handle_captcha(page):
                    logger.warning("CAPTCHA not solved, skipping Google")
                    return results
            await self._accept_cookies(page)

            search_box = await page.query_selector('[name="q"], [title="Search"]')
            if not search_box:
                return results
            await search_box.fill(query)
            await search_box.press("Enter")
            await page.wait_for_load_state("networkidle")

            elements = await page.query_selector_all("[data-ved] h3")
            for el in elements[:max_results]:
                try:
                    result = await self._extract_google_result(el)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error("Google result extraction: %s", e)
        finally:
            await page.close()
        return results

    # -------------------------------------------------------------------
    # CAPTCHA handling
    # -------------------------------------------------------------------

    async def _detect_captcha(self, page: Page) -> bool:
        """Detect if CAPTCHA is present on page."""
        selectors = [
            ".g-recaptcha",
            ".h-captcha",
            ".captcha",
            "[data-sitekey]",
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            "#captcha",
            ".cf-challenge-running",
        ]
        for selector in selectors:
            if await page.query_selector(selector):
                logger.info("CAPTCHA detected: %s", selector)
                return True

        title = await page.title()
        if any(kw in title.lower() for kw in _CAPTCHA_KEYWORDS):
            logger.info("CAPTCHA detected in title: %s", title)
            return True
        return False

    async def _detect_captcha_type(self, page: Page) -> str:
        """Detect the type of CAPTCHA present. Issue #620."""
        if await page.query_selector(".g-recaptcha, [data-sitekey]"):
            return "recaptcha"
        elif await page.query_selector(".h-captcha"):
            return "hcaptcha"
        elif await page.query_selector(".cf-challenge-running"):
            return "cloudflare"
        return "unknown"

    async def _handle_captcha(self, page: Page) -> bool:
        """Handle CAPTCHA with human-in-the-loop fallback."""
        logger.info("Attempting to handle CAPTCHA challenge")
        captcha_type = await self._detect_captcha_type(page)
        if await self._try_automated_recaptcha(page):
            return True
        logger.warning("Automated CAPTCHA failed, requesting human intervention")
        return await self._request_human_captcha(page, captcha_type)

    async def _try_automated_recaptcha(self, page: Page) -> bool:
        """Attempt automated reCAPTCHA solving. Issue #620."""
        el = await page.query_selector(".g-recaptcha, [data-sitekey]")
        if not el:
            return False
        site_key = await el.get_attribute("data-sitekey")
        if not site_key:
            return False
        solution = await self.captcha_solver.solve_recaptcha(site_key, page.url)
        if not solution:
            return False
        await page.evaluate(
            "document.getElementById('g-recaptcha-response')"
            f'.innerHTML="{solution}";'
        )
        await page.evaluate("if(window.captchaCallback) window.captchaCallback();")
        await page.wait_for_timeout(2000)
        return True

    async def _request_human_captcha(self, page: Page, captcha_type: str) -> bool:
        """Request human intervention for CAPTCHA. Issue #620."""
        service = get_captcha_human_loop(
            timeout_seconds=120.0, auto_skip_on_timeout=True
        )
        result = await service.request_human_intervention(
            page=page, url=page.url, captcha_type=captcha_type
        )
        if result.success:
            logger.info(
                "CAPTCHA solved by user in %.1fs",
                result.duration_seconds,
            )
            await page.wait_for_timeout(2000)
            return True
        logger.warning(
            "CAPTCHA not solved: %s (%.1fs)",
            result.status.value,
            result.duration_seconds,
        )
        return False

    # -------------------------------------------------------------------
    # Content scraping and enhancement
    # -------------------------------------------------------------------

    async def _enhance_results_with_content(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance search results by scraping page content."""
        enhanced = []
        for result in results:
            try:
                domain = result["domain"]
                await self._respect_rate_limit(domain)
                content = await self._scrape_page_content(result["url"])
                result["content"] = content
                result["content_length"] = len(content)
                result["quality_score"] = self._calculate_quality_score(result)
                enhanced.append(result)
                await self._random_delay(1, 3)
            except Exception as e:
                logger.error("Failed to enhance %s: %s", result["url"], e)
                result["content"] = result.get("snippet", "")
                result["content_length"] = len(result["content"])
                result["quality_score"] = 0.5
                enhanced.append(result)
        return enhanced

    async def _scrape_page_content(self, url: str) -> str:
        """Scrape content from a web page."""
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            if await self._detect_captcha(page):
                logger.warning("CAPTCHA on %s, skipping scrape", url)
                return ""
            content = await self._extract_main_content(page)
            content = self._clean_content(content)
            return content[:5000]
        except Exception as e:
            logger.error("Failed to scrape %s: %s", url, e)
            return ""
        finally:
            await page.close()

    async def _extract_main_content(self, page) -> str:
        """Extract main content from page using common selectors."""
        selectors = [
            "article",
            "main",
            ".content",
            "#content",
            ".post",
            ".entry-content",
            ".article-content",
            '[role="main"]',
        ]
        for selector in selectors:
            el = await page.query_selector(selector)
            if el:
                return await el.inner_text()
        body = await page.query_selector("body")
        return await body.inner_text() if body else ""

    def _clean_content(self, content: str) -> str:
        """Clean scraped content of noise."""
        if not content:
            return ""
        lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
        cleaned = "\n".join(lines)
        noise = [
            "Cookie Policy",
            "Privacy Policy",
            "Terms of Service",
            "Subscribe to newsletter",
            "Follow us on",
            "Share this",
            "Advertisement",
            "Sponsored",
        ]
        for pattern in noise:
            cleaned = cleaned.replace(pattern, "")
        return cleaned.strip()

    # -------------------------------------------------------------------
    # Scoring and ranking
    # -------------------------------------------------------------------

    _TRUSTED_DOMAINS = [
        "github.com",
        "stackoverflow.com",
        "docs.python.org",
        "ubuntu.com",
        "redhat.com",
        "debian.org",
        "archlinux.org",
        "mozilla.org",
        "w3.org",
        "ietf.org",
    ]

    def _calculate_quality_score(self, result: Dict[str, Any]) -> float:
        """Calculate quality score for search result."""
        score = 0.5
        domain = result.get("domain", "")
        if any(t in domain for t in self._TRUSTED_DOMAINS):
            score += 0.3
        content_length = result.get("content_length", 0)
        if content_length > 2000:
            score += 0.2
        elif content_length > 1000:
            score += 0.1
        title = result.get("title", "").lower()
        if 10 < len(title) < 100:
            score += 0.1
        return min(score, 1.0)

    def _deduplicate_results(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate search results by URL."""
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for result in results:
            url = result.get("url", "")
            normalized = url.split("?")[0].split("#")[0]
            if normalized not in seen:
                seen.add(normalized)
                unique.append(result)
        return unique

    def _rank_results(
        self, results: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        """Rank search results by relevance."""
        query_terms = set(query.lower().split())
        for result in results:
            title_terms = set(result.get("title", "").lower().split())
            snippet_terms = set(result.get("snippet", "").lower().split())
            title_overlap = (
                len(query_terms & title_terms) / len(query_terms) if query_terms else 0
            )
            snippet_overlap = (
                len(query_terms & snippet_terms) / len(query_terms)
                if query_terms
                else 0
            )
            result["relevance_score"] = title_overlap * 0.7 + snippet_overlap * 0.3
        return sorted(
            results,
            key=lambda x: x.get("relevance_score", 0),
            reverse=True,
        )

    # -------------------------------------------------------------------
    # Rate limiting
    # -------------------------------------------------------------------

    async def _respect_rate_limit(self, domain: str):
        """Per-domain rate limiting (async-safe)."""
        min_interval = 2
        async with self._domain_rate_lock:
            wait_time = 0.0
            if domain in self._domain_rate_limiter:
                elapsed = time.time() - self._domain_rate_limiter[domain]
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
            self._domain_rate_limiter[domain] = time.time()
        if wait_time > 0:
            logger.info(
                "Rate limiting: waiting %.2fs for %s",
                wait_time,
                domain,
            )
            await asyncio.sleep(wait_time)

    async def _random_delay(self, min_seconds: float, max_seconds: float):
        """Add random delay to mimic human behavior."""
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))

    # -------------------------------------------------------------------
    # Orchestrated research (from WebResearchIntegration)
    # -------------------------------------------------------------------

    async def is_enabled(self) -> bool:
        """Check if web research is enabled."""
        return self.enabled

    async def enable_research(self, user_confirmed: bool = False) -> bool:
        """Enable web research with user confirmation."""
        if user_confirmed:
            self.enabled = True
            logger.info("Web research enabled by user confirmation")
            return True
        return False

    async def disable_research(self) -> bool:
        """Disable web research."""
        self.enabled = False
        logger.info("Web research disabled")
        return True

    async def conduct_research(
        self,
        query: str,
        research_type: Optional[ResearchType] = None,
        max_results: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Conduct web research with circuit breaker, rate limiting,
        and caching. Primary orchestration entry point.
        """
        if not self.enabled:
            return self._build_disabled_response(query)

        cache_key = self._generate_cache_key(query, research_type, max_results)
        cached = self._get_cached_result(cache_key)
        if cached:
            logger.info("Returning cached result for: %s...", query[:50])
            cached["from_cache"] = True
            return cached

        if not await self.rate_limiter.acquire():
            return self._build_rate_limited_response(query)

        max_res = max_results or self.max_results_default
        timeout_secs = timeout or self.timeout_seconds

        if not self.circuit_breaker.can_execute():
            logger.warning("Circuit breaker open, skipping search")
            return self._build_failure_response(query)

        try:
            task = asyncio.create_task(self.search_web(query, max_res))
            result = await asyncio.wait_for(task, timeout=timeout_secs)
            self.circuit_breaker.call_succeeded()
            result["method_used"] = "web_search"
            result["timestamp"] = datetime.now().isoformat()
            if result.get("status") == "success":
                self._cache_result(cache_key, result)
            return result
        except asyncio.TimeoutError:
            logger.warning("Research timed out after %ss", timeout_secs)
            self.circuit_breaker.call_failed()
            return self._build_failure_response(query)
        except Exception as e:
            logger.error("Research failed: %s", e)
            self.circuit_breaker.call_failed()
            return self._build_failure_response(query)

    def _build_disabled_response(self, query: str) -> Dict[str, Any]:
        """Build response for disabled state."""
        return {
            "status": "disabled",
            "message": (
                "Web research is disabled. "
                "Enable it in settings to use this feature."
            ),
            "query": query,
            "results": [],
            "timestamp": datetime.now().isoformat(),
        }

    def _build_rate_limited_response(self, query: str) -> Dict[str, Any]:
        """Build response for rate-limited state."""
        return {
            "status": "rate_limited",
            "message": ("Too many research requests. " "Please wait and try again."),
            "query": query,
            "results": [],
            "timestamp": datetime.now().isoformat(),
        }

    def _build_failure_response(self, query: str) -> Dict[str, Any]:
        """Build response when research fails."""
        return {
            "status": "failed",
            "message": "Research failed or circuit breaker open.",
            "query": query,
            "results": [],
            "timestamp": datetime.now().isoformat(),
        }

    # -------------------------------------------------------------------
    # Research API (from ResearchAgent)
    # -------------------------------------------------------------------

    async def perform_research(self, request: ResearchRequest) -> ResearchResponse:
        """Perform web research and return structured response."""
        start_time = time.time()
        logger.info(
            "Research for: '%s' focus: '%s'",
            request.query,
            request.focus,
        )
        try:
            search_results = await self.search_web(request.query, request.max_results)
            results = self._convert_to_research_results(search_results)
            summary = self._generate_research_summary(results, request.query)
            return ResearchResponse(
                success=True,
                query=request.query,
                results=results,
                summary=summary,
                execution_time=time.time() - start_time,
                sources_count=len(results),
            )
        except Exception as e:
            logger.error("Research failed for '%s': %s", request.query, e)
            return ResearchResponse(
                success=False,
                query=request.query,
                results=[],
                summary=f"Research failed: {e}",
                execution_time=time.time() - start_time,
                sources_count=0,
            )

    def _convert_to_research_results(
        self, search_results: Dict[str, Any]
    ) -> List[ResearchResult]:
        """Convert raw search results to ResearchResult models."""
        results = []
        if search_results.get("status") != "success":
            return results
        for item in search_results.get("results", []):
            results.append(
                ResearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("snippet", item.get("content", "")),
                    relevance_score=item.get("relevance_score", 0.8),
                    source_type=item.get("search_engine", "web"),
                )
            )
        return results

    async def research_specific_tools(self, request: ResearchRequest) -> Dict[str, Any]:
        """Research specific tools with installation info."""
        query_lower = request.query.lower()
        try:
            search_results = await self.search_web(request.query, request.max_results)
            research_results = self._convert_to_research_results(search_results)

            tools_found = []
            detailed_info: Dict[str, Any] = {}
            for name, info in _TOOL_REFERENCE_DATA.items():
                if name in query_lower:
                    tools_found.append(name)
                    detailed_info[name] = info

            return {
                "success": True,
                "tools_found": tools_found,
                "detailed_info": detailed_info,
                "research_results": [r.model_dump() for r in research_results],
                "web_search_results": search_results.get("results", []),
                "summary": self._generate_research_summary(
                    research_results, request.query
                ),
            }
        except Exception as e:
            logger.error("Tool research failed: %s", e)
            return await self.perform_research(request)

    async def _fetch_web_resources(self, tool_name: str, max_results: int = 3) -> list:
        """Fetch web resources for tool installation. Issue #620."""
        try:
            results = await self.search_web(
                f"{tool_name} installation guide",
                max_results=max_results,
            )
            if results.get("status") == "success":
                return results.get("results", [])
        except Exception as e:
            logger.warning("Web search for %s failed: %s", tool_name, e)
        return []

    def _build_guide_from_reference(
        self,
        tool_name: str,
        tool_info: Dict[str, Any],
        web_results: list,
    ) -> Dict[str, Any]:
        """Build installation guide from reference data. Issue #620."""
        return {
            "success": True,
            "tool_name": tool_name,
            "installation_command": tool_info.get("installation", "Not available"),
            "usage_example": tool_info.get("usage", "Not available"),
            "prerequisites": tool_info.get("prerequisites", ["sudo privileges"]),
            "verification_command": tool_info.get(
                "verification", f"{tool_name} --version"
            ),
            "web_resources": web_results,
        }

    async def get_tool_installation_guide(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed installation guide for a tool."""
        tool_lower = tool_name.lower()

        if tool_lower in _TOOL_REFERENCE_DATA:
            info = _TOOL_REFERENCE_DATA[tool_lower]
            web = await self._fetch_web_resources(tool_name, 3)
            return self._build_guide_from_reference(tool_name, info, web)

        web = await self._fetch_web_resources(tool_name, 5)
        if web:
            return {
                "success": True,
                "tool_name": tool_name,
                "installation_command": "See web resources below",
                "usage_example": "See web resources below",
                "prerequisites": ["sudo privileges"],
                "verification_command": f"{tool_name} --version",
                "web_resources": web,
                "note": "Tool not in reference database",
            }

        return {
            "success": False,
            "tool_name": tool_name,
            "error": "Tool info not available, web search failed",
        }

    def _get_verification_command(self, tool_name: str) -> str:
        """Get command to verify tool installation."""
        tool_lower = tool_name.lower()
        if tool_lower in _TOOL_REFERENCE_DATA:
            return _TOOL_REFERENCE_DATA[tool_lower].get(
                "verification", f"{tool_name} --version"
            )
        return f"{tool_name} --version"

    # -------------------------------------------------------------------
    # Summary generation
    # -------------------------------------------------------------------

    def _generate_research_summary(
        self, results: List[ResearchResult], query: str
    ) -> str:
        """Generate summary from ResearchResult list."""
        if not results:
            return f"No relevant results found for '{query}'"
        high_q = [r for r in results if r.relevance_score > 0.8]
        types = set(r.source_type for r in results if r.source_type)
        summary = (
            f"Research completed for '{query}' with "
            f"{len(results)} results found. "
            f"{len(high_q)} high-quality sources identified."
        )
        if types:
            summary += f" Results from: {', '.join(types)}."
        if results:
            summary += f" Top result: '{results[0].title}'"
        return summary

    def _generate_source_summary(
        self, sources: List[Dict[str, Any]], query: str
    ) -> str:
        """Generate summary from source dicts (for KB integration)."""
        if not sources:
            return "No relevant information found."
        top = sources[:3]
        parts = [f"Based on web research for '{query}', " f"here are the key findings:"]
        for i, src in enumerate(top, 1):
            title = src["title"]
            snippet = src.get("snippet", "")
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            parts.append(f"{i}. {title}: {snippet}")
        if len(sources) > 3:
            parts.append(f"({len(sources) - 3} additional sources found)")
        return "\n\n".join(parts)

    # -------------------------------------------------------------------
    # KB integration (from WebResearchAssistant)
    # -------------------------------------------------------------------

    async def research_query(self, query: str) -> Dict[str, Any]:
        """Research a query and return structured results with KB info.

        Compatible with WebResearchAssistant interface for librarian.
        """
        logger.info("Starting research for query: %s", query)

        cache_key = f"rq:{hash(query)}"
        cached = self._get_cached_result(cache_key)
        if cached:
            logger.info("Returning cached results for: %s", query)
            cached["from_cache"] = True
            return cached

        try:
            search_results = await self.search_web(query, 8)
            if search_results.get("status") != "success":
                return self._build_rq_error(query, "Search failed")

            sources = self._convert_to_sources(search_results)
            summary = self._generate_source_summary(sources, query)
            kb_worthy = [
                s for s in sources if s["quality_score"] >= self.quality_threshold
            ]

            result = {
                "status": "success",
                "query": query,
                "sources": sources,
                "summary": summary,
                "stored_in_kb": kb_worthy,
                "search_engines_used": search_results.get("search_engines_used", 0),
                "total_found": search_results.get("total_found", 0),
                "timestamp": datetime.now().isoformat(),
                "from_cache": False,
                "research_method": "advanced",
            }
            self._cache_result(cache_key, result)
            return result
        except Exception as e:
            logger.error("Research failed for %s: %s", query, e)
            return self._build_rq_error(query, str(e))

    def _build_rq_error(self, query: str, error: str) -> Dict[str, Any]:
        """Build error response for research_query."""
        return {
            "status": "error",
            "query": query,
            "error": error,
            "sources": [],
            "summary": None,
            "timestamp": datetime.now().isoformat(),
        }

    def _convert_to_sources(
        self, search_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Convert search results to source format for KB."""
        sources = []
        for r in search_results.get("results", []):
            sources.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "domain": r.get("domain", ""),
                    "snippet": r.get("snippet", ""),
                    "content": r.get("content", ""),
                    "quality_score": r.get("quality_score", 0.5),
                    "relevance": r.get("relevance_score", 0.5),
                    "search_engine": r.get("search_engine", "unknown"),
                    "timestamp": r.get("timestamp", datetime.now().isoformat()),
                }
            )
        return sources

    async def search_and_store_knowledge(
        self, query: str, knowledge_base
    ) -> Dict[str, Any]:
        """Research query and store high-quality results in KB."""
        research_results = await self.research_query(query)
        if research_results.get("status") != "success":
            return research_results

        stored_count = 0
        for source in research_results.get("stored_in_kb", []):
            try:
                kb_content = self._format_for_kb(source, query)
                await knowledge_base.add_document(
                    content=kb_content,
                    metadata={
                        "source": "web_research",
                        "query": query,
                        "url": source["url"],
                        "title": source["title"],
                        "quality_score": source["quality_score"],
                        "timestamp": source["timestamp"],
                    },
                )
                stored_count += 1
            except Exception as e:
                logger.error("Failed to store in KB: %s", e)

        research_results["kb_storage_count"] = stored_count
        logger.info("Stored %s sources in knowledge base", stored_count)
        return research_results

    def _format_for_kb(self, source: Dict[str, Any], query: str) -> str:
        """Format source content for knowledge base storage."""
        return (
            f"Title: {source['title']}\n"
            f"Source: {source['url']}\n"
            f"Query Context: {query}\n\n"
            f"Content:\n{source['content']}\n\n"
            f"Quality Score: {source['quality_score']}\n"
            f"Relevance Score: {source['relevance']}"
        )

    # -------------------------------------------------------------------
    # Cache management
    # -------------------------------------------------------------------

    def _generate_cache_key(
        self,
        query: str,
        research_type: Optional[ResearchType],
        max_results: Optional[int],
    ) -> str:
        """Generate cache key for research result."""
        method = research_type.value if research_type else "default"
        results = max_results or self.max_results_default
        return f"research:{hash(query)}:{method}:{results}"

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached research result if still valid."""
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            cache_time = cached_data.get("cached_at", 0)
            if time.time() - cache_time < self._cache_ttl:
                return cached_data.get("result")
            del self._cache[cache_key]
        return None

    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache research result with TTL."""
        self._cache[cache_key] = {
            "result": result,
            "cached_at": time.time(),
        }
        if len(self._cache) > 100:
            self._cleanup_cache()

    def _cleanup_cache(self):
        """Clean up expired cache entries."""
        now = time.time()
        expired = [
            k
            for k, v in self._cache.items()
            if now - v.get("cached_at", 0) > self._cache_ttl
        ]
        for k in expired:
            del self._cache[k]
        logger.debug("Cleaned up %s expired cache entries", len(expired))

    async def clear_cache(self):
        """Clear the search cache."""
        async with self._cache_lock:
            self._cache.clear()
        logger.info("Web research cache cleared")

    # -------------------------------------------------------------------
    # Monitoring and health
    # -------------------------------------------------------------------

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of circuit breaker."""
        cb = self.circuit_breaker
        return {
            "search": {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "last_failure": cb.last_failure_time,
            }
        }

    def reset_circuit_breakers(self):
        """Reset circuit breaker."""
        self.circuit_breaker.reset()
        logger.info("Circuit breaker reset")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
            "rate_limiter": {
                "max_requests": self.rate_limiter.max_requests,
                "window_seconds": self.rate_limiter.window_seconds,
                "current_requests": len(self.rate_limiter.requests),
            },
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on research integration."""
        return {
            "enabled": self.enabled,
            "circuit_breaker": self.get_circuit_breaker_status(),
            "cache_stats": self.get_cache_stats(),
            "browser_initialized": self.browser is not None,
        }


# ---------------------------------------------------------------------------
# Global singleton (from web_research_integration.py)
# ---------------------------------------------------------------------------

_global_researcher: Optional[WebResearcher] = None
_global_researcher_lock = threading.Lock()


def _load_web_research_config() -> Dict[str, Any]:
    """Load web research config from config manager."""
    try:
        from config import config_manager

        return config_manager.get_nested("web_research", {})
    except Exception as e:
        logger.warning("Could not load web research config: %s", e)
        return {}


def get_web_researcher(
    config: Optional[Dict[str, Any]] = None,
) -> WebResearcher:
    """Get or create global web researcher instance (thread-safe)."""
    global _global_researcher

    if _global_researcher is not None:
        return _global_researcher

    with _global_researcher_lock:
        if _global_researcher is None:
            if config is None:
                config = _load_web_research_config()
            _global_researcher = WebResearcher(config)

    return _global_researcher


# Backward compatibility alias
get_web_research_integration = get_web_researcher


async def conduct_web_research(query: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to conduct web research."""
    researcher = get_web_researcher()
    return await researcher.conduct_research(query, **kwargs)


# Factory function
async def create_web_researcher(
    config: Optional[Dict[str, Any]] = None,
) -> WebResearcher:
    """Create and initialize a web researcher instance."""
    researcher = WebResearcher(config)
    await researcher.initialize()
    return researcher
