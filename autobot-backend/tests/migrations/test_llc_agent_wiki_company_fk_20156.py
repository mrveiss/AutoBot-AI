# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``llc_agent_wiki_entries.company_id`` names a real company (#20156).

The Postgres tests need the disposable server the Migration Gate provides (skipped without it);
the mock-driven ones run anywhere.
"""

import importlib
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = pytest.mark.migration_gate

_MODULE = "migrations.versions.20261101_108_llc_agent_wiki_company_fk"
_FK = "fk_llc_agent_wiki_entries_company_id"
_INSERT_ORG = (
    "INSERT INTO organizations (id, name, slug, max_users, is_active, kb_inheritance_weight) "
    "VALUES (:id, :slug, :slug, -1, true, 0.6)"
)
_INSERT_WIKI = "INSERT INTO llc_agent_wiki_entries (agent_id, company_id, key, title) VALUES ('a', :c, :k, 't')"
_COUNT = "SELECT count(*) FROM llc_agent_wiki_entries"


def _upgrade(*, has_table=True, has_fk=False, orphans=0):
    module = importlib.import_module(_MODULE)
    op = MagicMock()
    op.get_bind.return_value.execute.return_value.scalar.return_value = orphans
    with (
        patch.object(module, "op", op),
        patch.object(module, "has_table", return_value=has_table),
        patch.object(module, "_has_fk", return_value=has_fk),
    ):
        module.upgrade()
    return module, op


def test_revision_chain():
    module = importlib.import_module(_MODULE)
    assert (module.revision, module.down_revision) == ("20261101_108", "20261031_107")


def test_constraint_is_not_valid_cascade_and_nothing_is_deleted(caplog):
    _, op = _upgrade(orphans=3)
    sql = op.execute.call_args.args[0]
    assert "NOT VALID" in sql and "ON DELETE CASCADE" in sql and _FK in sql
    executed = [str(c.args[0]) for c in op.get_bind.return_value.execute.call_args_list]
    assert all("DELETE" not in s.upper() and "UPDATE" not in s.upper() for s in executed)


def test_orphans_are_logged_at_warning(caplog):
    with caplog.at_level(logging.WARNING):
        _upgrade(orphans=3)
    assert any("3 row(s)" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


def test_no_orphans_no_warning_and_rerun_is_a_noop(caplog):
    with caplog.at_level(logging.WARNING):
        _upgrade(orphans=0)
    assert not caplog.records
    assert _upgrade(has_fk=True)[1].execute.call_count == 0
    assert _upgrade(has_table=False)[1].execute.call_count == 0


@requires_postgres
async def test_orphans_survive_new_rows_are_checked_and_company_delete_cascades(fresh_db_url):
    assert run_alembic(["upgrade", "20261031_107"], fresh_db_url).returncode == 0
    gone, live = uuid.uuid4(), uuid.uuid4()
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_INSERT_WIKI), {"c": gone, "k": "orphan"})
        assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
        async with engine.begin() as conn:
            assert (await conn.execute(text(_COUNT))).scalar_one() == 1
            valid = await conn.execute(text("SELECT convalidated FROM pg_constraint WHERE conname = :n"), {"n": _FK})
            assert valid.scalar_one() is False
            await conn.execute(text(_INSERT_ORG), {"id": live, "slug": "c-20156"})
            await conn.execute(text(_INSERT_WIKI), {"c": live, "k": "ok"})
        with pytest.raises(Exception, match="foreign key"):
            async with engine.begin() as conn:
                await conn.execute(text(_INSERT_WIKI), {"c": uuid.uuid4(), "k": "bad"})
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": live})
            assert (await conn.execute(text(_COUNT))).scalar_one() == 1  # only the kept orphan remains
        assert run_alembic(["downgrade", "20261031_107"], fresh_db_url).returncode == 0
        assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    finally:
        await engine.dispose()
