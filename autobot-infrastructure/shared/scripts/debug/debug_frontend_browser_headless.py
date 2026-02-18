#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Frontend debugging script to run on Browser VM (headless mode)
Analyzes the blank page issue on http://172.16.168.21:5173

Issue: #148 - Refactored to use shared frontend_analysis_lib
"""

from frontend_analysis_lib import FrontendDebugger


def analyze_frontend_issue():
    """Analyze the frontend blank page issue using Playwright in headless mode."""

    # Create debugger in headless mode
    debugger = FrontendDebugger(
        headless=True,
        devtools=False,
        viewport_width=1280,
        viewport_height=720,
        verbose=True,
    )

    # Run analysis
    result = debugger.analyze_page(
        url="http://172.16.168.21:5173",
        timeout=20000,
        wait_after_load=5,
        screenshot_path="/tmp/frontend_debug_screenshot.png",
        manual_inspection_time=0,  # No manual inspection in headless mode
    )

    return {
        "console_logs": [
            {"type": log.type, "text": log.text, "location": log.location}
            for log in result.console_logs
        ],
        "errors": result.errors,
        "network_requests": [
            {
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
            }
            for req in result.network_requests
        ],
        "network_responses": [
            {
                "url": resp.url,
                "status": resp.status,
                "ok": resp.ok,
            }
            for resp in result.network_responses
        ],
        "analysis_complete": result.analysis_complete,
    }


if __name__ == "__main__":
    print("Starting Headless Frontend Analysis on Browser VM...")
    print("Target: http://172.16.168.21:5173")
    print("=" * 80)

    try:
        result = analyze_frontend_issue()
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE!")
        print(f"Console logs captured: {len(result['console_logs'])}")
        print(f"Errors captured: {len(result['errors'])}")
        print(f"Network requests: {len(result['network_requests'])}")
        print("=" * 80)
    except Exception as e:
        print(f"Failed to complete analysis: {e}")
