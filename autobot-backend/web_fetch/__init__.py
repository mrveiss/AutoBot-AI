# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
web_fetch — Unified web fetch/scrape/crawl foundation package.

Issue #7400: Foundation for web research epic (#7396).

Public API::

    from web_fetch import WebFetcher, RenderMode, FetchResult, Frontier, RobotsCache
"""

from web_fetch.fetcher import WebFetcher
from web_fetch.frontier import Frontier
from web_fetch.robots import RobotsCache
from web_fetch.types import (
    ERR_CIRCUIT_OPEN,
    ERR_CONNECTION,
    ERR_HTTP_ERROR,
    ERR_ROBOTS_BLOCKED,
    ERR_SSRF_BLOCKED,
    ERR_TIMEOUT,
    ERR_TOO_LARGE,
    ERR_UNKNOWN,
    FetchResult,
    RenderMode,
)

__all__ = [
    "WebFetcher",
    "RenderMode",
    "FetchResult",
    "Frontier",
    "RobotsCache",
    # Error code constants
    "ERR_SSRF_BLOCKED",
    "ERR_ROBOTS_BLOCKED",
    "ERR_CIRCUIT_OPEN",
    "ERR_HTTP_ERROR",
    "ERR_TIMEOUT",
    "ERR_CONNECTION",
    "ERR_TOO_LARGE",
    "ERR_UNKNOWN",
]
