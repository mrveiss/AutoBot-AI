# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for migrations/db_url.py (#11466).

Proves that the get_url() dev-fallback branch produces byte-identical output
before and after the shared-helper refactor in #11466.

These tests run WITHOUT a real Postgres or SQLAlchemy connection — they only
exercise the URL string-assembly logic inside get_url() in isolation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path bootstrap: migrations/ is not on sys.path by default on the dev host.
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _BACKEND_ROOT / "migrations"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _get_url_dev_fallback(host_override: str | None = None) -> str:
    """Call get_url() with the deployment-config path failing (dev fallback)."""
    env: dict = {}
    if host_override is not None:
        env["AUTOBOT_POSTGRES_HOST"] = host_override

    with (
        patch.dict(os.environ, env, clear=False),
        patch(
            "user_management.config.get_deployment_config",
            side_effect=RuntimeError("no deployment config in test"),
        ),
    ):
        from migrations.db_url import get_url

        return get_url()


# ---------------------------------------------------------------------------
# #11466 — byte-identical dev-fallback regression
# ---------------------------------------------------------------------------


def test_get_url_dev_fallback_default_host() -> None:
    """Dev fallback without AUTOBOT_POSTGRES_HOST produces the historic default URL.

    Before (#11466): f"postgresql://autobot:autobot@autobot-postgres:5432/autobot"
    """
    env_backup = os.environ.pop("AUTOBOT_POSTGRES_HOST", None)
    env_backup_db_url = os.environ.pop("AUTOBOT_DATABASE_URL", None)
    try:
        result = _get_url_dev_fallback()
    finally:
        if env_backup is not None:
            os.environ["AUTOBOT_POSTGRES_HOST"] = env_backup
        if env_backup_db_url is not None:
            os.environ["AUTOBOT_DATABASE_URL"] = env_backup_db_url

    assert result == "postgresql://autobot:autobot@autobot-postgres:5432/autobot"


def test_get_url_dev_fallback_custom_host() -> None:
    """Dev fallback with a custom AUTOBOT_POSTGRES_HOST substitutes the host only.

    Before (#11466):
        db_host = os.environ.get("AUTOBOT_POSTGRES_HOST", "autobot-postgres")
        return f"postgresql://autobot:autobot@{db_host}:5432/autobot"
    """
    env_backup_db_url = os.environ.pop("AUTOBOT_DATABASE_URL", None)
    try:
        result = _get_url_dev_fallback(host_override="my-custom-pg")
    finally:
        if env_backup_db_url is not None:
            os.environ["AUTOBOT_DATABASE_URL"] = env_backup_db_url

    assert result == "postgresql://autobot:autobot@my-custom-pg:5432/autobot"


def test_get_url_dev_fallback_does_not_pick_up_other_pg_vars() -> None:
    """Dev fallback ignores AUTOBOT_POSTGRES_USER/PASSWORD/DB/PORT — those are
    fixed to 'autobot' in the original code and must stay fixed after #11466.
    """
    env_backup = {
        k: os.environ.pop(k)
        for k in (
            "AUTOBOT_POSTGRES_USER",
            "AUTOBOT_POSTGRES_PASSWORD",
            "AUTOBOT_POSTGRES_DB",
            "AUTOBOT_POSTGRES_PORT",
            "AUTOBOT_DATABASE_URL",
        )
        if k in os.environ
    }
    try:
        os.environ["AUTOBOT_POSTGRES_USER"] = "injected_user"
        os.environ["AUTOBOT_POSTGRES_PASSWORD"] = "injected_pw"
        os.environ["AUTOBOT_POSTGRES_DB"] = "injected_db"
        os.environ["AUTOBOT_POSTGRES_PORT"] = "9999"
        result = _get_url_dev_fallback()
    finally:
        os.environ.pop("AUTOBOT_POSTGRES_USER", None)
        os.environ.pop("AUTOBOT_POSTGRES_PASSWORD", None)
        os.environ.pop("AUTOBOT_POSTGRES_DB", None)
        os.environ.pop("AUTOBOT_POSTGRES_PORT", None)
        os.environ.update(env_backup)

    # User/password/db/port must remain the hardcoded dev values
    assert "autobot:autobot@" in result
    assert ":5432/" in result
    assert result.endswith("/autobot")
    assert "injected" not in result


def test_get_url_prefers_autobot_database_url_env_var() -> None:
    """AUTOBOT_DATABASE_URL in os.environ short-circuits before the dev fallback."""
    env_backup = os.environ.pop("AUTOBOT_DATABASE_URL", None)
    try:
        os.environ["AUTOBOT_DATABASE_URL"] = "postgresql://explicit:url@pghost/pgdb"
        from importlib import reload

        import migrations.db_url as _mod

        reload(_mod)
        result = _mod.get_url()
    finally:
        if env_backup is not None:
            os.environ["AUTOBOT_DATABASE_URL"] = env_backup
        else:
            os.environ.pop("AUTOBOT_DATABASE_URL", None)

    assert result == "postgresql://explicit:url@pghost/pgdb"
