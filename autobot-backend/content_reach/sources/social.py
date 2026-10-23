# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Browser-backed social content source (#10932).

Social content (Twitter/X, Instagram, etc.) is fetched via the shared
BrowserContentBackend — local-first, no cookies, Playwright-rendered page.
No dedicated backend class is needed; BrowserContentBackend(SourceKind.SOCIAL)
carries the correct source_type through its constructor parameter.
"""

from __future__ import annotations

from content_reach.backends.browser import BrowserContentBackend
from content_reach.chain import ContentSourceChain
from source_attribution import SourceKind


def build_social_chain() -> ContentSourceChain:
    """Return the social content chain: a single BrowserContentBackend with SOCIAL source_type."""
    return ContentSourceChain(
        source="social",
        source_type=SourceKind.SOCIAL,
        backends=[BrowserContentBackend(SourceKind.SOCIAL)],
    )
