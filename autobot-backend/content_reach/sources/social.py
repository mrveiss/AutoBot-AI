# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Browser-backed social content source (#10932).

Social content (Twitter/X, Instagram, etc.) is fetched via the shared
BrowserBackend — local-first, no cookies, Playwright-rendered page.
No dedicated backend class is needed; BrowserBackend(SourceType.SOCIAL)
carries the correct source_type through its constructor parameter.
"""

from __future__ import annotations

from content_reach.backends.browser import BrowserBackend
from content_reach.chain import ContentSourceChain
from source_attribution import SourceType


def build_social_chain() -> ContentSourceChain:
    """Return the social content chain: a single BrowserBackend with SOCIAL source_type."""
    return ContentSourceChain(
        source="social",
        source_type=SourceType.SOCIAL,
        backends=[BrowserBackend(SourceType.SOCIAL)],
    )
