# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The #18259 grant-change report: every role whose effective grant changes.

The fixture below is the set the PR body quotes as the newly granted set.
"""

import json
import uuid

from sqlalchemy.ext.asyncio import create_async_engine

from autobot_shared.user_management import permission_grant_report as report
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.conftest import _private_metadata
from autobot_shared.user_management.role_permission_query_test import _Bound

_ORG = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


async def _seed(db):
    await db.add_role("admin", ["users:read", "users:write", "secrets:system:read"])
    await db.add_role("auditor", ["audit:read"], org_id=_ORG)
    await db.add_role("empty", [])
    await db.add_user("u1", ["admin"])
    await db.add_user("u2", ["admin", "auditor"])
    await db.add_user("u3", ["empty"])


async def test_report_lists_every_role_with_permissions_and_its_new_grant(grant_db):
    await _seed(grant_db)
    changes = await report.build_grant_change_report(grant_db.session)
    summary = {c.role_name: (c.granted, c.revoked, c.users_holding, c.scope) for c in changes}
    assert summary == {
        "admin": (("secrets:system:read", "users:read", "users:write"), (), 2, "platform"),
        "auditor": (("audit:read",), (), 1, f"org:{_ORG}"),
    }


async def test_a_role_with_no_scope_is_not_a_change(grant_db):
    """#18338: no company and not a system role grants nothing after the fix either."""
    await grant_db.add_role("custom", ["admin.system"], is_system=False)
    await grant_db.add_user("u9", ["custom"])
    assert await report.build_grant_change_report(grant_db.session) == []


async def test_report_new_grant_matches_the_fixed_user_query(grant_db):
    """The report and ``get_user_permissions`` share one statement source."""
    await _seed(grant_db)
    changes = {c.role_name: set(c.granted) for c in await report.build_grant_change_report(grant_db.session)}
    service = _Bound(grant_db.session, TenantContext())
    assert await service.get_user_permissions(grant_db.users["u2"]) == changes["admin"]
    assert await service.get_user_permissions(grant_db.users["u2"], _ORG) == changes["admin"] | changes["auditor"]


async def test_report_writes_nothing(grant_db):
    await _seed(grant_db)
    await report.build_grant_change_report(grant_db.session)
    assert not grant_db.session.new and not grant_db.session.dirty and not grant_db.session.deleted


async def test_empty_database_reports_no_change(grant_db):
    assert await report.build_grant_change_report(grant_db.session) == []
    assert "No role" in report.format_report([])


def test_legacy_grant_is_empty_whatever_the_rows():
    assert report.legacy_effective_grant(["users:read"]) == frozenset()
    assert report.legacy_effective_grant([]) == frozenset()


def test_format_report_lists_role_and_permissions():
    change = report.RoleGrantChange("r1", "admin", None, True, "platform", 2, ("users:read",), ())
    text = report.format_report([change])
    assert "role admin (r1, grants apply: platform, 2 user(s))" in text and "    + users:read" in text


def test_cli_refuses_without_the_url_variable(monkeypatch, capsys):
    monkeypatch.delenv(report.DEFAULT_URL_ENV, raising=False)
    assert report.main([]) == 2
    assert report.DEFAULT_URL_ENV in capsys.readouterr().err


def test_cli_emits_json(monkeypatch, capsys):
    change = report.RoleGrantChange("r1", "admin", None, True, "platform", 1, ("users:read",), ())

    async def fake(url):
        assert url == "sqlite+aiosqlite:///:memory:"
        return report.GrantReport([change], [])

    monkeypatch.setenv("GRANT_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(report, "_report_from_url", fake)
    assert report.main(["--url-env", "GRANT_URL", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["role_changes"][0]["granted"] == ["users:read"] and payload["sso_admin_links"] == []


async def test_report_from_url_reads_a_real_engine(tmp_path):
    """End to end through the CLI's own engine path, against an empty SQLite file."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'rbac.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(_private_metadata().create_all)
    await engine.dispose()
    assert await report._report_from_url(url) == report.GrantReport([], [])


async def test_a_newly_granted_vault_admin_is_flagged_on_its_own_line(grant_db):
    """#18338: the vault reads admin:access from platform grants, so the operator must see it."""
    await grant_db.add_role("ops", ["admin:access", "secrets:system:read", "users:read"])
    await grant_db.add_role("company-ops", ["admin:access"], org_id=_ORG)
    await grant_db.add_user("v1", ["ops", "company-ops"])
    changes = {c.role_name: c for c in await report.build_grant_change_report(grant_db.session)}
    assert changes["ops"].vault_admin and changes["ops"].vault_grants == ("secrets:system:read",)
    assert not changes["company-ops"].vault_admin  # the vault asks for platform grants only
    text = report.format_report(list(changes.values()))
    assert "! VAULT ADMIN: 1 holder(s) become secrets-vault administrators" in text
    assert "! vault grant: secrets:system:read" in text
    assert text.count("VAULT ADMIN") == 1


async def test_the_report_lists_stored_sso_links_to_platform_admins(grant_db):
    await grant_db.add_sso_link("root-admin", admin=True)
    await grant_db.add_sso_link("plain-user", admin=False)
    full = await report.build_report(grant_db.session)
    assert [link.username for link in full.sso_admin_links] == ["root-admin"]
    assert "user root-admin" in report.format_sso_admin_links(full.sso_admin_links)
    assert "No stored SSO link" in report.format_sso_admin_links([])
    assert not grant_db.session.new and not grant_db.session.dirty and not grant_db.session.deleted
