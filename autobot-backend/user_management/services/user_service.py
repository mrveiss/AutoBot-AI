# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""This backend's ``UserService`` — the implementation lives in autobot_shared (#15068).

Not a re-export: this module binds the backend's concrete ``User`` and supplies
the two hooks only this backend has the means for — its own session store and
memory-ownership transfer. The SLM binds the same shared class with neither.
Error classes are imported from ``autobot_shared.user_management.user_service_errors``.
"""

import uuid
from typing import Any

from autobot_shared.auth.permissions import Role, role_value
from autobot_shared.user_management.user_service import UserService as SharedUserService
from user_management.models import User
from user_management.services.session_service import SessionService


class UserService(SharedUserService):
    """User service bound to this backend's ``User`` and its session store."""

    user_model = User

    @staticmethod
    def account_role(user: User) -> str:
        """The role login issues for *user*: ``admin`` for a platform admin, else ``user``.

        The one derivation: ``api/auth.py`` builds the token's role with it, and a
        workflow step re-derives the role an account holds when it runs (#19807).
        """
        return role_value(Role.ADMIN) if user.is_platform_admin else role_value(Role.USER)

    async def invalidate_other_sessions(self, user_id: uuid.UUID, current_token: str | None) -> int:
        """Invalidate every session but *current_token* in this backend's store.

        #12924: the password epoch set alongside this is what actually stops the
        old sessions; this store is still the only mechanism that can spare the
        caller's session.
        """
        return await SessionService().invalidate_user_sessions(user_id=user_id, except_token=current_token)

    async def reassign_memory(self, user_id: uuid.UUID, reassign_to: uuid.UUID) -> dict[str, Any]:
        """Transfer the user's memory records to *reassign_to* (fail-closed on hard delete)."""
        # Lazy import avoids heavy circular deps at module load time.
        from memory.ownership_reassign import reassign_user_memory  # noqa: PLC0415

        return await reassign_user_memory(str(user_id), str(reassign_to))
