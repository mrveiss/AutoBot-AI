# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Web Research Assistant - Tier 2 Implementation
Includes browser automation, anti-detection, and CAPTCHA handling
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from constants.security_constants import SecurityConstants
from constants.threshold_constants import TimingConstants
from services.captcha_human_loop import get_captcha_human_loop

# Issue #380: Module-level frozenset for CAPTCHA detection keywords
_CAPTCHA_KEYWORDS: frozenset = frozenset({"captcha", "challenge", "verification"})

try:
    from playwright.async_api import Browser, BrowserContext, Page, async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    # Create dummy types for type hints when Playwright isn't available
    Browser = Any
    Page = Any
    BrowserContext = Any
    async_playwright = None
    logging.warning("Playwright not available. Install with: pip install playwright")

try:
    pass

    from autobot_shared.http_client import get_http_client

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp not available. Install with: pip install aiohttp")
    get_http_client = None

logger = logging.getLogger(__name__)


class CaptchaSolver:
    """Integration with CAPTCHA solving services"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize CAPTCHA solver with API key and service configuration."""
        self.api_key = config.get("api_key")
        self.service = config.get("service", "2captcha")  # 2captcha, anticaptcha, etc.
        self.timeout = config.get("timeout", 120)  # 2 minutes default

    async def solve_recaptcha(
        self, site_key: str, page_url: str, invisible: bool = False
    ) -> Optional[str]:
        """Solve reCAPTCHA using solving service"""
        if not self.api_key:
            logger.warning("No CAPTCHA API key configured")
            return None

        try:
            if self.service == "2captcha":
                return await self._solve_2captcha_recaptcha(
                    site_key, page_url, invisible
                )
            elif self.service == "anticaptcha":
                return await self._solve_anticaptcha_recaptcha(
                    site_key, page_url, invisible
                )
            else:
                logger.error("Unsupported CAPTCHA service: %s", self.service)
                return None
        except Exception as e:
            logger.error("CAPTCHA solving failed: %s", str(e))
            return None

    async def _solve_2captcha_recaptcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Solve reCAPTCHA using 2captcha service"""
        if not AIOHTTP_AVAILABLE:
            return None

        submit_url = "http://2captcha.com/in.php"
        result_url = "http://2captcha.com/res.php"

        # Submit CAPTCHA
        submit_data = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "invisible": 1 if invisible else 0,
            "json": 1,
        }

        # Use singleton HTTP client
        http_client = get_http_client()

        # Submit CAPTCHA for solving
        submit_result = await http_client.post_json(submit_url, json_data=submit_data)

        if submit_result.get("status") != 1:
            logger.error("CAPTCHA submit failed: %s", submit_result)
            return None

        captcha_id = submit_result["request"]
        logger.info("CAPTCHA submitted, ID: %s", captcha_id)

        # Poll for result
        for attempt in range(self.timeout // 5):
            await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

            # Use HTTP client for result polling
            result = await http_client.get_json(
                f"{result_url}?key={self.api_key}&action=get&id={captcha_id}&json=1"
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

    async def _solve_anticaptcha_recaptcha(
        self, site_key: str, page_url: str, invisible: bool
    ) -> Optional[str]:
        """Solve reCAPTCHA using AntiCaptcha service"""
        # Similar implementation for AntiCaptcha API
        # This is a placeholder for the actual implementation
        logger.info("AntiCaptcha integration not implemented yet")
        return None


class BrowserFingerprint:
    """Manages browser fingerprinting and randomization"""

    USER_AGENTS = SecurityConstants.USER_AGENT_POOL

    VIEWPORTS = [
        {"width": 1920, "height": 1080},  # Full HD - prioritized
        {"width": 1920, "height": 1080},  # Duplicate for higher probability
        {"width": 1536, "height": 864},  # High resolution
        {"width": 1440, "height": 900},  # MacBook Pro
        {"width": 1366, "height": 768},  # Common laptop
        {"width": 1280, "height": 720},  # HD minimum
    ]

    def __init__(self):
        """Initialize fingerprint manager with randomized browser fingerprint."""
        self.current_fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """Generate randomized browser fingerprint"""
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


class AdvancedWebResearcher:
    """Advanced web research with anti-detection and automation"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize researcher with browser automation and anti-detection config."""
        self.config = config or {}
        self.fingerprint = BrowserFingerprint()
        self.captcha_solver = CaptchaSolver(self.config.get("captcha", {}))
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.search_cache = {}
        self.rate_limiter = {}  # Domain -> last request time
        self._rate_lock = asyncio.Lock()  # Lock for rate_limiter access

    async def initialize(self):
        """Initialize browser automation"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not available. "
                "Run: pip install playwright && playwright install"
            )

        playwright = await async_playwright().start()

        # Launch browser with anti-detection settings
        self.browser = await playwright.chromium.launch(
            headless=self.config.get("headless", True),
            args=[
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
            ],
        )

        # Create context with randomized fingerprint
        await self._create_context()

    async def _create_context(self):
        """Create browser context with anti-detection"""
        fingerprint = self.fingerprint.get_fingerprint()

        self.context = await self.browser.new_context(
            user_agent=fingerprint["user_agent"],
            viewport=fingerprint["viewport"],
            timezone_id=fingerprint["timezone"],
            locale=fingerprint["language"].split(",")[0],
            extra_http_headers={
                "Accept-Language": fingerprint["language"],
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/webp,*/*;q=0.8"
                ),
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Add stealth scripts
        await self.context.add_init_script(
            """
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // Mock permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """
        )

    async def _search_all_engines(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """
        Execute search across all configured search engines.

        Args:
            query: Search query string
            max_results: Maximum results per engine

        Returns:
            Combined list of results from all engines. Issue #620.
        """
        search_engines = [
            ("duckduckgo", self._search_duckduckgo),
            ("bing", self._search_bing),
            ("google", self._search_google),
        ]
        all_results = []

        for engine_name, search_func in search_engines:
            try:
                logger.info("Searching %s for: %s", engine_name, query)
                results = await search_func(
                    query, max_results // len(search_engines) + 1
                )
                for result in results:
                    result["search_engine"] = engine_name
                    result["timestamp"] = datetime.now().isoformat()
                all_results.extend(results)
                await self._random_delay(2, 5)
            except Exception as e:
                logger.error("Search engine %s failed: %s", engine_name, str(e))
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
        """
        Build successful search response dictionary.

        Args:
            query: Original search query
            results: Enhanced search results
            total_found: Total results found
            unique_count: Unique results count
            engine_count: Number of engines used

        Returns:
            Search response dictionary. Issue #620.
        """
        return {
            "status": "success",
            "query": query,
            "results": results,
            "total_found": total_found,
            "unique_results": unique_count,
            "search_engines_used": engine_count,
            "timestamp": datetime.now().isoformat(),
        }

    async def search_web(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Perform web search with anti-detection. Issue #620."""
        logger.info("Starting advanced web search for: %s", query)

        if not self.browser:
            await self.initialize()

        try:
            all_results = await self._search_all_engines(query, max_results)
            unique_results = self._deduplicate_results(all_results)
            ranked_results = self._rank_results(unique_results, query)[:max_results]
            enhanced_results = await self._enhance_results_with_content(ranked_results)

            return self._build_search_response(
                query, enhanced_results, len(all_results), len(unique_results), 3
            )

        except Exception as e:
            logger.error("Advanced web search failed: %s", str(e))
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "results": [],
                "timestamp": datetime.now().isoformat(),
            }

    async def _search_duckduckgo(
        self, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """Search DuckDuckGo with anti-detection"""
        page = await self.context.new_page()
        results = []

        try:
            await page.goto("https://duckduckgo.com/", wait_until="networkidle")

            # Handle potential CAPTCHA
            if await self._detect_captcha(page):
                captcha_solved = await self._handle_captcha(page)
                if not captcha_solved:
                    logger.warning("CAPTCHA not solved, skipping DuckDuckGo")
                    return results

            # Perform search
            await page.fill('[name="q"]', query)
            await page.press('[name="q"]', "Enter")
            await page.wait_for_load_state("networkidle")

            # Extract results
            result_elements = await page.query_selector_all('[data-result="result"]')

            for element in result_elements[:max_results]:
                try:
                    title_el = await element.query_selector("h2 a")
                    snippet_el = await element.query_selector('[data-result="snippet"]')

                    if title_el and snippet_el:
                        title = await title_el.inner_text()
                        url = await title_el.get_attribute("href")
                        snippet = await snippet_el.inner_text()

                        results.append(
                            {
                                "title": title.strip(),
                                "url": url,
                                "snippet": snippet.strip(),
                                "domain": urlparse(url).netloc if url else "",
                            }
                        )

                except Exception as e:
                    logger.error("Error extracting DuckDuckGo result: %s", str(e))
                    continue

        finally:
            await page.close()

        return results

    async def _search_bing(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Search Bing with anti-detection"""
        page = await self.context.new_page()
        results = []

        try:
            await page.goto("https://www.bing.com/", wait_until="networkidle")

            # Handle potential CAPTCHA
            if await self._detect_captcha(page):
                captcha_solved = await self._handle_captcha(page)
                if not captcha_solved:
                    logger.warning("CAPTCHA not solved, skipping Bing")
                    return results

            # Perform search
            await page.fill('[name="q"]', query)
            await page.press('[name="q"]', "Enter")
            await page.wait_for_load_state("networkidle")

            # Extract results
            result_elements = await page.query_selector_all(".b_algo")

            for element in result_elements[:max_results]:
                try:
                    title_el = await element.query_selector("h2 a")
                    snippet_el = await element.query_selector(".b_caption p")

                    if title_el and snippet_el:
                        title = await title_el.inner_text()
                        url = await title_el.get_attribute("href")
                        snippet = await snippet_el.inner_text()

                        results.append(
                            {
                                "title": title.strip(),
                                "url": url,
                                "snippet": snippet.strip(),
                                "domain": urlparse(url).netloc if url else "",
                            }
                        )

                except Exception as e:
                    logger.error("Error extracting Bing result: %s", str(e))
                    continue

        finally:
            await page.close()

        return results

    async def _accept_cookies(self, page) -> None:
        """Accept cookies dialog if present (Issue #334 - extracted helper)."""
        try:
            accept_button = await page.query_selector(
                'button[id*="accept"], button[id*="agree"]'
            )
            if accept_button:
                await accept_button.click()
                await page.wait_for_timeout(1000)
        except Exception as e:
            logger.debug("Cookie dialog not found or not clickable: %s", e)

    async def _extract_google_result(self, element) -> Dict[str, Any] | None:
        """Extract single Google search result (Issue #334 - extracted helper)."""
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
        """Search Google with anti-detection (more aggressive protection)"""
        page = await self.context.new_page()
        results = []

        try:
            await page.goto("https://www.google.com/", wait_until="networkidle")

            if await self._detect_captcha(page):
                captcha_solved = await self._handle_captcha(page)
                if not captcha_solved:
                    logger.warning("CAPTCHA not solved, skipping Google")
                    return results

            await self._accept_cookies(page)

            search_box = await page.query_selector('[name="q"], [title="Search"]')
            if not search_box:
                return results

            await search_box.fill(query)
            await search_box.press("Enter")
            await page.wait_for_load_state("networkidle")

            result_elements = await page.query_selector_all("[data-ved] h3")
            for element in result_elements[:max_results]:
                try:
                    result = await self._extract_google_result(element)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error("Error extracting Google result: %s", str(e))

        finally:
            await page.close()

        return results

    async def _detect_captcha(self, page: Page) -> bool:
        """Detect if CAPTCHA is present on page"""
        captcha_selectors = [
            ".g-recaptcha",
            ".h-captcha",
            ".captcha",
            "[data-sitekey]",
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            "#captcha",
            ".cf-challenge-running",
        ]

        for selector in captcha_selectors:
            element = await page.query_selector(selector)
            if element:
                logger.info("CAPTCHA detected with selector: %s", selector)
                return True

        # Check page title and content for CAPTCHA indicators
        title = await page.title()
        if any(keyword in title.lower() for keyword in _CAPTCHA_KEYWORDS):
            logger.info("CAPTCHA detected in page title: %s", title)
            return True

        return False

    async def _detect_captcha_type(self, page: Page) -> str:
        """
        Detect the type of CAPTCHA present on the page.

        Args:
            page: Playwright page instance

        Returns:
            String identifier for the CAPTCHA type. Issue #620.
        """
        if await page.query_selector(".g-recaptcha, [data-sitekey]"):
            return "recaptcha"
        elif await page.query_selector(".h-captcha"):
            return "hcaptcha"
        elif await page.query_selector(".cf-challenge-running"):
            return "cloudflare"
        return "unknown"

    async def _try_automated_recaptcha_solving(self, page: Page) -> bool:
        """
        Attempt automated reCAPTCHA solving using the captcha solver service.

        Args:
            page: Playwright page instance

        Returns:
            True if CAPTCHA was solved automatically, False otherwise. Issue #620.
        """
        recaptcha_element = await page.query_selector(".g-recaptcha, [data-sitekey]")
        if not recaptcha_element:
            return False

        site_key = await recaptcha_element.get_attribute("data-sitekey")
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

    async def _request_human_captcha_intervention(
        self, page: Page, captcha_type: str
    ) -> bool:
        """
        Request human intervention to solve CAPTCHA via human-in-the-loop service.

        Args:
            page: Playwright page instance
            captcha_type: Type of CAPTCHA detected

        Returns:
            True if human solved the CAPTCHA, False otherwise. Issue #620.
        """
        captcha_service = get_captcha_human_loop(
            timeout_seconds=120.0,
            auto_skip_on_timeout=True,
        )

        result = await captcha_service.request_human_intervention(
            page=page,
            url=page.url,
            captcha_type=captcha_type,
        )

        if result.success:
            logger.info("CAPTCHA solved by user in %.1fs", result.duration_seconds)
            await page.wait_for_timeout(2000)
            return True

        logger.warning(
            "CAPTCHA not solved: %s (waited %.1fs)",
            result.status.value,
            result.duration_seconds,
        )
        return False

    async def _handle_captcha(self, page: Page) -> bool:
        """Handle CAPTCHA challenge with human-in-the-loop fallback"""
        logger.info("Attempting to handle CAPTCHA challenge")

        captcha_type = await self._detect_captcha_type(page)

        if await self._try_automated_recaptcha_solving(page):
            return True

        logger.warning(
            "Automated CAPTCHA solving failed, requesting human intervention"
        )
        return await self._request_human_captcha_intervention(page, captcha_type)

    async def _enhance_results_with_content(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance search results by scraping content from pages"""
        enhanced_results = []

        for result in results:
            try:
                # Rate limiting per domain
                domain = result["domain"]
                await self._respect_rate_limit(domain)

                # Scrape content
                content = await self._scrape_page_content(result["url"])
                result["content"] = content
                result["content_length"] = len(content)
                result["quality_score"] = self._calculate_quality_score(result)

                enhanced_results.append(result)

                # Random delay between requests
                await self._random_delay(1, 3)

            except Exception as e:
                logger.error("Failed to enhance result %s: %s", result["url"], str(e))
                result["content"] = result.get("snippet", "")
                result["content_length"] = len(result["content"])
                result["quality_score"] = 0.5
                enhanced_results.append(result)

        return enhanced_results

    async def _scrape_page_content(self, url: str) -> str:
        """Scrape content from a web page"""
        page = await self.context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Handle potential CAPTCHA
            if await self._detect_captcha(page):
                logger.warning("CAPTCHA detected on %s, skipping content scraping", url)
                return ""

            # Extract main content
            content_selectors = [
                "article",
                "main",
                ".content",
                "#content",
                ".post",
                ".entry-content",
                ".article-content",
                '[role="main"]',
            ]

            content = ""
            for selector in content_selectors:
                element = await page.query_selector(selector)
                if element:
                    content = await element.inner_text()
                    break

            # Fallback to body content if no specific content found
            if not content:
                body = await page.query_selector("body")
                if body:
                    content = await body.inner_text()

            # Clean and limit content
            content = self._clean_content(content)
            return content[:5000]  # Limit to 5000 characters

        except Exception as e:
            logger.error("Failed to scrape content from %s: %s", url, str(e))
            return ""
        finally:
            await page.close()

    def _clean_content(self, content: str) -> str:
        """Clean scraped content"""
        if not content:
            return ""

        # Remove excessive whitespace
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        cleaned = "\n".join(lines)

        # Remove common noise
        noise_patterns = [
            "Cookie Policy",
            "Privacy Policy",
            "Terms of Service",
            "Subscribe to newsletter",
            "Follow us on",
            "Share this",
            "Advertisement",
            "Sponsored",
        ]

        for pattern in noise_patterns:
            cleaned = cleaned.replace(pattern, "")

        return cleaned.strip()

    def _calculate_quality_score(self, result: Dict[str, Any]) -> float:
        """Calculate quality score for search result"""
        score = 0.5  # Base score

        # Domain reputation
        trusted_domains = [
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

        domain = result.get("domain", "")
        if any(trusted in domain for trusted in trusted_domains):
            score += 0.3

        # Content quality indicators
        content_length = result.get("content_length", 0)
        if content_length > 2000:
            score += 0.2
        elif content_length > 1000:
            score += 0.1

        # Title relevance (already calculated during ranking)
        title = result.get("title", "").lower()
        if len(title) > 10 and len(title) < 100:  # Good title length
            score += 0.1

        return min(score, 1.0)

    def _deduplicate_results(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate search results"""
        seen_urls = set()
        unique_results = []

        for result in results:
            url = result.get("url", "")
            normalized_url = url.split("?")[0].split("#")[
                0
            ]  # Remove query params and fragments

            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique_results.append(result)

        return unique_results

    def _rank_results(
        self, results: List[Dict[str, Any]], query: str
    ) -> List[Dict[str, Any]]:
        """Rank search results by relevance"""
        query_terms = set(query.lower().split())

        for result in results:
            # Calculate relevance score
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

            result["relevance_score"] = (title_overlap * 0.7) + (snippet_overlap * 0.3)

        # Sort by relevance
        return sorted(results, key=lambda x: x.get("relevance_score", 0), reverse=True)

    async def _respect_rate_limit(self, domain: str):
        """Implement rate limiting per domain (thread-safe)"""
        min_interval = 2  # Minimum 2 seconds between requests to same domain

        # Check rate limit under lock
        async with self._rate_lock:
            wait_time = 0.0
            if domain in self.rate_limiter:
                last_request = self.rate_limiter[domain]
                elapsed = time.time() - last_request

                if elapsed < min_interval:
                    wait_time = min_interval - elapsed

            # Update timestamp before waiting (prevents other requests from also waiting)
            self.rate_limiter[domain] = time.time()

        # Wait outside lock if needed
        if wait_time > 0:
            logger.info("Rate limiting: waiting %.2fs for %s", wait_time, domain)
            await asyncio.sleep(wait_time)

    async def _random_delay(self, min_seconds: float, max_seconds: float):
        """Add random delay to mimic human behavior"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def close(self):
        """Clean up browser resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def __aenter__(self):
        """Initialize browser and return self for context manager usage."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up browser resources when exiting context."""
        await self.close()


# Factory function for easy integration
async def create_advanced_web_researcher(
    config: Dict[str, Any] = None,
) -> AdvancedWebResearcher:
    """Create and initialize advanced web researcher"""
    researcher = AdvancedWebResearcher(config)
    await researcher.initialize()
    return researcher
