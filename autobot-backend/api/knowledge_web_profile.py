# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HTTP mapping of the ingest-profile seam for the knowledge web routes (#18826).

``POST /knowledge/crawl`` and ``POST /knowledge/scrape`` both accept a ``profile``.
The request model already rejects an unknown value (422); this turns a known but
unimplemented one into a 501 before any page is fetched, instead of letting it
surface later as a generic crawl or fetch failure.
"""

from fastapi import HTTPException

from web_fetch.profile import IngestProfile, ProfileNotImplementedError, require_implemented


def require_profile_or_501(profile: IngestProfile) -> IngestProfile:
    """Return *profile* when implemented; raise ``HTTPException(501)`` otherwise."""
    try:
        return require_implemented(profile)
    except ProfileNotImplementedError as exc:
        raise HTTPException(
            status_code=501,
            detail={"success": False, "error_code": "profile_not_implemented", "message": str(exc)},
        ) from exc
