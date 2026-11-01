# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Account lifecycle for the shared ``UserService`` (#15068).

Two of the four hunks that separated the backend's and the SLM's copies live
here, merged as a union of what each side did, never a choice between them:

- ``change_password``: both services set the password epoch, which revokes
  every session opened with the old password (#12924). The backend also
  invalidated its own session store; that is now the ``invalidate_other_sessions``
  hook, a no-op where no such store exists. The audit entry carries BOTH keys
  the two copies wrote — ``sessions_revoked_from`` (SLM) and
  ``sessions_invalidated`` (backend, 0 where the hook does nothing) — so no
  consumer of either service's audit trail loses a field.
- ``delete_user(reassign_to=...)``: backend-only memory reassignment, now the
  ``reassign_memory`` hook. Fail-closed on hard delete is preserved.
"""

import uuid
from typing import Any

from sqlalchemy import select

from autobot_shared.db_session import run_after_commit
from autobot_shared.logging_manager import get_logger
from autobot_shared.membership_epoch import MembershipEpochBump
from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.audit import AuditResourceType, IdentityAuditAction
from autobot_shared.user_management.models.team import Team, TeamMembership
from autobot_shared.user_management.models.user import UserCore
from autobot_shared.user_management.password_epoch import set_password_epoch
from autobot_shared.user_management.user_service_base import UserServiceBase
from autobot_shared.user_management.user_service_errors import (
    InvalidCredentialsError,
    UserNotFoundError,
)

logger = get_logger(__name__)


class UserLifecycleMixin(UserServiceBase):
    """Password change, activation state and deletion."""

    async def _require_user(self, user_id: uuid.UUID) -> UserCore:
        """Return the user, or raise ``UserNotFoundError``."""
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")
        return user

    def _check_current_password(self, user: UserCore, current_password: str | None, require_current: bool) -> None:
        """Raise ``InvalidCredentialsError`` unless the current password verifies."""
        if require_current and user.password_hash:
            if not current_password or not self.verify_password(current_password, user.password_hash):
                raise InvalidCredentialsError("Current password is incorrect")

    async def change_password(
        self,
        user_id: uuid.UUID,
        current_password: str | None,
        new_password: str,
        require_current: bool = True,
        current_token: str | None = None,
    ) -> bool:
        """Change a user's password and revoke the sessions opened with the old one.

        ``current_token`` is passed to ``invalidate_other_sessions`` so a service
        with its own session store can spare the caller's session there.

        Raises:
            UserNotFoundError: the user does not exist.
            InvalidCredentialsError: the current password is wrong.
        """
        user = await self._require_user(user_id)
        self._check_current_password(user, current_password, require_current)
        user.password_hash = self.hash_password(new_password)
        user.updated_at = now_utc()
        await self.session.flush()

        details = await self._revoke_old_sessions(user_id, user.username, current_token)
        await self._audit_log(IdentityAuditAction.PASSWORD_CHANGED, AuditResourceType.USER, user_id, details)
        return True

    async def _revoke_old_sessions(self, user_id: uuid.UUID, username: str, current_token: str | None) -> dict:
        """Revoke sessions opened with the old password; return the audit details."""
        invalidated_count = await self.invalidate_other_sessions(user_id, current_token)
        epoch = await set_password_epoch(username)
        return {
            "method": "user_initiated",
            "sessions_revoked_from": epoch,
            "sessions_invalidated": invalidated_count,
        }

    async def _set_active(self, user_id: uuid.UUID, active: bool) -> bool:
        """Set ``is_active`` and audit it; raises ``UserNotFoundError``."""
        user = await self._require_user(user_id)
        user.is_active = active
        user.updated_at = now_utc()
        await self.session.flush()
        action = IdentityAuditAction.USER_ACTIVATED if active else IdentityAuditAction.USER_DEACTIVATED
        await self._audit_log(action, AuditResourceType.USER, user_id, {})
        logger.info("%s user: %s", "Activated" if active else "Deactivated", user_id)
        return True

    async def deactivate_user(self, user_id: uuid.UUID) -> bool:
        """Deactivate a user account; raises ``UserNotFoundError``."""
        return await self._set_active(user_id, False)

    async def activate_user(self, user_id: uuid.UUID) -> bool:
        """Activate a user account; raises ``UserNotFoundError``."""
        return await self._set_active(user_id, True)

    async def _reassign_before_delete(
        self, user_id: uuid.UUID, reassign_to: uuid.UUID, hard_delete: bool
    ) -> dict[str, Any]:
        """Run the ``reassign_memory`` hook ahead of a delete.

        Fail-closed for a hard delete: an error propagates and aborts the delete,
        so data is never hard-destroyed-then-orphaned. A soft delete keeps the
        row, so it proceeds and the failure is logged.
        """
        if hard_delete:
            return await self.reassign_memory(user_id, reassign_to)
        try:
            return await self.reassign_memory(user_id, reassign_to)
        except Exception as exc:
            logger.warning("delete_user: memory reassign failed (soft delete continues): %s", exc)
            return {}

    async def _queue_membership_epoch_bumps(self, user: UserCore) -> None:
        """Queue a post-commit membership-epoch bump for every organisation *user* holds a team in (#19670).

        Called BEFORE a hard delete: the ``team_memberships`` rows cascade away with the user, so
        the organisations are read while the rows still exist. The user's own organisation is
        included because the cached memberships are keyed by it.
        """
        rows = await self.session.execute(
            select(Team.org_id)
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .where(TeamMembership.user_id == user.id)
            .distinct()
        )
        org_ids = {user.org_id, *rows.scalars().all()} - {None}
        for org_id in sorted(org_ids, key=str):
            run_after_commit(self.session, MembershipEpochBump(org_id))

    async def delete_user(
        self,
        user_id: uuid.UUID,
        hard_delete: bool = False,
        reassign_to: uuid.UUID | None = None,
    ) -> bool:
        """Delete a user: permanently if *hard_delete*, otherwise soft delete.

        With *reassign_to*, the user's memory records are transferred to that
        user BEFORE the row is deleted (see ``_reassign_before_delete``).

        Raises:
            UserNotFoundError: the user does not exist.
        """
        user = await self._require_user(user_id)
        details: dict[str, Any] = {"hard_delete": hard_delete}
        if reassign_to is not None:
            details["reassign_to"] = str(reassign_to)
            details["reassign_counts"] = await self._reassign_before_delete(user_id, reassign_to, hard_delete)

        if hard_delete:
            await self._queue_membership_epoch_bumps(user)  # the cascade removes the rows this reads
            await self.session.delete(user)
        else:
            user.deleted_at = now_utc()
            user.is_active = False
        await self.session.flush()

        await self._audit_log(IdentityAuditAction.USER_DELETED, AuditResourceType.USER, user_id, details)
        logger.info("Deleted user: %s (hard=%s, reassign_to=%s)", user_id, hard_delete, reassign_to)
        return True
