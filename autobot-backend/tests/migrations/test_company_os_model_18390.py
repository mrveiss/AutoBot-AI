# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 20261012_101 -- Company OS model, up and down (#18390).

Existing Automation rows must stay valid across the upgrade, the new tables must
enforce what the model claims in the schema itself, and the downgrade must put the
previous shape back without touching those rows.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PREVIOUS = "20261012_100"
_TARGET = "20261012_101"
_NEW_TABLES = ("llc_processes", "llc_workflow_nodes", "llc_workflow_transitions", "llc_role_skills")
_INSERT_WF = (
    "INSERT INTO workflows (id, workflow_id, company_id, name, status, source, definition{extra_cols}) "
    "VALUES (:id, :wf, :company, 'n', 'planned', 'created', '{{}}'::jsonb{extra_vals})"
)


async def _tables_and_columns(engine) -> tuple[set[str], set[str]]:
    async with engine.connect() as conn:
        tables = {r[0] for r in await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
        cols = {
            r[0]
            for r in await conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='workflows'")
            )
        }
    return tables, cols


async def test_upgrade_keeps_existing_rows_and_downgrade_restores_the_shape(fresh_db_url):
    assert run_alembic(["upgrade", _PREVIOUS], fresh_db_url).returncode == 0
    legacy, company = str(uuid.uuid4()), str(uuid.uuid4())
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(_INSERT_WF.format(extra_cols="", extra_vals="")), {"id": legacy, "wf": "old", "company": company}
            )
        up = run_alembic(["upgrade", _TARGET], fresh_db_url)
        assert up.returncode == 0, up.stderr
        tables, cols = await _tables_and_columns(engine)
        assert set(_NEW_TABLES) <= tables
        assert {"kind", "owner_role_id", "trigger_type", "trigger_config"} <= cols
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT kind, owner_role_id, trigger_type, trigger_config, name FROM workflows")
                )
            ).one()
        assert (row.kind, row.owner_role_id, row.trigger_type, row.trigger_config, row.name) == (
            "workflow",
            None,
            None,
            {},
            "n",
        )

        down = run_alembic(["downgrade", _PREVIOUS], fresh_db_url)
        assert down.returncode == 0, down.stderr
        tables, cols = await _tables_and_columns(engine)
        assert not set(_NEW_TABLES) & tables
        assert not {"kind", "owner_role_id", "trigger_type", "trigger_config"} & cols
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM workflows"))).scalar() == 1

        again = run_alembic(["upgrade", _TARGET], fresh_db_url)
        assert again.returncode == 0, again.stderr
    finally:
        await engine.dispose()


async def _expect_integrity_error(engine, sql: str, params: dict) -> None:
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)


async def test_schema_itself_refuses_a_meta_skill_with_an_owner_or_a_trigger(fresh_db_url):
    assert run_alembic(["upgrade", _TARGET], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        sql = _INSERT_WF.format(
            extra_cols=", kind, owner_role_id, trigger_type", extra_vals=", 'meta_skill', :role, :trig"
        )
        base = {"company": str(uuid.uuid4())}
        await _expect_integrity_error(
            engine, sql, {**base, "id": str(uuid.uuid4()), "wf": "a", "role": str(uuid.uuid4()), "trig": None}
        )
        await _expect_integrity_error(
            engine, sql, {**base, "id": str(uuid.uuid4()), "wf": "b", "role": None, "trig": "manual"}
        )
        async with engine.begin() as conn:
            await conn.execute(text(sql), {**base, "id": str(uuid.uuid4()), "wf": "c", "role": None, "trig": None})
        bad_kind = _INSERT_WF.format(extra_cols=", kind", extra_vals=", 'bogus'")
        await _expect_integrity_error(engine, bad_kind, {**base, "id": str(uuid.uuid4()), "wf": "d"})
    finally:
        await engine.dispose()


async def test_schema_itself_refuses_malformed_nodes_transitions_and_grants(fresh_db_url):
    assert run_alembic(["upgrade", _TARGET], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    wf, company = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(_INSERT_WF.format(extra_cols="", extra_vals="")), {"id": wf, "wf": "w", "company": company}
            )
        node = (
            "INSERT INTO llc_workflow_nodes (id, company_id, workflow_row_id, node_key, kind{c}) "
            "VALUES (:id, :co, :wf, 'k', :kind{v})"
        )
        args = {"id": str(uuid.uuid4()), "co": company, "wf": wf}
        # a process node without a process, and an end node without an outcome
        await _expect_integrity_error(engine, node.format(c="", v=""), {**args, "kind": "process"})
        await _expect_integrity_error(engine, node.format(c="", v=""), {**args, "kind": "end"})
        trans = (
            "INSERT INTO llc_workflow_transitions (id, company_id, workflow_row_id, from_node_key, to_node_key, kind) "
            "VALUES (:id, :co, :wf, 'a', :to, :kind)"
        )
        # a handoff needs a target workflow; a non-handoff needs a target node
        await _expect_integrity_error(engine, trans, {**args, "to": None, "kind": "handoff"})
        await _expect_integrity_error(engine, trans, {**args, "to": None, "kind": "success"})
        grant = "INSERT INTO llc_role_skills (id, company_id, role_id, skill_name) VALUES (:id, :co, :role, :skill)"
        both_null = {**args, "role": str(uuid.uuid4()), "skill": None}
        await _expect_integrity_error(engine, grant, both_null)
    finally:
        await engine.dispose()


async def test_deleting_a_workflow_cascades_its_graph_and_a_referenced_one_is_restricted(fresh_db_url):
    assert run_alembic(["upgrade", _TARGET], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    owner, target, company = (str(uuid.uuid4()) for _ in range(3))
    try:
        async with engine.begin() as conn:
            for wid, name in ((owner, "o"), (target, "t")):
                await conn.execute(
                    text(_INSERT_WF.format(extra_cols="", extra_vals="")), {"id": wid, "wf": name, "company": company}
                )
            await conn.execute(
                text(
                    "INSERT INTO llc_workflow_nodes (id, company_id, workflow_row_id, node_key, kind) "
                    "VALUES (:id, :co, :wf, 's', 'start')"
                ),
                {"id": str(uuid.uuid4()), "co": company, "wf": owner},
            )
            await conn.execute(
                text(
                    "INSERT INTO llc_workflow_transitions "
                    "(id, company_id, workflow_row_id, from_node_key, kind, handoff_row_id) "
                    "VALUES (:id, :co, :wf, 's', 'handoff', :t)"
                ),
                {"id": str(uuid.uuid4()), "co": company, "wf": owner, "t": target},
            )
        await _expect_integrity_error(engine, "DELETE FROM workflows WHERE id = :id", {"id": target})
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM workflows WHERE id = :id"), {"id": owner})
            assert (await conn.execute(text("SELECT count(*) FROM llc_workflow_nodes"))).scalar() == 0
            assert (await conn.execute(text("SELECT count(*) FROM llc_workflow_transitions"))).scalar() == 0
    finally:
        await engine.dispose()


async def test_downgrade_refuses_while_company_os_data_exists(fresh_db_url):
    """No data loss on update: a meta skill or any model row blocks the downgrade."""
    assert run_alembic(["upgrade", _TARGET], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        sql = _INSERT_WF.format(extra_cols=", kind", extra_vals=", 'meta_skill'")
        async with engine.begin() as conn:
            await conn.execute(text(sql), {"id": str(uuid.uuid4()), "wf": "m", "company": str(uuid.uuid4())})
        refused = run_alembic(["downgrade", _PREVIOUS], fresh_db_url)
        assert refused.returncode != 0 and "downgrade is refused" in refused.stderr
        _, cols = await _tables_and_columns(engine)
        assert "kind" in cols, "a refused downgrade must change nothing"
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM workflows"))
            await conn.execute(
                text(
                    "INSERT INTO llc_processes (id, company_id, process_key, name, owner_role_id) "
                    "VALUES (:id, :co, 'p', 'p', :role)"
                ),
                {"id": str(uuid.uuid4()), "co": str(uuid.uuid4()), "role": str(uuid.uuid4())},
            )
        assert run_alembic(["downgrade", _PREVIOUS], fresh_db_url).returncode != 0
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM llc_processes"))
        assert run_alembic(["downgrade", _PREVIOUS], fresh_db_url).returncode == 0
    finally:
        await engine.dispose()


async def test_a_row_cannot_reference_a_workflow_of_another_company(fresh_db_url):
    """Composite (company_id, id) foreign keys: the database itself refuses the cross-company link."""
    assert run_alembic(["upgrade", _TARGET], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    wf, company_a, company_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(_INSERT_WF.format(extra_cols="", extra_vals="")), {"id": wf, "wf": "w", "company": company_a}
            )
        node = (
            "INSERT INTO llc_workflow_nodes (id, company_id, workflow_row_id, node_key, kind) "
            "VALUES (:id, :co, :wf, 's', 'start')"
        )
        await _expect_integrity_error(engine, node, {"id": str(uuid.uuid4()), "co": company_b, "wf": wf})
        async with engine.begin() as conn:
            await conn.execute(text(node), {"id": str(uuid.uuid4()), "co": company_a, "wf": wf})
    finally:
        await engine.dispose()
