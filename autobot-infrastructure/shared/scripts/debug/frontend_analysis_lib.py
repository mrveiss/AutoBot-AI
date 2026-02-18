# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Frontend Analysis Library

Shared utilities for debugging frontend issues using Playwright.
Consolidates duplicate code from debug_frontend_browser.py and debug_frontend_browser_headless.py.

Issue: #148 - Extract frontend analysis library (Phase 3 - 200 line reduction)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, sync_playwright


class IssueSeverity(Enum):
    """Severity levels for frontend issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(Enum):
    """Types of frontend issues."""

    CONSOLE_ERROR = "console_error"
    NETWORK_ERROR = "network_error"
    DOM_ERROR = "dom_error"
    BUILD_ERROR = "build_error"
    VUE_ERROR = "vue_error"
    SCRIPT_ERROR = "script_error"


@dataclass
class FrontendIssue:
    """Structured frontend issue representation."""

    type: IssueType
    severity: IssueSeverity
    message: str
    location: Optional[str] = None
    recommendation: Optional[str] = None


@dataclass
class ConsoleLogEntry:
    """Captured console log entry."""

    type: str
    text: str
    location: Optional[Dict[str, Any]] = None


@dataclass
class NetworkRequestInfo:
    """Captured network request information."""

    url: str
    method: str
    resource_type: str
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class NetworkResponseInfo:
    """Captured network response information."""

    url: str
    status: int
    ok: bool
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    console_logs: List[ConsoleLogEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    network_requests: List[NetworkRequestInfo] = field(default_factory=list)
    network_responses: List[NetworkResponseInfo] = field(default_factory=list)
    issues: List[FrontendIssue] = field(default_factory=list)
    page_state: Dict[str, Any] = field(default_factory=dict)
    analysis_complete: bool = False


class FrontendDebugger:
    """
    Shared browser automation for frontend debugging.

    Provides common functionality for both headless and visual debugging modes.
    """

    def __init__(
        self,
        headless: bool = True,
        devtools: bool = False,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        verbose: bool = True,
    ):
        """
        Initialize the frontend debugger.

        Args:
            headless: Run browser in headless mode
            devtools: Open DevTools (visual mode only)
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            verbose: Print debug output to console
        """
        self.headless = headless
        self.devtools = devtools and not headless  # DevTools only works in visual mode
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.verbose = verbose

        # Data collectors
        self.console_logs: List[ConsoleLogEntry] = []
        self.errors: List[str] = []
        self.network_requests: List[NetworkRequestInfo] = []
        self.network_responses: List[NetworkResponseInfo] = []

    def _log(self, message: str) -> None:
        """Print message if verbose mode enabled."""
        if self.verbose:
            print(message)

    def _setup_event_handlers(self, page: Page) -> None:
        """Set up page event handlers for data collection."""

        def handle_console(msg):
            """Handle console log events and capture to log entries."""
            entry = ConsoleLogEntry(
                type=msg.type,
                text=msg.text,
                location=msg.location if hasattr(msg, "location") else None,
            )
            self.console_logs.append(entry)
            self._log(f"CONSOLE [{msg.type}]: {msg.text}")
            if entry.location:
                self._log(f"  Location: {entry.location}")

        def handle_page_error(error):
            """Handle page error events and capture error messages."""
            error_str = str(error)
            self.errors.append(error_str)
            self._log(f"PAGE ERROR: {error_str}")

        def handle_request(request):
            """Handle network request events and capture request details."""
            request_info = NetworkRequestInfo(
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
                headers=dict(request.headers),
            )
            self.network_requests.append(request_info)
            self._log(
                f"REQUEST: {request.method} {request.resource_type} {request.url}"
            )

        def handle_response(response):
            """Handle network response events and capture response status."""
            response_info = NetworkResponseInfo(
                url=response.url,
                status=response.status,
                ok=response.ok,
                headers=dict(response.headers),
            )
            self.network_responses.append(response_info)
            if response.status >= 400:
                self._log(f"FAILED RESPONSE: {response.status} {response.url}")

        page.on("console", handle_console)
        page.on("pageerror", handle_page_error)
        page.on("request", handle_request)
        page.on("response", handle_response)

    def _get_browser_args(self) -> List[str]:
        """Get browser launch arguments based on mode."""
        if self.headless:
            return ["--disable-web-security", "--no-sandbox"]
        return [
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
        ]

    def analyze_page(
        self,
        url: str,
        timeout: int = 20000,
        wait_after_load: int = 5,
        screenshot_path: Optional[str] = "/tmp/frontend_debug_screenshot.png",
        manual_inspection_time: int = 0,
    ) -> AnalysisResult:
        """
        Analyze a frontend page for issues.

        Args:
            url: URL to analyze
            timeout: Navigation timeout in milliseconds
            wait_after_load: Seconds to wait after page load
            screenshot_path: Path to save screenshot (None to skip)
            manual_inspection_time: Seconds to keep browser open for manual inspection

        Returns:
            AnalysisResult with collected data and detected issues
        """
        # Reset collectors
        self.console_logs = []
        self.errors = []
        self.network_requests = []
        self.network_responses = []

        result = AnalysisResult()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                devtools=self.devtools,
                args=self._get_browser_args(),
            )

            context = browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height}
            )

            page = context.new_page()
            self._setup_event_handlers(page)

            try:
                self._log("=" * 80)
                self._log(f"NAVIGATING TO: {url}")
                self._log("=" * 80)

                # Navigate to page
                wait_until = "networkidle" if self.headless else "load"
                response = page.goto(url, wait_until=wait_until, timeout=timeout)
                self._log(
                    f"Navigation response: {response.status if response else 'No response'}"
                )

                # Wait for additional loading
                if wait_after_load > 0:
                    self._log(f"Waiting {wait_after_load}s for page to fully load...")
                    time.sleep(wait_after_load)

                # Analyze page content
                page_state = self._analyze_page_content(page)
                result.page_state = page_state

                # Take screenshot
                if screenshot_path:
                    page.screenshot(path=screenshot_path, full_page=True)
                    self._log(f"\nScreenshot saved to: {screenshot_path}")

                # Manual inspection time
                if manual_inspection_time > 0:
                    self._log("\n" + "=" * 80)
                    self._log("BROWSER READY FOR MANUAL INSPECTION")
                    self._log("=" * 80)
                    self._log(
                        f"Browser will stay open for {manual_inspection_time} seconds..."
                    )
                    time.sleep(manual_inspection_time)

                result.analysis_complete = True

            except Exception as e:
                self._log(f"ERROR during analysis: {e}")
                self.errors.append(str(e))

                # Take error screenshot
                try:
                    error_screenshot = (
                        screenshot_path.replace(".png", "_error.png")
                        if screenshot_path
                        else "/tmp/frontend_error_screenshot.png"
                    )
                    page.screenshot(path=error_screenshot)
                    self._log(f"Error screenshot saved to: {error_screenshot}")
                except Exception:
                    pass

            finally:
                browser.close()

        # Populate result
        result.console_logs = self.console_logs
        result.errors = self.errors
        result.network_requests = self.network_requests
        result.network_responses = self.network_responses
        result.issues = self._detect_issues()

        return result

    def _analyze_page_content(self, page: Page) -> Dict[str, Any]:
        """Analyze page content and Vue.js state."""
        state = {}

        self._log("\n" + "=" * 80)
        self._log("PAGE CONTENT ANALYSIS")
        self._log("=" * 80)

        # Basic page info
        state["title"] = page.title()
        state["url"] = page.url
        self._log(f"Page Title: '{state['title']}'")
        self._log(f"Current URL: {state['url']}")

        # Check #app element
        app_element = page.query_selector("#app")
        if app_element:
            app_content = app_element.inner_html()
            state["app_found"] = True
            state["app_content_length"] = len(app_content)
            self._log(f"#app element FOUND with content length: {len(app_content)}")

            if app_content.strip():
                if len(app_content) < 500:
                    self._log(f"#app content:\n{app_content}")
                else:
                    self._log(
                        f"#app content (first 500 chars):\n{app_content[:500]}..."
                    )
            else:
                self._log("WARNING: #app element is empty!")
                state["app_empty"] = True
        else:
            state["app_found"] = False
            self._log("CRITICAL ERROR: #app element NOT FOUND")

        # Vue.js analysis
        self._log("\n" + "=" * 80)
        self._log("VUE.JS FRAMEWORK ANALYSIS")
        self._log("=" * 80)

        try:
            vue_check = page.evaluate(
                """
                () => {
                    return {
                        vue_available: typeof Vue !== 'undefined',
                        vue3_app: typeof window.__VUE__ !== 'undefined',
                        vite_client: typeof window.__vite_plugin_vue_export_helper !== 'undefined',
                        app_instance: typeof window.app !== 'undefined',
                        vue_devtools: typeof window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined',
                        vite_hmr: !!window.__vite__
                    };
                }
            """
            )
            state["vue_checks"] = vue_check
            for check, result in vue_check.items():
                self._log(f"{check}: {result}")
        except Exception as e:
            self._log(f"Error during Vue.js analysis: {e}")
            state["vue_checks"] = {"error": str(e)}

        # Script analysis
        self._log("\n" + "=" * 80)
        self._log("SCRIPT TAGS ANALYSIS")
        self._log("=" * 80)

        scripts = page.query_selector_all("script")
        state["script_count"] = len(scripts)
        self._log(f"Total script tags found: {len(scripts)}")

        for i, script in enumerate(scripts[:10]):  # Show first 10
            src = script.get_attribute("src")
            script_type = script.get_attribute("type")
            if src:
                self._log(f"  Script {i+1}: {src} (type: {script_type})")
            else:
                content = script.inner_text()
                content_preview = (
                    content[:100].replace("\n", " ") if content else "empty"
                )
                self._log(
                    f"  Script {i+1}: inline ({len(content)} chars) - {content_preview}..."
                )

        # Network summary
        self._print_network_summary()

        # Console summary
        self._print_console_summary()

        # Final page state
        try:
            final_state = page.evaluate(
                """
                () => {
                    return {
                        ready_state: document.readyState,
                        scripts_loaded: document.scripts.length,
                        stylesheets_loaded: document.styleSheets.length,
                        body_children: document.body.children.length,
                        app_children: document.getElementById('app') ?
                                      document.getElementById('app').children.length : 0,
                        page_height: document.body.scrollHeight,
                        visible_text: document.body.innerText.length
                    };
                }
            """
            )
            state["final_state"] = final_state
            self._log("\n" + "=" * 80)
            self._log("FINAL PAGE STATE")
            self._log("=" * 80)
            for key, value in final_state.items():
                self._log(f"  {key}: {value}")
        except Exception as e:
            self._log(f"Error getting final state: {e}")

        return state

    def _print_network_summary(self) -> None:
        """Print network requests summary."""
        self._log("\n" + "=" * 80)
        self._log("NETWORK REQUESTS SUMMARY")
        self._log("=" * 80)

        js_requests = [r for r in self.network_requests if r.resource_type == "script"]
        css_requests = [
            r for r in self.network_requests if r.resource_type == "stylesheet"
        ]
        api_requests = [r for r in self.network_requests if "/api/" in r.url]
        failed_responses = [r for r in self.network_responses if not r.ok]

        self._log(f"JavaScript requests: {len(js_requests)}")
        for req in js_requests[:5]:  # Show first 5
            status = next(
                (r.status for r in self.network_responses if r.url == req.url),
                "pending",
            )
            self._log(f"  {req.method} {req.url} -> {status}")

        self._log(f"\nCSS requests: {len(css_requests)}")
        for req in css_requests[:3]:
            status = next(
                (r.status for r in self.network_responses if r.url == req.url),
                "pending",
            )
            self._log(f"  {req.method} {req.url} -> {status}")

        self._log(f"\nAPI requests: {len(api_requests)}")
        for req in api_requests[:5]:
            status = next(
                (r.status for r in self.network_responses if r.url == req.url),
                "pending",
            )
            self._log(f"  {req.method} {req.url} -> {status}")

        self._log(f"\nFailed requests: {len(failed_responses)}")
        for resp in failed_responses:
            self._log(f"  {resp.status} {resp.url}")

    def _print_console_summary(self) -> None:
        """Print console logs summary."""
        self._log("\n" + "=" * 80)
        self._log("CONSOLE LOGS SUMMARY")
        self._log("=" * 80)

        error_logs = [log for log in self.console_logs if log.type == "error"]
        warning_logs = [log for log in self.console_logs if log.type == "warning"]

        self._log(f"Console Errors ({len(error_logs)}):")
        for i, log in enumerate(error_logs[:10]):
            self._log(f"  Error {i+1}: {log.text}")
            if log.location:
                self._log(f"    Location: {log.location}")

        self._log(f"\nConsole Warnings ({len(warning_logs)}):")
        for i, log in enumerate(warning_logs[:5]):
            self._log(f"  Warning {i+1}: {log.text}")

    def _detect_issues(self) -> List[FrontendIssue]:
        """Detect and classify frontend issues from collected data."""
        issues = []

        # Check for console errors
        for log in self.console_logs:
            if log.type == "error":
                severity = IssueSeverity.HIGH
                if "Cannot read" in log.text or "undefined" in log.text.lower():
                    severity = IssueSeverity.CRITICAL

                issues.append(
                    FrontendIssue(
                        type=IssueType.CONSOLE_ERROR,
                        severity=severity,
                        message=log.text,
                        location=str(log.location) if log.location else None,
                        recommendation="Check browser console for stack trace",
                    )
                )

        # Check for failed network requests
        for resp in self.network_responses:
            if not resp.ok:
                severity = (
                    IssueSeverity.CRITICAL if resp.status >= 500 else IssueSeverity.HIGH
                )

                issues.append(
                    FrontendIssue(
                        type=IssueType.NETWORK_ERROR,
                        severity=severity,
                        message=f"HTTP {resp.status}: {resp.url}",
                        recommendation="Check network tab and server logs",
                    )
                )

        # Check for page errors
        for error in self.errors:
            issues.append(
                FrontendIssue(
                    type=IssueType.SCRIPT_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    message=error,
                    recommendation="Check JavaScript console for details",
                )
            )

        return issues


def generate_issue_report(result: AnalysisResult) -> str:
    """
    Generate a formatted issue report from analysis results.

    Args:
        result: AnalysisResult from page analysis

    Returns:
        Formatted markdown report string
    """
    lines = []
    lines.append("# Frontend Analysis Report\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- Console logs captured: {len(result.console_logs)}")
    lines.append(f"- Page errors: {len(result.errors)}")
    lines.append(f"- Network requests: {len(result.network_requests)}")
    lines.append(f"- Issues detected: {len(result.issues)}")
    lines.append(f"- Analysis complete: {result.analysis_complete}\n")

    # Issues by severity
    if result.issues:
        lines.append("## Detected Issues\n")

        critical = [i for i in result.issues if i.severity == IssueSeverity.CRITICAL]
        high = [i for i in result.issues if i.severity == IssueSeverity.HIGH]
        medium = [i for i in result.issues if i.severity == IssueSeverity.MEDIUM]

        if critical:
            lines.append("### Critical\n")
            for issue in critical:
                lines.append(f"- **{issue.type.value}**: {issue.message}")
                if issue.recommendation:
                    lines.append(f"  - Recommendation: {issue.recommendation}")

        if high:
            lines.append("\n### High\n")
            for issue in high:
                lines.append(f"- **{issue.type.value}**: {issue.message}")

        if medium:
            lines.append("\n### Medium\n")
            for issue in medium:
                lines.append(f"- **{issue.type.value}**: {issue.message}")

    # Page state
    if result.page_state:
        lines.append("\n## Page State\n")
        for key, value in result.page_state.items():
            if not isinstance(value, dict):
                lines.append(f"- {key}: {value}")

    return "\n".join(lines)
