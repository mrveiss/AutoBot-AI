# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Prometheus scrape token gate for ``/api/metrics/prometheus`` (#16375).

Prometheus has no session, so the scrape cannot use ``get_current_user``. The
owner ruling on #16375 is a dedicated, read-only scrape token instead:

* **Generated and stored** by the SLM in its ``SystemSecret`` store under
  ``prometheus_scrape_token`` (seeded once at SLM startup, mirrored to the
  System vault), and handed to deploys through ``fetch_deploy_secrets``.
* **Delivered** to this backend as ``AUTOBOT_PROMETHEUS_SCRAPE_TOKEN`` in
  ``backend.env``, and to Prometheus as a ``bearer_token_file`` the monitoring
  role writes from the same secret.
* **Verified here** on every scrape, in constant time.

The token authorises reading metrics and nothing else: no other route accepts
it, and it maps to no user. An unset token refuses every scrape -- a missing
credential must never read as an open endpoint.
"""

import secrets

from fastapi import Header, HTTPException, status

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config

logger = get_logger(__name__)

_BEARER_PREFIX = "bearer "


def _presented_token(authorization: str | None) -> str:
    """The credential after ``Bearer``, or ``""`` when the header has another shape."""
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        return ""
    return authorization[len(_BEARER_PREFIX) :].strip()


def scrape_token_matches(presented: str) -> bool:
    """Constant-time compare against the configured token; unset never matches."""
    expected = ssot_config.misc.prometheus_scrape_token
    if not expected or not presented:
        return False
    return secrets.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def require_scrape_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: admit only a request carrying the scrape token.

    Refusals log that a scrape was refused and why in one word, never the value
    presented -- a wrong token is often a right token for something else.
    """
    if scrape_token_matches(_presented_token(authorization)):
        return
    logger.warning("Prometheus scrape refused: %s", "missing" if not authorization else "invalid")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Prometheus scrape token required",
        headers={"WWW-Authenticate": "Bearer"},
    )
