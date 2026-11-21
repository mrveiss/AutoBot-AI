# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One answer for a stored credential that cannot be read (#17981).

``field_encryption.decrypt_field`` raises ``FieldDecryptionError`` rather than return
an empty value a caller could save back over the credential. Every route that reads
one (company PM settings, the Telegram and WhatsApp settings and webhooks) answers it
here, with the same status and body, instead of each choosing its own 500 or 503.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autobot_shared.field_encryption import FieldDecryptionError
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

CREDENTIAL_UNREADABLE = {
    "code": "CREDENTIAL_UNREADABLE",
    "message": "A stored credential could not be read. Re-enter it, or restore the key it was sealed with.",
}


def register_credential_handlers(app: FastAPI) -> None:
    """Map ``FieldDecryptionError`` onto one 503 for every router."""

    @app.exception_handler(FieldDecryptionError)
    async def _credential_unreadable(request: Request, exc: FieldDecryptionError) -> JSONResponse:
        # The message names where the value is stored, never the value.
        logger.error("stored credential unreadable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": CREDENTIAL_UNREADABLE})
