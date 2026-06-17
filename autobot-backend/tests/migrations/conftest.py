# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures for Alembic migration-path tests (#10001 / #10026).

Every test gets a disposable database created on the Postgres server named by
``AUTOBOT_MIGRATION_TEST_ADMIN_URL`` (an asyncpg URL with rights to CREATE
DATABASE, e.g. ``postgresql+asyncpg://migtest:migtest@127.0.0.1:5499/postgres``).
Without that variable the whole directory is skipped — these tests need a real
Postgres because the migration chain uses Postgres-only constructs
(postgresql.ENUM, JSONB, TIMESTAMPTZ conversions).

CI provides the URL via a postgres:16 service container (migration-gate
workflow); locally run e.g.::

    docker run -d --name mig-test-pg -e POSTGRES_PASSWORD=migtest \
        -e POSTGRES_USER=migtest -p 5499:5432 postgres:16
    export AUTOBOT_MIGRATION_TEST_ADMIN_URL=postgresql+asyncpg://migtest:migtest@127.0.0.1:5499/postgres
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ADMIN_URL_ENV = "AUTOBOT_MIGRATION_TEST_ADMIN_URL"

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

pytestmark = pytest.mark.migration_gate


def _admin_url() -> str | None:
    return os.environ.get(ADMIN_URL_ENV)


requires_postgres = pytest.mark.skipif(
    not os.environ.get(ADMIN_URL_ENV),
    reason=f"{ADMIN_URL_ENV} not set — needs a disposable Postgres server",
)


@pytest.fixture
async def fresh_db_url():
    """Create a throwaway database for one test; drop it afterwards."""
    admin_url = _admin_url()
    if not admin_url:
        pytest.skip(f"{ADMIN_URL_ENV} not set")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    db_name = f"migtest_{uuid.uuid4().hex[:12]}"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    base = admin_url.rsplit("/", 1)[0]
    url = f"{base}/{db_name}"
    try:
        yield url
    finally:
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
        await admin_engine.dispose()


def run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess:
    """Run ``python -m alembic -c migrations/alembic.ini <args>`` against db_url.

    Mirrors the production invocation (docker/backend/entrypoint.sh and the
    Ansible migration tasks) exactly: cwd is the backend root, config is
    migrations/alembic.ini, URL comes from AUTOBOT_DATABASE_URL.
    """
    env = dict(os.environ)
    env["AUTOBOT_DATABASE_URL"] = db_url
    env["PYTHONPATH"] = f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def run_baseline(db_url: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run the baseline-adoption entrypoint (``python -m migrations.baseline``).

    This is the pre-migration bootstrap step that classifies the database and
    stamps an adoption revision when needed (#10001). Same invocation contract
    as run_alembic: cwd backend root, URL via AUTOBOT_DATABASE_URL.
    """
    env = dict(os.environ)
    env["AUTOBOT_DATABASE_URL"] = db_url
    env["PYTHONPATH"] = f"{BACKEND_ROOT}{os.pathsep}{REPO_ROOT}"
    return subprocess.run(
        [sys.executable, "-m", "migrations.baseline", *(extra_args or [])],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


async def create_all_schema(db_url: str) -> None:
    """Build the schema the way historical app startups did: metadata.create_all.

    Imports the user_management Base model set (incl. canvas,
    push_subscription and process_run, which all register on that Base) and
    creates every table directly — leaving NO alembic_version stamp. This is
    the fleet state #10026 case 3 describes: schema without provenance.

    LLCBase is deliberately NOT included: ``LLCBase.metadata.create_all``
    fails on Postgres at head (#9980 — sa.Enum(PyEnum) emits member NAMES
    while column server_defaults use lowercase values), so no real database
    can have been built that way. Stranded fleet schemas are UM-Base-shaped.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import canvas.models  # noqa: F401 — registers canvas tables on Base
    import models.process_run  # noqa: F401 — registers process_runs/agent_sessions
    import user_management.models  # noqa: F401 — registers all UM models
    from models.push_subscription import PushSubscription  # noqa: F401
    from user_management.models.base import Base

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def drop_alembic_version(db_url: str) -> None:
    """Remove the alembic_version stamp, simulating a never-migrated DB.

    ``upgrade <rev>`` followed by this produces the exact schema an old
    code-version's create_all would have built, without provenance — the
    bracketable legacy fleet state for adoption tests.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()


async def fetch_version_rows(db_url: str) -> list[str]:
    """Return the contents of alembic_version (empty list if table absent)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            present = await conn.execute(text("SELECT to_regclass('public.alembic_version')"))
            if present.scalar() is None:
                return []
            rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
            return [r[0] for r in rows]
    finally:
        await engine.dispose()


def script_head() -> str:
    """Resolve the single head revision of the migration chain."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_ROOT / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("version_locations", str(BACKEND_ROOT / "migrations" / "versions"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"chain must have exactly one head, got {heads}"
    return heads[0]
