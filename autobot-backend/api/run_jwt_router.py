# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Run JWT refresh endpoint (SEC-2 Phase 3, #6473).

POST /runs/{run_id}/jwt/refresh — renew a run-scoped JWT before it expires.
The caller must present the current (not-yet-expired, not-revoked) JWT as a
Bearer token.  The old token is atomically revoked and a fresh one returned.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError
from autobot_shared.logging_manager import get_logger
from services.run_jwt import JWTRefreshConflictError, _ttl, refresh_run_jwt

logger = get_logger(__name__)

router = APIRouter()


class RunJwtRefreshResponse(BaseModel):
    token: str
    expires_in: int


def _bearer_token(request: Request) -> str:
    """Extract the Bearer token from Authorization header or raise 401."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.split(" ", 1)[1]


@router.post(
    "/runs/{run_id}/jwt/refresh",
    response_model=RunJwtRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh a run-scoped JWT",
    tags=["security", "run-jwt"],
)
async def refresh_run_jwt_endpoint(run_id: str, request: Request) -> RunJwtRefreshResponse:
    """Renew a run-scoped JWT before it expires.

    The caller presents the current JWT as ``Authorization: Bearer <token>``.
    The run_id in the URL must match the ``run_id`` claim embedded in the token
    to prevent cross-run token reuse.

    On success the old token is revoked and a new one with a fresh TTL is
    returned.  Returns 401 if the token is expired, revoked, or otherwise
    invalid.
    """
    token = _bearer_token(request)
    try:
        new_token = await refresh_run_jwt(token, run_id)
    except JWTRefreshConflictError as exc:
        logger.info("run_jwt: refresh conflict — concurrent refresh for run_id=%s: %s", run_id, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent refresh detected — use the token from the winning request",
        ) from exc
    except JWTExpiredError as exc:
        logger.info("run_jwt: refresh denied — expired token for run_id=%s: %s", run_id, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT has expired and cannot be refreshed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except JWTDecodeError as exc:
        logger.info("run_jwt: refresh denied — invalid/revoked token for run_id=%s: %s", run_id, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT is invalid or has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return RunJwtRefreshResponse(token=new_token, expires_in=_ttl())
