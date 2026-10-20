# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE answer for "the revocation store could not answer" (#18892).

Both backends fail CLOSED when a revocation check (the jti denylist, the
password epoch) reaches no verdict (#16387, #16411): the token is never
accepted. What differs from "this token is bad" is what the CLIENT must do. A
401 tells it the credential is dead, so it clears a perfectly valid session and
redirects to login. A 503 + ``Retry-After`` tells it the server could not
decide, so it keeps the session and retries. 401 stays for an invalid,
expired or revoked token.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from autobot_shared.env_utils import env_int_clamped

#: Stable machine-readable detail clients match on; never reworded.
REVOCATION_UNAVAILABLE_DETAIL = "revocation_check_unavailable"

_RETRY_AFTER_ENV = "AUTOBOT_REVOCATION_RETRY_AFTER_SECONDS"
# The registry's declared default and range (env_registry_slm.py). Not read from REGISTRY at import:
# that module pulls in the whole registry tree, which config-mocking harnesses cannot load. A test
# pins these to the registry spec so the two cannot drift.
_RETRY_AFTER_DEFAULT, _RETRY_AFTER_RANGE = 5, (1, 300)


def _read_retry_after_seconds() -> int:
    """Read the interval, clamped (and logged when clamped) to the registry's declared range."""
    low, high = _RETRY_AFTER_RANGE
    return env_int_clamped(_RETRY_AFTER_ENV, _RETRY_AFTER_DEFAULT, min_v=low, max_v=high)


#: Seconds a client is told to wait before retrying (``Retry-After``).
REVOCATION_RETRY_AFTER_SECONDS: int = _read_retry_after_seconds()


def revocation_unavailable_error() -> HTTPException:
    """The 503 to raise when a revocation check cannot run. The caller denies the token."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=REVOCATION_UNAVAILABLE_DETAIL,
        headers={"Retry-After": str(max(1, REVOCATION_RETRY_AFTER_SECONDS))},
    )
