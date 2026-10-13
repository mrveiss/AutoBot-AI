# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only audit: existing SSO identity links whose account is a platform admin (#18338).

Before #18338 the SSO path linked an unlinked identity to ANY existing account with a
matching email, platform admins included. No such link could sign in while SSO token
minting raised (#18322), but the links may exist, and from #18322 on they would sign
in. The policy now refuses NEW links to a platform admin by email; this lists the ones
already stored so an operator reviews them before deploy.

It only reads. Removing a link is a data change and goes through the #17038 review
queue as a proposal, never through this code.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, column, select, table

from autobot_shared.user_management.models.sso import SSOProvider, UserSSOLink

_LINKS = UserSSOLink.__table__
_PROVIDERS = SSOProvider.__table__
# Each service maps its own concrete ``users`` table (UserCore is abstract), so the
# audit names only the columns every one of them carries.
_USERS = table("users", column("id"), column("username"), column("is_platform_admin"))


@dataclass(frozen=True)
class SSOAdminLink:
    """One stored SSO link whose local account is a platform admin."""

    link_id: str
    user_id: str
    username: str
    provider_name: str
    provider_type: str


def sso_admin_links_query() -> Select:
    """Every SSO link whose account has ``is_platform_admin`` set, ordered by user then provider."""
    joined = _LINKS.join(_USERS, _USERS.c.id == _LINKS.c.user_id).join(
        _PROVIDERS, _PROVIDERS.c.id == _LINKS.c.provider_id
    )
    columns = (_LINKS.c.id, _LINKS.c.user_id, _USERS.c.username, _PROVIDERS.c.name, _PROVIDERS.c.provider_type)
    return (
        select(*columns)
        .select_from(joined)
        .where(_USERS.c.is_platform_admin.is_(True))
        .order_by(_USERS.c.username, _PROVIDERS.c.name)
    )


async def find_sso_admin_links(session: Any) -> list[SSOAdminLink]:
    """The stored SSO links to platform-admin accounts. Reads only."""
    rows = (await session.execute(sso_admin_links_query())).all()
    return [SSOAdminLink(str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(r[4])) for r in rows]


def format_sso_admin_links(links: list[SSOAdminLink]) -> str:
    """Human-readable section for the grant report."""
    if not links:
        return "No stored SSO link points at a platform-admin account.\n"
    header = f"{len(links)} stored SSO link(s) point at a platform-admin account"
    lines = [f"{header} (review; unlinking is a #17038 proposal):"]
    lines.extend(
        f"- user {link.username} ({link.user_id}) via {link.provider_type} provider {link.provider_name} "
        f"(link {link.link_id})"
        for link in links
    )
    return "\n".join(lines) + "\n"
