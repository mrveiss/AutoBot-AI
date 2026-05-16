# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Natural Language Database API (Issue #723)

FastAPI router providing endpoints for natural language to SQL query
capabilities via the Vanna.ai integration.

Endpoints:
- POST /nl-database/query         - Execute NL query against a database
- GET  /nl-database/schema        - Get info about trained database schemas
- POST /nl-database/train         - Train on an external database schema
- GET  /nl-database/history       - Retrieve query history
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.schemas_agent import NLDatabaseSchemaResponse
from api.schemas_knowledge import (
    NLQueryRequest,
    NLQueryResponse,
    TrainRequest,
    TrainResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.nl_database_service import get_nl_database_service

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_db_url(db_secret_id: str | None, request: Request) -> str | None:
    """
    Resolve a database URL from a secret ID.

    Helper for query and train endpoints (Issue #723).

    Args:
        db_secret_id: Secret ID from the secrets manager, or None for local DB
        request: FastAPI request (used to access the secrets service)

    Returns:
        Database URL string, or None if using local DB
    """
    if db_secret_id is None:
        return None

    try:
        from api.secrets import get_secrets_manager

        manager = get_secrets_manager()
        secret = await manager.get_secret(db_secret_id, user_id=None)
        if secret is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Secret '{db_secret_id}' not found",
            )
        if secret.get("type") != "database_url":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Secret '{db_secret_id}' is not a database_url secret",
            )
        return secret["value"]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to resolve database secret: %s", exc)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve database credentials",
        ) from exc


def _extract_user_id(request: Request) -> str | None:
    """
    Extract user ID from the request state if available.

    Helper for audit logging in query endpoints (Issue #723).

    Args:
        request: FastAPI request object

    Returns:
        User ID string or None
    """
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        return user.get("id") or user.get("user_id")
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/query",
    response_model=NLQueryResponse,
    summary="Execute natural language database query",
    description=(
        "Converts a natural language question into SQL using Vanna.ai "
        "and executes it against the specified database. "
        "Only read-only queries (SELECT) are permitted."
    ),
    tags=["nl-database"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="nl_query",
    error_code_prefix="NL_DATABASE",
)
async def nl_query(
    body: NLQueryRequest,
    request: Request,
    _auth=Depends(get_current_user),
) -> NLQueryResponse:
    """Execute a natural language query against a database."""
    service = get_nl_database_service()
    user_id = _extract_user_id(request)

    db_url = await _resolve_db_url(body.db_secret_id, request)

    result = await service.query(
        question=body.question,
        db_url=db_url,
        db_id=body.db_id,
        user_id=user_id,
    )

    if "error" in result and result.get("sql") is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["error"],
        )

    return NLQueryResponse(**result)


@router.get(
    "/schema",
    summary="Get trained database schema information",
    description="Returns metadata about databases the NL service has been trained on.",
    tags=["nl-database"],
    response_model=NLDatabaseSchemaResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_schema",
    error_code_prefix="NL_DATABASE",
)
async def get_schema(
    _auth=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get information about trained database schemas."""
    service = get_nl_database_service()
    return await service.get_schema_info()


@router.post(
    "/train",
    response_model=TrainResponse,
    summary="Train on external database schema",
    description=(
        "Fetches the schema from an external database (via secrets manager) "
        "and trains the NL service for improved SQL generation."
    ),
    tags=["nl-database"],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="train_on_db",
    error_code_prefix="NL_DATABASE",
)
async def train_on_db(
    body: TrainRequest,
    request: Request,
    _auth=Depends(get_current_user),
) -> TrainResponse:
    """Train the NL service on an external database schema."""
    service = get_nl_database_service()

    db_url = await _resolve_db_url(body.db_secret_id, request)
    if db_url is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="db_secret_id is required for training on external databases",
        )

    result = await service.train_on_external_db(
        db_url=db_url,
        db_id=body.db_id,
        db_type=body.db_type,
    )
    return TrainResponse(**result)


@router.get(
    "/history",
    summary="Get query history",
    description="Retrieve the history of natural language queries executed by the current user.",
    tags=["nl-database"],
    response_model=List[Dict[str, Any]],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_history",
    error_code_prefix="NL_DATABASE",
)
async def get_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500, description="Max entries to return"),
    _auth=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve query history for the current user."""
    service = get_nl_database_service()
    user_id = _extract_user_id(request)
    return await service.get_query_history(user_id=user_id, limit=limit)
