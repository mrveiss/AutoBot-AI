# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may act on an agent-terminal session (#17052, #17053, #17057).

An agent-terminal session runs commands on a host for one user: its verified
creator, or, for a session a chat drives, that conversation's recorded owner
(``AgentTerminalSession.owner``, a username). Every route that reads a session,
drives it or decides for it is limited to that owner or an admin. A session with
no recorded owner is admin-only. A missing session, an unowned one and someone
else's all answer the same 404, so a response never confirms who owns what
(THREAT_MODEL.md section 2).

Decisions -- approving or denying a command, taking control, choosing a host --
also need a person signed in interactively (#17042).

Why these stay outside the consolidated approval service (#17043): a command
approval is a synchronous gate on a live session -- the agent is blocked until
the session's owner answers, and the answer is consumed at once -- not a
durable record with a lifecycle (revision, comments, task links) that any
authorised reviewer in a tenant may decide. What the two share is the rule,
and it is shared by code: the same interactive-human predicate and the verified
caller as the recorded approver.

This module also holds the process-wide ``AgentTerminalService`` singleton, so
the REST routes, the host-selection sub-router, the WebSocket approval path and
the chat workflow all act on one instance.
"""

import threading
from typing import Any, Iterable, Mapping, Optional

from fastapi import Depends, HTTPException

from api.user_management.human_decider import require_interactive_human
from auth_middleware import get_current_user
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.error_constants import ERR_SESSION_NOT_FOUND
from services.agent_terminal import AgentTerminalService
from services.agent_terminal.conversation_owner import ConversationNotOwnedError
from services.agent_terminal.redis_usability import usable_redis

logger = get_logger(__name__)

# CRITICAL: one instance for every caller, or sessions vanish between them.
_agent_terminal_service_instance: AgentTerminalService | None = None
_agent_terminal_service_lock = threading.Lock()


def ensure_agent_terminal_service(**kwargs: Any) -> AgentTerminalService:
    """The singleton, built from ``kwargs`` by whichever caller gets there first (thread-safe).

    A later caller's ``redis_client`` is ADOPTED if the instance has none usable
    (#17436). Whoever arrives first wins, and `chat_workflow/tool_handler.py`
    calls this with no ``redis_client`` at all -- so on that ordering the
    singleton was built with ``None`` and every later client, however correctly
    awaited, was discarded. Fixing the await alone would have left this PR inert
    on exactly that path.

    Only an upgrade: an unusable client is never installed, and a working one is
    never swapped out from under in-flight callers.
    """
    global _agent_terminal_service_instance
    if _agent_terminal_service_instance is None:
        with _agent_terminal_service_lock:
            if _agent_terminal_service_instance is None:
                logger.info("Initializing AgentTerminalService singleton")
                _agent_terminal_service_instance = AgentTerminalService(**kwargs)
                return _agent_terminal_service_instance
    _adopt_redis_client(_agent_terminal_service_instance, kwargs.get("redis_client"))
    return _agent_terminal_service_instance


def _adopt_redis_client(service: AgentTerminalService, candidate: Any) -> None:
    """Install *candidate* on an existing singleton that has no usable client.

    Reaches into the two collaborators that were handed the client at
    construction, because the service does not own a setter and adding one to a
    file already at its size ceiling is a separate change.
    """
    if candidate is None or not usable_redis(candidate) or usable_redis(service.redis_client):
        return
    with _agent_terminal_service_lock:
        if usable_redis(service.redis_client):
            return
        logger.info("Adopting a usable Redis client onto the existing AgentTerminalService")
        service.redis_client = candidate
        service.session_manager.redis_client = candidate
        if getattr(service, "terminal_logger", None) is not None:
            service.terminal_logger.redis_client = candidate


def get_agent_terminal_service(redis_client=Depends(get_redis_client)) -> AgentTerminalService:
    """FastAPI dependency: the singleton AgentTerminalService."""
    return ensure_agent_terminal_service(redis_client=redis_client)


def may_act_for(owner: Optional[str], user: Mapping[str, Any]) -> bool:
    """True for an admin or for ``owner`` itself; nobody else acts for an unowned record."""
    if is_admin_role(user.get("role")):
        return True
    return bool(owner) and owner == user.get("username")


def may_access_session(session: Any, user: Mapping[str, Any]) -> bool:
    """True for an admin or the session's recorded owner; never for an unowned session."""
    return may_act_for(getattr(session, "owner", None), user)


async def require_session_access(
    service: AgentTerminalService, session_id: Optional[str], user: Mapping[str, Any]
) -> Any:
    """The session, or the same 404 whether it is missing, unowned or someone else's."""
    session = await service.get_session(session_id) if session_id else None
    if session is None or not may_access_session(session, user):
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)
    return session


async def create_session_for_caller(service: AgentTerminalService, user: Mapping[str, Any], **fields: Any) -> Any:
    """Create a session owned by the caller (#14989, #16975); 404 for a conversation they do not own (#17422).

    ``conversation_id`` comes from the request body, so it is the one input here
    the caller controls: the service refuses it unless the caller owns it, and the
    refusal answers the same 404 as a missing session.
    """
    try:
        return await service.create_session(owner=user.get("username"), tenant_id=user.get("org_id"), **fields)
    except ConversationNotOwnedError:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND) from None


async def session_owner(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service: AgentTerminalService = Depends(get_agent_terminal_service),
) -> dict:
    """Dependency: the caller, once they may act on ``session_id`` (path or query)."""
    await require_session_access(service, session_id, current_user)
    return current_user


async def session_decider(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service: AgentTerminalService = Depends(get_agent_terminal_service),
) -> dict:
    """Dependency: a person, signed in interactively, who may act on ``session_id``."""
    require_interactive_human(current_user, f"agent terminal decision on session {session_id}")
    await require_session_access(service, session_id, current_user)
    return current_user


def verified_actor(user: Mapping[str, Any], claimed: Optional[str]) -> Optional[str]:
    """The verified caller's username; a client-claimed ``user_id`` is ignored and logged."""
    if claimed:
        logger.warning(
            "Ignoring client-supplied user_id=%s; recording the verified caller %s", claimed, user.get("username")
        )
    return user.get("username")


def session_for_terminal_id(sessions: Iterable[Any], terminal_session_id: Optional[str]) -> Any:
    """The session a command ran in: matched by its PTY id, or its own id when it has none."""
    if not terminal_session_id:
        return None
    for session in sessions:
        if terminal_session_id in (session.pty_session_id, session.session_id):
            return session
    return None


async def approve_over_websocket(data: Mapping[str, Any], user: Mapping[str, Any]) -> dict:
    """The WebSocket twin of ``POST /sessions/{id}/approve`` (#17052): same person, owner and approver."""
    session_id = data.get("terminal_session_id")
    require_interactive_human(user, f"agent terminal decision on session {session_id}")
    service = get_agent_terminal_service(redis_client=get_redis_client())
    await require_session_access(service, session_id, user)
    return await service.approve_command(
        session_id=session_id,
        approved=data.get("approved", False),
        user_id=verified_actor(user, data.get("user_id")),
    )
