# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Errors for the chat-sessions API (#12685)."""

from fastapi import HTTPException, status


class OwnershipUnavailableError(HTTPException):
    """Session ownership could not be verified, so no list can be returned.

    503 rather than 500: the request is valid and will succeed once the
    ownership store is reachable again. Returning an unfiltered list instead
    would leak other tenants' sessions, which is why this is an error rather
    than a degraded success.
    """

    def __init__(self, detail: str = "Could not verify session ownership") -> None:
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
