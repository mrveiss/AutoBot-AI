# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Web Pipeline Engine — Phase 1 building blocks.

Provides:
- XHRInterceptor: intercepts fetch() and XMLHttpRequest calls in a Playwright page
- AccessibilitySnapshot: captures and queries the accessibility tree of a Playwright page
"""

from services.web_pipeline.interceptor import InterceptedRequest, XHRInterceptor
from services.web_pipeline.snapshot import AccessibilityNode, AccessibilitySnapshot

__all__ = [
    "XHRInterceptor",
    "InterceptedRequest",
    "AccessibilitySnapshot",
    "AccessibilityNode",
]
