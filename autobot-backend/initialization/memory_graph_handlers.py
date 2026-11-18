# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Answer a memory-graph name collision with a generic 409 on every route (#18825).

Entity names are globally unique, so ``get_or_create_entity`` refuses to hand back an
entity another owner holds. The refusal must not echo the name (or anything else the
caller or the other owner wrote): the answer is one fixed body, whatever route reached it.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

ENTITY_NAME_IN_USE_DETAIL = "Entity name already in use"


def register_memory_graph_handlers(app: FastAPI) -> None:
    """Map ``EntityNameInUse`` onto a fixed 409 for every router."""
    from autobot_memory_graph.entity_upsert import EntityNameInUse

    @app.exception_handler(EntityNameInUse)
    async def _entity_name_in_use(request: Request, exc: EntityNameInUse) -> JSONResponse:
        logger.warning("entity name collision on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=409, content={"detail": ENTITY_NAME_IN_USE_DETAIL})
