#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Test script to capture frontend console errors using Playwright"""

import asyncio
import sys

from playwright.async_api import async_playwright

from src.constants import ServiceURLs


async def capture_console_errors():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect console messages
        console_messages = []
        page.on(
            "console",
            lambda msg: console_messages.append(
                {
                    "type": msg.type,
                    "text": msg.text,
                    "location": f"{msg.location['url']}:{msg.location.get('lineNumber', 0)}",
                }
            ),
        )

        # Collect page errors
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # Collect network failures
        failed_requests = []

        def on_request_failed(request):
            failed_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "failure": request.failure,
                }
            )

        page.on("requestfailed", on_request_failed)

        # Navigate to the page
        print("Loading AutoBot frontend...")
        try:
            response = await page.goto(
                ServiceURLs.FRONTEND_LOCAL, wait_until="networkidle", timeout=30000
            )
            print(f"Page loaded with status: {response.status}")
        except Exception as e:
            print(f"Failed to load page: {e}")

        # Wait for Vue to initialize
        await page.wait_for_timeout(3000)

        # Try to get Vue DevTools info if available
        try:
            vue_info = await page.evaluate(
                """
                () => {
                    if (window.__VUE__) {
                        return 'Vue 3 detected';
                    } else if (window.Vue) {
                        return 'Vue 2 detected';
                    }
                    return 'Vue not detected';
                }
            """
            )
            print(f"Vue status: {vue_info}")
        except Exception:
            print("Could not check Vue status")

        # Print results
        print("\n=== CONSOLE ERRORS AND WARNINGS ===")
        error_count = 0
        warning_count = 0
        for msg in console_messages:
            if msg["type"] in ["error", "warning"]:
                print(f"[{msg['type'].upper()}] {msg['text']}")
                print(f"  Location: {msg['location']}")
                if msg["type"] == "error":
                    error_count += 1
                else:
                    warning_count += 1

        print(f"\nTotal errors: {error_count}")
        print(f"Total warnings: {warning_count}")

        print("\n=== PAGE ERRORS ===")
        for err in page_errors:
            print(f"ERROR: {err}")

        print("\n=== FAILED NETWORK REQUESTS ===")
        for req in failed_requests:
            print(f"FAILED: {req['method']} {req['url']}")
            print(f"  Reason: {req['failure']}")

        # Check for specific Vue components
        print("\n=== CHECKING VUE COMPONENTS ===")
        components_check = await page.evaluate(
            """
            () => {
                const checks = [];

                // Check if main app is mounted
                if (document.getElementById('app')) {
                    checks.push('App div found');
                    if (document.getElementById('app').__vue_app__) {
                        checks.push('Vue app mounted');
                    } else {
                        checks.push('ERROR: Vue app NOT mounted');
                    }
                }

                // Check for error indicators
                const errors = document.querySelectorAll('.error, .Error, [class*="error"]');
                if (errors.length > 0) {
                    checks.push(`Found ${errors.length} error elements in DOM`);
                }

                return checks;
            }
        """
        )

        for check in components_check:
            print(f"  {check}")

        await browser.close()

        # Return exit code based on errors
        return 1 if error_count > 0 or len(page_errors) > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(capture_console_errors())
    sys.exit(exit_code)
