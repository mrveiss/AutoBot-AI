#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Frontend debugging script to run on Browser VM (visual mode with DevTools)
Analyzes the blank page issue on http://10.0.0.2:5173

Issue: #148 - Refactored to use shared frontend_analysis_lib
"""

from frontend_analysis_lib import FrontendDebugger


def analyze_frontend_issue():
    """Analyze the frontend blank page issue using Playwright in visual mode."""

    # Create debugger in visual mode with DevTools
    debugger = FrontendDebugger(
        headless=False,
        devtools=True,
        viewport_width=1280,
        viewport_height=720,
        verbose=True,
    )

    # Run analysis with manual inspection time
    result = debugger.analyze_page(
        url="http://10.0.0.2:5173",
        timeout=15000,
        wait_after_load=3,
        screenshot_path="/tmp/frontend_debug_screenshot.png",
        manual_inspection_time=30,  # Keep browser open for manual debugging
    )

    return {
        "console_logs": [{"type": log.type, "text": log.text, "location": log.location} for log in result.console_logs],
        "errors": result.errors,
        "network_requests": [
            {
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
            }
            for req in result.network_requests
        ],
        "analysis_complete": result.analysis_complete,
    }


if __name__ == "__main__":
    print("Starting Frontend Analysis on Browser VM (Visual Mode)...")
    result = analyze_frontend_issue()
    print("\nAnalysis complete!")
