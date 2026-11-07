# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Answer an unreadable code-source registry with 503, not a generic 500 (#17982).

``source_storage.get_source`` and ``get_default_source_id`` used to return None
when the registry could not be reached, which every caller read as "no such
source". They raise ``RegistryUnavailable`` now. Handlers that wrap their own
errors (``with_error_handling``) still produce their logged 500; this is the
answer for the ones that do not, including the LLC routes that resolve a
project's source.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def register_registry_handlers(app: FastAPI) -> None:
    """Map ``RegistryUnavailable`` onto a 503 for every router."""
    from api.codebase_analytics.source_storage import RegistryUnavailable

    @app.exception_handler(RegistryUnavailable)
    async def _registry_unavailable(request: Request, exc: RegistryUnavailable) -> JSONResponse:
        logger.error("source registry unavailable on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": "Code source registry unavailable"})
