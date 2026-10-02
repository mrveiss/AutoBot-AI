# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-user and per-conversation rate limits on sending a chat message (#16857).

``user_rate_limiter`` and ``conversation_rate_limiter`` were built (#4460) and
never acquired against, so no per-user or per-conversation request cap ran on
the chat surface. Owner decision on #16857: enforce both on the **message-send
endpoints only**. A route-wide cap would also throttle the UI's own polling and
reconnects, which is the control working as specified and breaking the product.

Attached as a router-level dependency of ``api.chat`` through
``initialization.router_registry.route_dependencies``, so ``api/chat.py`` (at its
file-size ceiling) is not edited. It acts only on POSTs to the endpoints named
in ``SEND_ENDPOINTS``; every other chat route passes through untouched.

Limits are the shared ``authenticated`` tier defaults (``autobot_shared.rate_limiter``).
A Redis outage fails open there by design, so this cannot hard-block chat.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from user_management.middleware.rate_limit import user_rate_limiter
from utils.conversation_rate_limiter import conversation_rate_limiter

logger = get_logger(__name__)

#: Endpoint functions in ``api.chat`` that send a message to the model. Matched by
#: the routed endpoint's name, so a renamed handler drops out loudly in the test
#: that pins this set against the router, not silently at runtime.
SEND_ENDPOINTS = frozenset(
    {
        "send_message",
        "stream_message",
        "send_chat_message_by_id",
        "resume_chat_graph",
        "send_direct_chat_response",
        "chat_ai_stack",
        "stream_ai_stack_chat",
    }
)


async def _conversation_id(request: Request) -> str | None:
    """The conversation a send targets: path ``chat_id``, else the JSON body's id."""
    if request.path_params.get("chat_id"):
        return str(request.path_params["chat_id"])
    try:
        body: Any = await request.json()
    except ValueError:  # json.JSONDecodeError: an empty or non-JSON body names no conversation
        return None
    if not isinstance(body, dict):
        return None
    nested = body.get("message")
    found = body.get("chat_id") or body.get("session_id")
    if not found and isinstance(nested, dict):
        found = nested.get("session_id")
    return str(found) if found else None


async def _refuse_if_limited(limiter, key: str, scope: str) -> None:
    if await limiter.acquire(key):
        return
    retry_after = await limiter.get_retry_after_seconds(key)
    logger.info("chat send refused: %s rate limit reached", scope)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many messages for this {scope}; retry in {retry_after}s",
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_chat_send_rate_limits(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Refuse a chat send with 429 once the user's or the conversation's limit is reached."""
    endpoint = request.scope.get("endpoint")
    if request.method != "POST" or getattr(endpoint, "__name__", "") not in SEND_ENDPOINTS:
        return
    user_id = (current_user or {}).get("user_id")
    if user_id:
        await _refuse_if_limited(user_rate_limiter, str(user_id), "user")
    conversation_id = await _conversation_id(request)
    if conversation_id:
        await _refuse_if_limited(conversation_rate_limiter, conversation_id, "conversation")
