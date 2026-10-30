# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who acted, for an activity record (GH#13999).

``LLCActivityLogService.record`` requires an actor type. A service that is handed the
caller's identity states it here, in one place, rather than each call site re-deriving it.
"""

from typing import Optional

from ..models.activity import ActorType


def resolve_actor(agent_id: Optional[str] = None, user_id: Optional[str] = None) -> tuple[ActorType, Optional[str]]:
    """Return ``(actor_type, actor_id)`` for the identity the caller supplied.

    A user wins over an agent (a human acting through an agent is still the human's act);
    with neither, the act is the system's and carries no actor id.
    """
    if user_id:
        return ActorType.USER, str(user_id)
    if agent_id:
        return ActorType.AGENT, str(agent_id)
    return ActorType.SYSTEM, None
