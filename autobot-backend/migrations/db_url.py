# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Database-URL resolution shared by env.py and the baseline entrypoint.

Single source for how migration tooling locates the backend Postgres
database: ``AUTOBOT_DATABASE_URL`` first, then the deployment config, then
the development fallback. Extracted from env.py so migrations/baseline.py
can reuse it without executing the Alembic context (#10001).
"""

import os

from sqlalchemy.engine import make_url


def get_url() -> str:
    """Get database URL from deployment config or environment."""
    url = os.environ.get("AUTOBOT_DATABASE_URL", "")
    if url:
        return url

    # Fall back to deployment config (Postgres-backed user modes)
    try:
        from user_management.config import get_deployment_config

        deployment_config = get_deployment_config()
        return deployment_config.postgres_sync_url
    except Exception:
        # Default fallback for development
        db_host = os.environ.get("AUTOBOT_POSTGRES_HOST", "autobot-postgres")
        return f"postgresql://autobot:autobot@{db_host}:5432/autobot"


def as_async_url(url: str) -> str:
    """Force the asyncpg driver onto a Postgres URL.

    ``get_url()`` fallbacks return sync URLs (``postgresql://`` → psycopg2,
    which is not installed); the engines built by migration tooling are
    async, so a plain-driver URL aborted migrations before ever
    connecting (#9759).
    """
    sa_url = make_url(url)
    if sa_url.drivername in ("postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        sa_url = sa_url.set(drivername="postgresql+asyncpg")
    return sa_url.render_as_string(hide_password=False)
