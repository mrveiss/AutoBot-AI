# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Playwright request schemas (#6042), split out of `schemas_code.py` (#15802).

The split is not cosmetic. `schemas_code.py` is grandfathered at its #14236
ceiling, so it may not grow -- and documenting what omitting `session_id` does
(#15802 AC2) is text, which is growth. Moving the models here is the ratchet
working as designed: the exemption froze a size, and the way past it is to make
the file smaller rather than to raise the number.

Re-exported from `schemas_code` so both importers -- `api/playwright.py` and
`tests/unit/api/test_playwright_session_isolation.py` -- keep working unchanged.
"""

from pydantic import BaseModel, Field

class PlaywrightSearchRequest(BaseModel):
    query: str
    search_engine: str = "duckduckgo"
    max_results: int = 5


class PlaywrightScreenshotRequest(BaseModel):
    """Embedded-Playwright capture -- NOT the session-scoped browser worker.

    `services/playwright_service.py` has no session concept at all (zero
    references), so this route cannot route a capture into a browser context.
    Use `/worker-screenshot` for that. See #15871.
    """

    url: str
    full_page: bool = True
    wait_timeout: int = 5000
    session_id: str | None = Field(
        None,
        description=(
            "ACCEPTED AND IGNORED by /screenshot: the embedded browser is not "
            "session-partitioned (#15871). The capture happens in the shared "
            "embedded browser regardless. Use /worker-screenshot to capture "
            "inside a specific session's context."
        ),
    )


class PlaywrightNavigateRequest(BaseModel):
    url: str
    wait_until: str = "networkidle"
    timeout: int = 30000
    session_id: str | None = Field(
        None,
        description="Session id for isolated browser-context routing (#11539); omitted uses shared default",
    )


class PlaywrightReloadRequest(BaseModel):
    wait_until: str = "networkidle"
    session_id: str | None = Field(
        None,
        description=(
            "Isolated browser-context routing (#11539). Omitted, the caller joins the "
            "shared default context, which every other unscoped caller also uses."
        ),
    )


class PlaywrightInteractRequest(BaseModel):
    action: str
    x: float | None = None
    y: float | None = None
    deltaX: float = 0
    deltaY: float = 0
    text: str | None = None
    session_id: str | None = Field(
        None,
        description=(
            "Isolated browser-context routing (#11539). Omitted, the caller joins the "
            "shared default context, which every other unscoped caller also uses."
        ),
    )


class PlaywrightSessionRequest(BaseModel):
    """Optional body for worker proxy calls with no other payload (#11539):
    /back, /forward, /worker-screenshot. GET /status takes the same id as a
    query param instead (no request body on GET)."""

    session_id: str | None = Field(
        None,
        description=(
            "Isolated browser-context routing (#11539). Omitted, the caller joins the "
            "shared default context, which every other unscoped caller also uses."
        ),
    )


