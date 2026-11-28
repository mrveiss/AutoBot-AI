# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Observed-headroom reads for pre-dispatch routing (Issue #15028).

Consumes ``quota_headroom.QuotaHeadroomStore`` (#15026): decides whether a
provider's account is so close to a rate-limit window that routing it a
request is a wasted round-trip, and returns the evidence.

Contract:

- No data is never "exhausted". An absent or stale observation (older than
  ``_MAX_AGE_SECONDS``) is ignored, so a stale reading can neither block a
  provider forever nor widen a limit.
- A window the provider has already reset (``resets_at`` in the past) is
  ignored.
- Every failure of the store reads as "no data": routing falls back to the
  reactive path, it never fails because headroom could not be read.
"""

from __future__ import annotations

import time
from typing import Optional

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger

from .quota_headroom import QuotaHeadroomEntry, get_quota_headroom_store

logger = get_logger(__name__)

# Remaining fraction of a window at or below which the window counts as
# near-exhausted. Env-backed; never inlined at a call site.
_HEADROOM_FLOOR: float = env_float("AUTOBOT_LLM_HEADROOM_FLOOR", 0.05)

# An observation older than this carries no weight in routing or limit sizing.
_MAX_AGE_SECONDS: float = env_float("AUTOBOT_LLM_HEADROOM_MAX_AGE_SECONDS", 120.0)


def is_fresh(entry: QuotaHeadroomEntry, now: Optional[float] = None) -> bool:
    """True while *entry* is recent enough to act on."""
    now = time.time() if now is None else now
    return 0.0 <= now - entry.observed_at <= _MAX_AGE_SECONDS


def entry_is_exhausted(entry: QuotaHeadroomEntry, now: Optional[float] = None) -> bool:
    """True when *entry* is fresh, not yet reset, and at or under the floor."""
    now = time.time() if now is None else now
    if not is_fresh(entry, now) or entry.remaining is None:
        return False
    if entry.resets_at is not None and entry.resets_at <= now:
        return False
    if entry.remaining <= 0:
        return True
    return entry.limit is not None and entry.limit > 0 and entry.remaining / entry.limit <= _HEADROOM_FLOOR


async def exhausted_window(provider: str) -> Optional[QuotaHeadroomEntry]:
    """The first near-exhausted window observed for *provider*, or None."""
    try:
        entries = await get_quota_headroom_store().all_entries(provider)
    except Exception:
        logger.debug("headroom: store unreadable for %s -- treating as no data", provider, exc_info=True)
        return None
    now = time.time()
    return next((e for e in entries if entry_is_exhausted(e, now)), None)


__all__ = ["entry_is_exhausted", "exhausted_window", "is_fresh"]
