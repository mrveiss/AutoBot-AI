# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-user rate limit on sending a chat message (#16857).

``user_rate_limiter`` was built (#4460) and never acquired against, so no
per-user request cap ran on the chat surface. Owner decision on #16857: enforce
it on the **message-send endpoints only**. A route-wide cap would also throttle
the UI's own polling and reconnects, which is the control working as specified
and breaking the product.

A per-*conversation* limit was built and then deliberately left off: keyed by a
conversation id taken from the request, it runs before the endpoint proves the
caller owns that conversation, so any user could exhaust someone else's
conversation and lock its owner out. The per-user limit already bounds how fast
any one caller can send to any conversation. See ``utils.conversation_rate_limiter``.

Attached as a router-level dependency of ``api.chat`` through
``initialization.router_registry.route_dependencies``, so ``api/chat.py`` (at its
file-size ceiling) is not edited. It returns immediately for anything but a POST
to an endpoint named in ``SEND_ENDPOINTS``, before resolving the caller, so no
other chat route gains an authentication requirement it did not already have.

Limits are the shared ``authenticated`` tier (``autobot_shared.rate_limiter``).
A Redis outage fails open there by design, so this cannot hard-block chat.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from user_management.middleware.rate_limit import user_rate_limiter

logger = get_logger(__name__)

#: Endpoint functions in ``api.chat`` that send a message to the model. Matched by
#: the routed endpoint's name; the test pins this set against ``api/chat.py`` so a
#: renamed handler fails CI instead of silently escaping the limit.
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


def _is_send(request: Request) -> bool:
    endpoint = request.scope.get("endpoint")
    return request.method == "POST" and getattr(endpoint, "__name__", "") in SEND_ENDPOINTS


async def enforce_chat_send_rate_limit(request: Request) -> None:
    """Refuse a chat send with 429 once the caller's per-user limit is reached.

    A caller with no ``user_id`` -- the internal-service identity -- is not a user
    and is not counted.
    """
    if not _is_send(request):
        return
    user_id = (await get_current_user(request) or {}).get("user_id")
    if not user_id:
        return
    key = str(user_id)
    if await user_rate_limiter.acquire(key):
        return
    retry_after = await user_rate_limiter.get_retry_after_seconds(key)
    logger.info("chat send refused: per-user rate limit reached")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many messages; retry in {retry_after}s",
        headers={"Retry-After": str(retry_after)},
    )
