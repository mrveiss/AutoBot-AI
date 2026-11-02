# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""This backend's ``UserService`` — the implementation lives in autobot_shared (#15068).

Not a re-export: it binds the backend's concrete ``User`` and supplies the hooks only this backend has the
means for: its session store, memory-ownership transfer and chat-session handover (#20029). The SLM binds the
same shared class with none. Error classes are in ``autobot_shared.user_management.user_service_errors``.
"""

import uuid
from typing import Any

from autobot_shared.user_management.user_service import UserService as SharedUserService
from user_management.models import User
from user_management.services.session_service import SessionService


class UserService(SharedUserService):
    """User service bound to this backend's ``User`` and its session store."""

    user_model = User

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

    async def reassign_sessions(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Hand the user's chat sessions to a successor, or refuse the removal (#20029)."""
        from user_management.services.session_successor import reassign_user_sessions  # noqa: PLC0415

        return await reassign_user_sessions(self.session, user_id, str(self.context.user_id or "system"))
