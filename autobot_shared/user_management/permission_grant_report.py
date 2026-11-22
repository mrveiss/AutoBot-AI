# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which roles' effective permissions change with the #18259 fix -- read-only.

Before #18259 the DB-backed RBAC path raised for any user holding a role with at
least one ``role_permissions`` row, and the middleware returned an empty set
(deny-all). A role with no rows also granted nothing. So the legacy effective
grant of EVERY role on that path is the empty set, and the fix grants exactly
the role's rows, in the role's scope (#18338): a system role's platform-wide, a
company role's only to callers acting in that company. A role with neither grants
nothing and is not listed. This module computes old vs new per role and permission so the
newly granted set is reviewed per deployment before the fix is deployed.

The secrets vault reads these grants too, platform scope only: a newly granted
``admin:access`` makes the role's holders vault administrators, flagged on its own
line (#18338). The report also lists stored SSO links whose account is a platform
admin, read-only, for review.

Only meaningful where the service runs with ``postgres_enabled``: without it the
middleware never consulted the database, before or after the fix.

Operator use (read-only; the URL is read from an environment variable so it never
appears in the process list)::

    AUTOBOT_GRANT_REPORT_DATABASE_URL=postgresql+asyncpg://... \\
        python -m autobot_shared.user_management.permission_grant_report [--json]

On PostgreSQL the transaction is opened ``READ ONLY`` and always rolled back.
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from autobot_shared.secrets_vault import VAULT_ADMIN_PERMISSION, VAULT_PERMISSION_PREFIX
from autobot_shared.user_management.grant_scope import grant_scope
from autobot_shared.user_management.role_permission_query import role_grant_rows_query
from autobot_shared.user_management.sso_admin_link_audit import (
    SSOAdminLink,
    find_sso_admin_links,
    format_sso_admin_links,
)

DEFAULT_URL_ENV = "AUTOBOT_GRANT_REPORT_DATABASE_URL"


@dataclass(frozen=True)
class RoleGrantChange:
    """One role whose effective permission set differs between legacy and fixed code."""

    role_id: str
    role_name: str
    org_id: str | None
    is_system: bool
    scope: str
    users_holding: int
    granted: tuple[str, ...]
    revoked: tuple[str, ...]
    #: Newly granted names the secrets vault reads (#10088), which asks for platform grants only.
    vault_admin: bool = False
    vault_grants: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrantReport:
    """The role changes plus the read-only SSO admin-link audit."""

    role_changes: list[RoleGrantChange]
    sso_admin_links: list[SSOAdminLink]


def legacy_effective_grant(role_permission_names: Iterable[str]) -> frozenset[str]:
    """What the middleware granted for a role before #18259: always nothing.

    A role with rows made ``select(role.Permission)`` raise ``AttributeError`` and
    the middleware returned ``set()``; a role without rows yielded ``set()`` too.
    The argument is taken so the contract (old depends on nothing) stays explicit.
    """
    del role_permission_names
    return frozenset()


def _group_rows(rows: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Fold (role, permission) rows into one entry per role, order preserved."""
    roles: dict[str, dict[str, Any]] = {}
    for row in rows:
        role_id = str(row.role_id)
        entry = roles.setdefault(
            role_id,
            {
                "role_name": row.role_name,
                "org_id": str(row.org_id) if row.org_id is not None else None,
                "is_system": bool(row.is_system),
                "scope": grant_scope(row.org_id, bool(row.is_system)),
                "users_holding": int(row.users_holding),
                "permissions": [],
            },
        )
        entry["permissions"].append(row.permission_name)
    return roles


def _change_for(role_id: str, entry: dict[str, Any]) -> RoleGrantChange | None:
    """The role's change, or None when legacy and fixed grants agree.

    A role whose grants have no scope (no company, not a system role) grants nothing
    after the fix either, so it is not a change (#18338).
    """
    new = frozenset(entry["permissions"]) if entry["scope"] else frozenset()
    old = legacy_effective_grant(entry["permissions"])
    if old == new:
        return None
    granted = tuple(sorted(new - old))
    vault_view = granted if entry["scope"] == "platform" else ()
    return RoleGrantChange(
        role_id=role_id,
        role_name=entry["role_name"],
        org_id=entry["org_id"],
        is_system=entry["is_system"],
        scope=entry["scope"],
        users_holding=entry["users_holding"],
        granted=granted,
        revoked=tuple(sorted(old - new)),
        vault_admin=VAULT_ADMIN_PERMISSION in vault_view,
        vault_grants=tuple(name for name in vault_view if name.startswith(VAULT_PERMISSION_PREFIX)),
    )


async def build_grant_change_report(session: Any) -> list[RoleGrantChange]:
    """Every role whose effective grant changes with the fix. Reads only.

    *session* is an ``AsyncSession`` or ``AsyncConnection``; nothing is written.
    """
    result = await session.execute(role_grant_rows_query())
    changes = (_change_for(role_id, entry) for role_id, entry in _group_rows(result).items())
    return [change for change in changes if change is not None]


def _vault_lines(change: RoleGrantChange) -> list[str]:
    """The vault consequences of a role change, each on its own line (#18338)."""
    lines = []
    if change.vault_admin:
        lines.append(f"    ! VAULT ADMIN: {change.users_holding} holder(s) become secrets-vault administrators")
    lines.extend(f"    ! vault grant: {name}" for name in change.vault_grants)
    return lines


def format_report(changes: list[RoleGrantChange]) -> str:
    """Human-readable report: one block per role, one line per permission, vault effects flagged."""
    if not changes:
        return "No role's effective permission set changes with the #18259 fix.\n"
    lines = [f"{len(changes)} role(s) change effective permissions with the #18259 fix:"]
    for change in changes:
        lines.append(
            f"- role {change.role_name} ({change.role_id}, grants apply: {change.scope}, "
            f"{change.users_holding} user(s))"
        )
        lines.extend(f"    + {name}" for name in change.granted)
        lines.extend(f"    - {name}" for name in change.revoked)
        lines.extend(_vault_lines(change))
    return "\n".join(lines) + "\n"


async def build_report(session: Any) -> GrantReport:
    """The whole read-only report: role changes and stored SSO links to platform admins."""
    return GrantReport(await build_grant_change_report(session), await find_sso_admin_links(session))


async def _report_from_url(url: str) -> GrantReport:
    """Open a read-only transaction, build the report, roll back, dispose."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                await conn.execute(text("SET TRANSACTION READ ONLY"))
            try:
                return await build_report(conn)
            finally:
                await conn.rollback()
    finally:
        await engine.dispose()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--url-env", default=DEFAULT_URL_ENV, help="env var holding the database URL")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 2 when the URL variable is unset."""
    args = _parse_args(argv)
    url = os.environ.get(args.url_env)
    if not url:
        sys.stderr.write(f"{args.url_env} is not set; it must hold the database URL\n")
        return 2
    report = asyncio.run(_report_from_url(url))
    if args.json:
        sys.stdout.write(json.dumps(asdict(report), indent=2) + "\n")
    else:
        sys.stdout.write(format_report(report.role_changes) + format_sso_admin_links(report.sso_admin_links))
    return 0


if __name__ == "__main__":
    sys.exit(main())
