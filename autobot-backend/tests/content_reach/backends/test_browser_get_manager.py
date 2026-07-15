# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Smoke test: _get_manager() actually resolves to the ResearchBrowserManager singleton (#11078).

This test exercises the real import path so the line is covered and the pragma
no-cover comment has been removed from browser.py.
"""

from __future__ import annotations


def test_get_manager_returns_research_browser_manager_singleton():
    """_get_manager() returns the ResearchBrowserManager singleton (import path works)."""
    from content_reach.backends.browser import _get_manager
    from research_browser_manager import ResearchBrowserManager, get_research_browser_manager

    manager = _get_manager()

    # Must be the same singleton returned by the canonical accessor.
    assert manager is get_research_browser_manager()
    assert isinstance(manager, ResearchBrowserManager)
