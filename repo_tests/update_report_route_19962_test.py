# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The update report route is admin-only, and its deploy query is bounded and parses the log's start (#19962)."""

from __future__ import annotations

import ast
from unittest.mock import AsyncMock, MagicMock

import pytest
from repo_tests._paths import repo_root
from sqlalchemy import Column, DateTime, Integer, select
from sqlalchemy.orm import declarative_base

_SOURCE = repo_root() / "autobot-slm-backend" / "api" / "update_report.py"
_Base = declarative_base()


class _Deployment(_Base):
    __tablename__ = "deployments"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True))


def _deploy_runs_since():
    """The shipped function, run against a real SQLAlchemy select; the suite stubs its import chain."""
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_deploy_runs_since")
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    namespace = {
        "Deployment": _Deployment,
        "select": select,
        "datetime": datetime,
        "AsyncSession": AsyncSession,
        "DEPLOY_RUNS_LIMIT": 7,
    }
    exec(compile(ast.Module([func], []), str(_SOURCE), "exec"), namespace)  # noqa: S102 - the repo's own source
    return namespace["_deploy_runs_since"]


@pytest.mark.asyncio
async def test_the_query_is_bounded_newest_first_and_reads_a_z_timestamp():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: ["run"])))
    assert await _deploy_runs_since()(db, "2026-10-30T08:50:00Z") == ["run"]
    query = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 7" in query and "DESC" in query and "2026-10-30 08:50:00" in query


@pytest.mark.asyncio
async def test_no_logged_start_lists_nothing_without_a_query():
    db = MagicMock(execute=AsyncMock())
    assert await _deploy_runs_since()(db, None) == []
    db.execute.assert_not_awaited()


def test_the_route_requires_the_admin_permission():
    source = _SOURCE.read_text(encoding="utf-8")
    assert "require_permission(Permission.ADMIN_SYSTEM)" in source
    assert "get_current_user" not in source, "any authenticated user could read raw update errors"
