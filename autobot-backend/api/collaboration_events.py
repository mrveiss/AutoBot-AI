# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session Collaboration Event History & Invitations API

#16460: read-side surface for the durable collaboration event history
(GET .../events, the backfill counterpart to the live broadcast persisted
by api/collaboration.py + websocket/presence.py), plus the invitation
list/respond endpoints. Split out of api/collaboration.py to stay under
the per-file line-count guard (#5060) -- these share that module's
permission helpers but are a separable read/respond concern from the
original invite/remove/participants/presence/share-secret surface.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.collaboration import _ensure_permission, _get_session_collab
from api.schemas_collaboration import (
    CollabEventResponse,
    InvitationRespondRequest,
    InvitationRespondResponse,
    MyInvitationsResponse,
    PendingInvitationResponse,
    SessionEventsResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import parse_utc_iso
from models.collaboration_event import CollaborationEvent
from models.session_collaboration import PermissionLevel, SessionCollaboration
from user_management.database import get_async_session

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["collaboration"])


async def _list_my_invitations(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Helper for list_my_invitations (#16460).

    Invitations live in each session_collaborations row's own JSONB
    ``invitations`` array, not a separate table, so "my pending invitations
    across every session" is a scan -- there is no index that makes "does
    this JSONB array contain my user_id" a targeted lookup without adding a
    normalized join table, which the small expected scale here doesn't
    justify yet.
    """
    result = await db.execute(select(SessionCollaboration))
    user_id_str = str(user_id)
    mine: list[dict] = []
    for collab in result.scalars().all():
        invitations_list = collab.invitations if isinstance(collab.invitations, list) else []
        for inv in invitations_list:
            if inv.get("user_id") == user_id_str:
                mine.append(
                    {
                        "session_id": collab.session_id,
                        "from_user_id": str(collab.owner_id),
                        "permission": inv.get("permission"),
                        "invited_at": inv.get("invited_at"),
                        "expires_at": inv.get("expires_at"),
                    }
                )
    return mine


@router.get("/{session_id}/events", response_model=SessionEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_events",
    error_code_prefix="COLLABORATION",
)
async def get_session_events(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None, description="ISO timestamp cursor; returns events strictly before it"),
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    List recent collaboration events (activity + secret-share notifications)
    for a session, newest first (#16460).

    Requires: VIEWER permission
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))
        await _ensure_permission(session_id, user_id, PermissionLevel.VIEWER, db)

        stmt = (
            select(CollaborationEvent)
            .where(CollaborationEvent.session_id == session_id)
            .order_by(CollaborationEvent.timestamp.desc())
            .limit(limit + 1)
        )
        if before:
            stmt = stmt.where(CollaborationEvent.timestamp < parse_utc_iso(before))

        result = await db.execute(stmt)
        rows = result.scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        return SessionEventsResponse(
            session_id=session_id,
            events=[
                CollabEventResponse(
                    id=str(event.id),
                    session_id=event.session_id,
                    kind=event.kind,
                    user_id=str(event.user_id) if event.user_id else None,
                    username=event.username,
                    payload=event.payload,
                    timestamp=event.timestamp.isoformat(),
                )
                for event in rows
            ],
            has_more=has_more,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting session events: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session events",
        )


@router.get("/invitations/mine", response_model=MyInvitationsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_my_invitations",
    error_code_prefix="COLLABORATION",
)
async def list_my_invitations(
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    List pending collaboration invitations addressed to the current user,
    across every session (#16460).

    Authorization: identity only, no participant/owner permission check --
    you can only ever see invitations naming your own user_id, and you are
    by definition not yet a participant of a session you're merely invited
    to (that's exactly what accepting the invitation would make you).
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))
        raw = await _list_my_invitations(user_id, db)

        return MyInvitationsResponse(
            invitations=[
                PendingInvitationResponse(
                    session_id=inv["session_id"],
                    from_user_id=inv["from_user_id"],
                    permission=inv["permission"],
                    invited_at=inv["invited_at"],
                    expires_at=inv.get("expires_at"),
                )
                for inv in raw
            ]
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing invitations: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list invitations",
        )


@router.post("/{session_id}/invitations/respond", response_model=InvitationRespondResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="respond_to_invitation",
    error_code_prefix="COLLABORATION",
)
async def respond_to_invitation(
    session_id: str,
    response: InvitationRespondRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept or decline a pending invitation addressed to the current user
    (#16460).

    Authorization: the caller must be the exact user_id the invitation
    names -- not an owner/participant permission check. Accepting an
    invitation is what makes you a participant; you are not one yet, so
    _ensure_permission's VIEWER floor would refuse you.
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))

        collab = await _get_session_collab(session_id, db)
        if not collab:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        invitations_list = collab.invitations if isinstance(collab.invitations, list) else []
        user_id_str = str(user_id)
        my_invitation = next((inv for inv in invitations_list if inv.get("user_id") == user_id_str), None)
        if not my_invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No pending invitation for you in this session",
            )

        permission: str | None = None
        if response.accept:
            permission = my_invitation["permission"]
            collab.add_collaborator(user_id, PermissionLevel(permission))
        collab.remove_invitation(user_id)

        await db.commit()

        logger.info(
            f"User {user_id} {'accepted' if response.accept else 'declined'} " f"invitation to session {session_id}"
        )

        return InvitationRespondResponse(
            success=True,
            session_id=session_id,
            accepted=response.accept,
            permission=permission,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error responding to invitation: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to respond to invitation",
        )
