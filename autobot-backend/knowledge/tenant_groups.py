# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The team memberships of a verified ``TenantContext``, for its KB principal (#19007).

A ``TenantContext`` carries the user and org only, so a route that authorises through
``get_tenant_context`` had a principal with no groups and its users never saw a fact shared to
their team. The memberships come from the canonical team service
(``autobot_shared.user_management.team_service.TeamService.get_user_teams``: live teams only),
the same set ``extract_user_context_from_request`` reads off an ORM ``User``.

A per-user TTL cache keeps this to one query per user per ``KB_TENANT_GROUPS_TTL_SECONDS``, so a
membership change reaches these routes within that window. A lookup that fails resolves to no
groups: logged, never cached, never a broader scope (THREAT_MODEL: fail closed).
"""

from __future__ import annotations

import uuid
from typing import Any

from cachetools import TTLCache

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Seconds a user's resolved team ids are reused (registered in ``env_registry_knowledge``).
KB_TENANT_GROUPS_TTL_SECONDS = env_int_clamped("AUTOBOT_KB_TENANT_GROUPS_TTL_SECONDS", 60, 0, 3600)

#: Users held at once; the least recently stored entry is evicted past it.
_CACHE_MAX_USERS = 4096

_cache: TTLCache = TTLCache(maxsize=_CACHE_MAX_USERS, ttl=KB_TENANT_GROUPS_TTL_SECONDS)


async def _lookup_team_ids(session: Any, user_id: uuid.UUID) -> tuple[str, ...]:
    """The ids of *user_id*'s live teams, through the canonical team service."""
    from autobot_shared.user_management.team_service import TeamService  # noqa: PLC0415 -- ORM import on use

    teams = await TeamService(session).get_user_teams(user_id)
    return tuple(str(team.id) for team in teams)


async def tenant_group_ids(tenant: Any, session: Any) -> list[str]:
    """The team ids of *tenant*'s user, cached; ``[]`` with no user, or when the lookup fails."""
    user_id = getattr(tenant, "user_id", None)
    if not user_id:
        return []
    key = str(user_id)
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)
    try:
        team_ids = await _lookup_team_ids(session, user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(key))
    except Exception as exc:
        logger.warning("KB team-membership lookup failed for user %s; reading with no groups: %s", key, exc)
        return []
    _cache[key] = team_ids
    return list(team_ids)
