# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The RBAC role an account holds, from its id (#22278).

``role_has_permission`` answers from a role string; a tool call carries only the verified user id. This is
the id -> role step: the role login issues for the account (``UserAccessMixin.account_role``), read from the
same user store, so a tool call is judged by the role the account's own token would have carried.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.user_service_access import UserAccessMixin
from user_management.database import db_session_context
from user_management.services.user_service import UserService

logger = get_logger(__name__)


async def role_for_user_id(user_id: str) -> Optional[str]:
    """The role of account *user_id*; None when it is not a known account or the store cannot be read (fail closed)."""
    try:
        async with db_session_context() as session:
            user = await UserService(session).get_user(uuid.UUID(str(user_id)))
    except (ValueError, SQLAlchemyError) as exc:
        logger.error("could not resolve the role of user %s: %s", user_id, exc)
        return None
    return UserAccessMixin.account_role(user) if user is not None else None
