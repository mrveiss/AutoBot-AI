# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared content-reach backends (browser, etc.) used by multiple source chains."""

from content_reach.backends.browser import BrowserBackend, BrowserSearchBackend

__all__ = ["BrowserBackend", "BrowserSearchBackend"]
