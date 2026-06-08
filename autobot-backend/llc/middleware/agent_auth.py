# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC agent auth middleware (GH#8218).

Intercepts requests to /api/llc/agent/* only.
Validates Bearer token against llc_agent_api_keys via SHA-256 lookup.
Injects request.state.agent_id and request.state.company_id on success.
"""

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import or_, select, update
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from llc.models.api_key import LLCApiKey
from user_management.database import get_async_session_factory

logger = logging.getLogger(__name__)

_AGENT_PREFIX = "/api/llc/agent/"


class LLCAgentAuthMiddleware(BaseHTTPMiddleware):
    """Validate LLC bearer tokens for /api/llc/agent/* routes."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(_AGENT_PREFIX):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Missing bearer token"}, status_code=401)

        raw_key = auth[len("Bearer ") :]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = datetime.now(timezone.utc)

        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(LLCApiKey).where(
                    LLCApiKey.key_hash == key_hash,
                    LLCApiKey.revoked_at.is_(None),
                    # GH#9623: reject expired ephemeral keys (TTL backstop).
                    or_(LLCApiKey.expires_at.is_(None), LLCApiKey.expires_at > now),
                )
            )
            key_record = result.scalar_one_or_none()

        if key_record is None:
            return JSONResponse({"detail": "Invalid or revoked token"}, status_code=401)

        # Update last_used_at (best-effort, non-blocking)
        try:
            async with factory() as session:
                await session.execute(
                    update(LLCApiKey)
                    .where(LLCApiKey.id == key_record.id)
                    .values(last_used_at=datetime.now(timezone.utc))
                )
                await session.commit()
        except Exception:
            logger.debug("Could not update last_used_at for key %s", key_record.id)

        request.state.agent_id = key_record.agent_id
        request.state.company_id = key_record.company_id
        return await call_next(request)
