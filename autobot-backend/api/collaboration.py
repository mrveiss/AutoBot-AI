# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session Collaboration API

Multi-user session collaboration with permission management.
Part of Issue #872 - Session Collaboration API (#608 Phase 3).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_agent import (
    CollabInviteRequest,
    CollabInviteResponse,
    CollabParticipantResponse,
    CollabRemoveRequest,
    CollabRemoveResponse,
    CollabShareSecretRequest,
    SessionParticipantsResponse,
)
from api.schemas_workflows import SessionPresenceResponse, SessionShareSecretResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from models.session_collaboration import PermissionLevel, SessionCollaboration
from user_management.database import get_async_session

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["collaboration"])


# ====================================================================
# Permission Helpers
# ====================================================================


async def _get_session_collab(session_id: str, db: AsyncSession) -> SessionCollaboration | None:
    """Get session collaboration record."""
    from sqlalchemy import select

    stmt = select(SessionCollaboration).where(SessionCollaboration.session_id == session_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _ensure_permission(
    session_id: str,
    user_id: uuid.UUID,
    required_level: PermissionLevel,
    db: AsyncSession,
) -> SessionCollaboration:
    """
    Ensure user has required permission level.

    Raises HTTPException if insufficient permission.
    """
    collab = await _get_session_collab(session_id, db)

    if not collab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if not collab.has_permission(user_id, required_level):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission for this operation",
        )

    return collab


async def _get_or_create_collab(session_id: str, owner_id: uuid.UUID, db: AsyncSession) -> SessionCollaboration:
    """Get or create session collaboration record."""
    collab = await _get_session_collab(session_id, db)

    if not collab:
        collab = SessionCollaboration(session_id=session_id, owner_id=owner_id)
        db.add(collab)
        await db.commit()
        await db.refresh(collab)
        logger.info(f"Created collaboration record for session {session_id}")

    return collab


async def _fetch_and_validate_secret(secret_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession):
    """Helper for share_secret_with_session. Ref: #1088."""
    from sqlalchemy import select

    from models.secret import Secret

    stmt = select(Secret).where(Secret.id == secret_id)
    result = await db.execute(stmt)
    secret = result.scalar_one_or_none()

    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    if secret.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only share secrets you own",
        )

    return secret


def _resolve_share_recipients(
    share: CollabShareSecretRequest, user_id: uuid.UUID, collab: SessionCollaboration
) -> list:
    """Helper for share_secret_with_session. Ref: #1088."""
    if share.participant_ids:
        return [uuid.UUID(pid) for pid in share.participant_ids]

    recipient_ids = [collab.owner_id]
    for uid_str, perm in collab.list_collaborators().items():
        if perm in [
            PermissionLevel.EDITOR.value,
            PermissionLevel.OWNER.value,
        ]:
            recipient_ids.append(uuid.UUID(uid_str))
    return recipient_ids


# ====================================================================
# API Endpoints
# ====================================================================


@router.post("/{session_id}/invite", response_model=CollabInviteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="invite_user",
    error_code_prefix="COLLABORATION",
)
async def invite_user(
    session_id: str,
    invite: CollabInviteRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Invite user to collaborate on session.

    Requires: OWNER permission
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))
        invited_user_id = uuid.UUID(invite.user_id)

        # Ensure caller is owner
        collab = await _ensure_permission(session_id, user_id, PermissionLevel.OWNER, db)

        # Add collaborator
        collab.add_collaborator(invited_user_id, invite.permission)

        await db.commit()

        logger.info(
            f"User {user_id} invited {invited_user_id} " f"to session {session_id} as {invite.permission.value}"
        )

        return CollabInviteResponse(
            success=True,
            session_id=session_id,
            invited_user_id=invite.user_id,
            permission=invite.permission.value,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inviting user to session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invite user",
        )


@router.post("/{session_id}/remove", response_model=CollabRemoveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_collaborator",
    error_code_prefix="COLLABORATION",
)
async def remove_collaborator(
    session_id: str,
    remove: CollabRemoveRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove collaborator from session.

    Requires: OWNER permission
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))
        remove_user_id = uuid.UUID(remove.user_id)

        # Ensure caller is owner
        collab = await _ensure_permission(session_id, user_id, PermissionLevel.OWNER, db)

        # Cannot remove owner
        if remove_user_id == collab.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove session owner",
            )

        # Remove collaborator
        removed = collab.remove_collaborator(remove_user_id)

        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a collaborator",
            )

        await db.commit()

        logger.info(f"User {user_id} removed {remove_user_id} " f"from session {session_id}")

        return CollabRemoveResponse(
            success=True,
            session_id=session_id,
            removed_user_id=remove.user_id,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing collaborator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove collaborator",
        )


@router.get("/{session_id}/participants", response_model=SessionParticipantsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_participants",
    error_code_prefix="COLLABORATION",
)
async def get_participants(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    List all session participants with roles.

    Requires: VIEWER permission
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))

        # Ensure caller has at least viewer access
        collab = await _ensure_permission(session_id, user_id, PermissionLevel.VIEWER, db)

        # Build participant list
        participants = []

        # Add owner
        participants.append(
            CollabParticipantResponse(
                user_id=str(collab.owner_id),
                permission=PermissionLevel.OWNER.value,
                is_owner=True,
            )
        )

        # Add collaborators
        for user_id_str, perm in collab.list_collaborators().items():
            participants.append(
                CollabParticipantResponse(
                    user_id=user_id_str,
                    permission=perm,
                    is_owner=False,
                )
            )

        return SessionParticipantsResponse(
            session_id=session_id,
            owner_id=str(collab.owner_id),
            participants=participants,
            total_count=len(participants),
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting participants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get participants",
        )


@router.post("/{session_id}/secrets/share", response_model=SessionShareSecretResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_secret_with_session",
    error_code_prefix="COLLABORATION",
)
async def share_secret_with_session(
    session_id: str,
    share: CollabShareSecretRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Share secret with session participants.

    Requires: EDITOR permission
    """
    try:
        user_id = uuid.UUID(current_user.get("user_id"))
        secret_id = uuid.UUID(share.secret_id)

        collab = await _ensure_permission(session_id, user_id, PermissionLevel.EDITOR, db)

        secret = await _fetch_and_validate_secret(secret_id, user_id, db)
        recipient_ids = _resolve_share_recipients(share, user_id, collab)

        for recipient_id in recipient_ids:
            if recipient_id != user_id:  # Don't share with self
                secret.share_with(recipient_id)

        await db.commit()

        logger.info(f"User shared secret with {len(recipient_ids)} participants in session {session_id}")

        return {
            "success": True,
            "secret_id": str(secret_id),
            "shared_with_count": len(recipient_ids) - 1,
        }

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sharing secret: %s", e)  # codeql[py/clear-text-logging-sensitive-data]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to share secret",
        )


@router.get("/{session_id}/presence", response_model=SessionPresenceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_presence",
    error_code_prefix="COLLABORATION",
)
async def get_presence(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get online participants (WebSocket presence tracking).

    Requires: VIEWER permission
    Returns list of currently connected user IDs.
    """
    try:
        # Import presence manager (to be implemented)
        from websocket.presence import presence_manager

        online_users = await presence_manager.get_online_users(session_id)

        return {
            "session_id": session_id,
            "online_users": online_users,
            "count": len(online_users),
        }

    except Exception as e:
        logger.error(f"Error getting presence: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get presence information",
        )
