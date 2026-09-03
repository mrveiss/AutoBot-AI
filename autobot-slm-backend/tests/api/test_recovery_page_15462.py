# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15462 — the recovery page must actually be servable, and dependency-free.

The route lives on ``health_router`` (``api/health.py``), not a dedicated
router — that router already owns "is the served frontend broken"
(``frontend_bundle_status``, wired into ``/api/health``) and is already
mounted ungated in ``main.py``, so the recovery surface for that exact
condition belongs beside the probe that detects it (#15462 review) rather
than a second router main.py and the #14339 ungated-router registry both
have to track.

This file proves the route resolves to a real, self-contained file: no
external <script src=, no CDN import, and the specific relative endpoint
paths the page's inline JS calls (``health``, ``auth/login``,
``code-sync/self-update``) actually exist as strings in it, so a typo there
fails a test instead of only being noticed by a locked-out operator.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _health_import import import_health  # noqa: E402

_health = import_health()
_RECOVERY_PAGE = _health._RECOVERY_PAGE
recovery_page = _health.recovery_page


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_recovery_page_file_exists_on_disk() -> None:
    assert _RECOVERY_PAGE.is_file()


def test_recovery_page_route_serves_the_static_file() -> None:
    response = _run(recovery_page())
    assert Path(response.path) == _RECOVERY_PAGE
    assert response.media_type == "text/html"


def test_recovery_page_has_no_external_script_or_cdn_dependency() -> None:
    """Dependency-free means dependency-free: no <script src=, no CDN host."""
    html = _RECOVERY_PAGE.read_text(encoding="utf-8")

    assert "<script src=" not in html
    assert "cdn." not in html
    assert "unpkg.com" not in html
    assert "jsdelivr" not in html


def test_recovery_page_calls_the_expected_backend_endpoints() -> None:
    html = _RECOVERY_PAGE.read_text(encoding="utf-8")

    assert 'fetch("health")' in html
    assert 'fetch("auth/login"' in html
    assert 'fetch("code-sync/self-update"' in html
