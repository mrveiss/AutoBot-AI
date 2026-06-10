# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Test-only harness for the LLC end-to-end loop test (test_llc_e2e_loop.py).

This module is NOT production code. It exists solely to stand up a real
FastAPI app wired to the REAL LLC routers/services, backed by an in-memory
SQLite database, so the core LLC loop can be exercised over httpx without
Postgres, Redis, or network access.

Responsibilities:
1. Register SQLAlchemy compile shims so Postgres-specific column types
   (JSONB / postgresql.UUID) render on the SQLite dialect.
2. Import every LLC model module the loop touches so its table registers on
   ``Base.metadata`` before ``create_all``.
3. Rewrite Postgres-only *raw-text* server defaults so SQLite can create the
   target tables:
     * ``gen_random_uuid()`` and ``'[]'::jsonb`` are DROPPED — the ORM /
       service / seed code always supplies these values explicitly, so the
       server default is never relied upon by the loop.
     * raw ``text("now()")`` is rewritten to ``func.now()`` (CURRENT_TIMESTAMP
       on SQLite) so created_at/updated_at still populate.
   ``func.now()`` defaults (from the shared Base) are a SQL Function, not a
   TextClause, and already render correctly — they are left untouched.
4. Rebind every ``sa.Enum`` column to validate by ENUM VALUE rather than enum
   NAME. The LLC enums store their lowercase ``.value`` ("backlog", "task", …)
   in Postgres native enum types; SQLAlchemy's default ``Enum`` round-trips by
   member NAME, which would reject the persisted lowercase values on SQLite.
5. Make ``created_at`` / ``updated_at`` client-side (Python) defaults instead
   of server defaults, and mark LLCWorkItem's collection relationships
   loaded-empty on init/load. Both avoid post-flush refresh / lazy IO that the
   async session cannot service. See ``_clientside_timestamps`` and
   ``_preload_empty_relationships``.
6. Build a minimal FastAPI app that mounts the real LLC routers under
   ``/api/llc`` (the production ``create_app`` lifespan hard-requires
   Postgres/Redis and cannot boot in-process — see test docstring).
"""

from __future__ import annotations

from typing import List

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import TextClause

# ---------------------------------------------------------------------------
# 1. SQLite compile shims for Postgres-only column types.
#    Registered at import time, BEFORE any create_all is invoked.
# ---------------------------------------------------------------------------


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid_sqlite(type_, compiler, **kw):  # noqa: ANN001, ANN202
    return "CHAR(32)"


# ---------------------------------------------------------------------------
# 2. Model imports — registering tables on Base.metadata.
#    The Base is user_management.models.base.Base (shared by all LLC models).
# ---------------------------------------------------------------------------

# LLC models touched by the loop (work item, budget, heartbeat run, review
# gate, goal/work-product/relation/comment that work_item relationships need).
import llc.models.company  # noqa: E402,F401
import llc.models.goal  # noqa: E402,F401  (work_item FK target)
from llc.models.budget import LLCAgentBudget  # noqa: E402
from llc.models.goal import LLCGoal  # noqa: E402
from llc.models.heartbeat_run import LLCHeartbeatRun  # noqa: E402
from llc.models.label import LLCLabel, LLCWorkItemLabel  # noqa: E402
from llc.models.membership import LLCCompanyMembership  # noqa: E402
from llc.models.review_gate import LLCReviewGatePolicy  # noqa: E402
from llc.models.work_item import (  # noqa: E402
    LLCWorkItem,
    LLCWorkItemComment,
    LLCWorkItemRelation,
)
from llc.models.work_product import LLCWorkProduct  # noqa: E402
from models.agent_org import AgentOrgNode  # noqa: E402
from user_management.models.base import Base  # noqa: E402

# Organization IS the company in the LLC layer (org_id == company_id).
from user_management.models.organization import Organization  # noqa: E402

# Needed for the assignee-display lookup in _item_to_dict after handoff to a
# human reviewer (queries users.display_name / users.username).
from user_management.models.user import User  # noqa: E402

# The exact set of tables the loop touches. Creating only these avoids the
# dozens of unrelated models on the shared Base that carry further Postgres-
# only constructs irrelevant to this test.
_LOOP_MODELS = [
    Organization,
    LLCGoal,
    LLCWorkItem,
    LLCWorkItemComment,
    LLCWorkItemRelation,
    LLCWorkProduct,
    LLCAgentBudget,
    LLCHeartbeatRun,
    LLCReviewGatePolicy,
    LLCCompanyMembership,
    LLCLabel,
    LLCWorkItemLabel,
    AgentOrgNode,
    User,
]

# Raw-text server defaults that SQLite cannot evaluate. Matched only against
# TextClause defaults so ``func.now()`` (a SQL Function, renders as
# CURRENT_TIMESTAMP) is left alone.
_DROP_DEFAULT_MARKERS = ("gen_random_uuid", "::jsonb")


def _scrub_pg_server_defaults(table) -> None:  # noqa: ANN001
    """Rewrite/drop Postgres-only raw-text server defaults (in place)."""
    for column in table.columns:
        default = column.server_default
        if default is None:
            continue
        arg = getattr(default, "arg", None)
        if not isinstance(arg, TextClause):
            continue  # func.now() etc. — renders fine on SQLite
        text_l = str(arg).lower()
        if any(marker in text_l for marker in _DROP_DEFAULT_MARKERS):
            column.server_default = None
        elif "now()" in text_l:
            column.server_default = sa.func.now()


def _rebind_enums_by_value(table) -> None:  # noqa: ANN001
    """Make every Enum column round-trip on the member VALUE, not NAME.

    Production stores the lowercase ``.value`` in Postgres native enums; the
    default SQLAlchemy Enum maps DB strings back to member NAMES, which rejects
    those lowercase values on SQLite. Rebinding with ``values_callable`` aligns
    the SQLite behaviour with production.
    """
    for column in table.columns:
        col_type = column.type
        enum_cls = getattr(col_type, "enum_class", None)
        if enum_cls is None:
            continue
        column.type = sa.Enum(
            enum_cls,
            name=getattr(col_type, "name", None),
            native_enum=False,
            values_callable=lambda e: [member.value for member in e],
        )


def _clientside_timestamps(table) -> None:  # noqa: ANN001
    """Replace server-side created_at/updated_at defaults with Python defaults.

    The shared Base declares ``created_at``/``updated_at`` with
    ``server_default=func.now()`` and ``updated_at`` additionally with
    ``onupdate=func.now()``. After an UPDATE, SQLAlchemy expires the
    server-onupdate column and must re-SELECT it on next access. Under async
    SQLite that refresh fires implicit IO outside an active greenlet and raises
    MissingGreenlet when ``_item_to_dict`` reads ``updated_at`` right after a
    checkout/transition commit. Switching to Python-side defaults makes the ORM
    populate the value in-process, so no post-flush refresh is ever needed.
    Production (asyncpg) is untouched — this only adapts the in-process test
    mapping.
    """
    from sqlalchemy import ColumnDefault

    def _now() -> "datetime":  # noqa: F821
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    for name in ("created_at", "updated_at"):
        if name not in table.c:
            continue
        col = table.c[name]
        col.server_default = None
        col.server_onupdate = None
        col.default = ColumnDefault(_now)
        if name == "updated_at":
            col.onupdate = ColumnDefault(_now)


def loop_tables() -> List["sa.Table"]:
    """Return the SQLAlchemy Table objects for the loop, adapted for SQLite."""
    tables = [m.__table__ for m in _LOOP_MODELS]
    for table in tables:
        _scrub_pg_server_defaults(table)
        _rebind_enums_by_value(table)
        _clientside_timestamps(table)
    return tables


async def create_loop_schema(engine) -> None:  # noqa: ANN001
    """Create only the loop's tables on the given async engine."""
    tables = loop_tables()
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))


# ---------------------------------------------------------------------------
# 5b. Preload LLCWorkItem collection relationships as loaded-empty.
# ---------------------------------------------------------------------------

# LLCWorkItem's children / relation / comment / product collections use
# ``lazy="selectin"``. SQLAlchemy omits eager (selectin) loaders under
# ``SELECT ... FOR UPDATE`` (the lock cannot span the eager join), and a freshly
# created object (POST /work-items) is never SELECTed at all. Accessing those
# unloaded collections in ``_item_to_dict`` then emits implicit lazy IO outside
# an active greenlet and raises MissingGreenlet under async SQLite. In this
# deterministic loop a work item never has relations / comments / products /
# children, so they are marked loaded-and-empty on both ``init`` (created) and
# ``load`` (fetched). This changes no persisted data — it only suppresses a
# redundant lazy load the async session cannot service.
_EMPTY_COLLECTIONS = (
    "outgoing_relations",
    "incoming_relations",
    "comments",
    "work_products",
    "children",
)


def _preload_empty_relationships() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm.attributes import set_committed_value

    def _set_empty(target) -> None:  # noqa: ANN001
        for name in _EMPTY_COLLECTIONS:
            set_committed_value(target, name, [])

    @event.listens_for(LLCWorkItem, "init")
    def _on_init(target, args, kwargs):  # noqa: ANN001, ANN202
        _set_empty(target)

    @event.listens_for(LLCWorkItem, "load")
    def _on_load(target, context):  # noqa: ANN001, ANN202
        _set_empty(target)


_preload_empty_relationships()
