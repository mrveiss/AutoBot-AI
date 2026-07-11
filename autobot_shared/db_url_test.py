# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autobot_shared.db_url.assemble_postgres_url (#11466).

Regression suite proving the shared primitive produces the exact strings
that both call sites previously assembled inline.
"""

from autobot_shared.db_url import assemble_postgres_url

# ---------------------------------------------------------------------------
# Core contract
# ---------------------------------------------------------------------------


def test_empty_source_no_default_host_returns_empty() -> None:
    """When host is absent and default_host is '', return ''."""
    assert assemble_postgres_url({}) == ""


def test_host_present_no_password_omits_colon() -> None:
    """Auth segment is 'user@' (not 'user:@') when password is empty."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "db.example.com"},
        default_user="myuser",
        default_db="mydb",
    )
    assert result == "postgresql://myuser@db.example.com:5432/mydb"
    assert ":@" not in result


def test_host_present_with_password_includes_colon() -> None:
    """Auth segment is 'user:pw@' when password is non-empty."""
    result = assemble_postgres_url(
        {
            "AUTOBOT_POSTGRES_HOST": "db.example.com",
            "AUTOBOT_POSTGRES_PASSWORD": "secret",
        },
        default_user="myuser",
        default_db="mydb",
    )
    assert result == "postgresql://myuser:secret@db.example.com:5432/mydb"


def test_custom_port_is_respected() -> None:
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "pg", "AUTOBOT_POSTGRES_PORT": "5433"},
        default_user="u",
        default_db="d",
    )
    assert ":5433/" in result


def test_custom_db_is_respected() -> None:
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "pg", "AUTOBOT_POSTGRES_DB": "mydb"},
        default_user="u",
    )
    assert result.endswith("/mydb")


def test_default_host_is_used_when_absent() -> None:
    result = assemble_postgres_url(
        {},
        default_host="autobot-postgres",
        default_user="autobot",
        default_db="autobot",
        password_default="autobot",
    )
    assert result == "postgresql://autobot:autobot@autobot-postgres:5432/autobot"


def test_password_default_applied_when_key_absent() -> None:
    """password_default is used when AUTOBOT_POSTGRES_PASSWORD is not in source."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "h"},
        default_user="u",
        default_db="d",
        password_default="pw123",
    )
    assert "u:pw123@" in result


# ---------------------------------------------------------------------------
# Regression: migrations/db_url.py dev-fallback (call site A)
# Exact string: postgresql://autobot:autobot@{host}:5432/autobot
# ---------------------------------------------------------------------------


def test_migrations_dev_fallback_default_host() -> None:
    """Reproduces migrations/db_url.py dev-fallback with default host."""
    result = assemble_postgres_url(
        {},
        default_host="autobot-postgres",
        default_user="autobot",
        default_db="autobot",
        password_default="autobot",
    )
    assert result == "postgresql://autobot:autobot@autobot-postgres:5432/autobot"


def test_migrations_dev_fallback_custom_host() -> None:
    """Reproduces migrations/db_url.py dev-fallback with a custom host in source."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "my-pg-host"},
        default_host="autobot-postgres",
        default_user="autobot",
        default_db="autobot",
        password_default="autobot",
    )
    assert result == "postgresql://autobot:autobot@my-pg-host:5432/autobot"


# ---------------------------------------------------------------------------
# Regression: code_sync._resolve_pg_db_url component-var assembly (call site B)
# Defaults: user=autobot_app, pw='', db=autobot_users
# ---------------------------------------------------------------------------


def test_code_sync_assembly_no_password() -> None:
    """Reproduces _resolve_pg_db_url assembly without a password."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": "10.0.0.5"},
        default_user="autobot_app",
        default_db="autobot_users",
    )
    assert result == "postgresql://autobot_app@10.0.0.5:5432/autobot_users"


def test_code_sync_assembly_with_password() -> None:
    """Reproduces _resolve_pg_db_url assembly with a password."""
    result = assemble_postgres_url(
        {
            "AUTOBOT_POSTGRES_HOST": "10.0.0.5",
            "AUTOBOT_POSTGRES_USER": "svc_user",
            "AUTOBOT_POSTGRES_PASSWORD": "s3cr3t",
            "AUTOBOT_POSTGRES_PORT": "5433",
            "AUTOBOT_POSTGRES_DB": "autobot",
        },
        default_user="autobot_app",
        default_db="autobot_users",
    )
    assert result == "postgresql://svc_user:s3cr3t@10.0.0.5:5433/autobot"


def test_code_sync_assembly_no_host_returns_empty() -> None:
    """Returns '' when AUTOBOT_POSTGRES_HOST is absent (no default_host)."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_USER": "autobot_app"},
        default_user="autobot_app",
        default_db="autobot_users",
    )
    assert result == ""


# ---------------------------------------------------------------------------
# Empty-string handling (callers must filter before passing)
# ---------------------------------------------------------------------------


def test_empty_string_host_in_source_returns_empty() -> None:
    """An explicit empty string for host is treated as absent."""
    result = assemble_postgres_url(
        {"AUTOBOT_POSTGRES_HOST": ""},
        default_user="u",
        default_db="d",
    )
    assert result == ""
