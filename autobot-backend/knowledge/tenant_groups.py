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

A per-(organisation, user) TTL cache keeps this to one query per user per
``KB_TENANT_GROUPS_TTL_SECONDS``. Each entry carries the organisation's membership epoch
(``knowledge.acl_epoch``) it was resolved under, and is served only while that epoch is still the
current one: ``TeamService`` bumps it on a removal or a team delete, so a removed member loses
the team's facts in every worker at once, not when the TTL runs out (#19630). An epoch that cannot be
read serves and fills nothing: the memberships are re-resolved. A lookup that fails resolves to no
groups: logged, never cached, never a broader scope (THREAT_MODEL: fail closed).

A tenant with no organisation (a platform admin, a service principal) resolves to no groups: an
unscoped lookup would return teams of every organisation. A superadmin reads team facts through
an explicit organisation context.

The team lookup is scoped to the tenant's organisation, and the organisation is part of the cache
key, so a team of another organisation can neither be returned nor served from a shared entry.
"""

from __future__ import annotations

import uuid
from typing import Any

from cachetools import TTLCache

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from knowledge.acl_epoch import read_membership_epoch

logger = get_logger(__name__)

#: Seconds a user's resolved team ids are reused (registered in ``env_registry_knowledge``).
KB_TENANT_GROUPS_TTL_SECONDS = env_int_clamped("AUTOBOT_KB_TENANT_GROUPS_TTL_SECONDS", 60, 0, 3600)

#: Users held at once; the least recently stored entry is evicted past it.
_CACHE_MAX_USERS = 4096

_cache: TTLCache = TTLCache(maxsize=_CACHE_MAX_USERS, ttl=KB_TENANT_GROUPS_TTL_SECONDS)


def _as_uuid(value: Any) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def _lookup_team_ids(session: Any, user_id: uuid.UUID, org_id: uuid.UUID) -> tuple[str, ...]:
    """The ids of *user_id*'s live teams in *org_id*, through the canonical team service."""
    from autobot_shared.user_management.base_service import TenantContext  # noqa: PLC0415 -- ORM import on use
    from autobot_shared.user_management.team_service import TeamService  # noqa: PLC0415 -- ORM import on use

    teams = await TeamService(session, TenantContext(org_id=org_id, user_id=user_id)).get_user_teams(user_id)
    return tuple(str(team.id) for team in teams)


def _cached_team_ids(key: tuple[str, str], epoch: str | None) -> tuple[str, ...] | None:
    """The entry for *key* if it was resolved under the current *epoch*; ``None`` re-resolves."""
    if epoch is None:
        return None
    entry = _cache.get(key)
    if entry is None or entry[0] != epoch:
        return None
    return entry[1]


async def tenant_group_ids(tenant: Any, session: Any) -> list[str]:
    """The team ids of *tenant*'s user in its organisation, cached; ``[]`` with no user or a failed lookup."""
    user_id = getattr(tenant, "user_id", None)
    if not user_id:
        return []
    org_id = getattr(tenant, "org_id", None)
    if not org_id:
        return []
    key = (str(org_id), str(user_id))
    epoch = await read_membership_epoch(org_id)  # read BEFORE the lookup: a bump during it orphans the entry it fills
    cached = _cached_team_ids(key, epoch)
    if cached is not None:
        return list(cached)
    try:
        team_ids = await _lookup_team_ids(session, _as_uuid(user_id), _as_uuid(org_id))
    except Exception as exc:
        logger.warning("KB team-membership lookup failed for user %s; reading with no groups: %s", key[1], exc)
        return []
    if epoch is not None:
        _cache[key] = (epoch, team_ids)
    return list(team_ids)
