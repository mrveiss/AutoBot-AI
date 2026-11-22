# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""autobot-admin reads the canonical db-credentials.env; the users DSN never falls back to the control DB (#19407)."""

import importlib.util
from pathlib import Path

import pytest

_ADMIN_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autobot-admin.py"


@pytest.fixture
def admin():
    spec = importlib.util.spec_from_file_location("autobot_admin_19407", _ADMIN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _store(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_the_canonical_store_is_read_and_wins(admin, tmp_path, monkeypatch) -> None:
    secrets = _store(  # an earlier file naming other databases: the canonical store must override both
        tmp_path,
        "slm-secrets.env",
        "SLM_ADMIN_PASSWORD=x\n"
        "SLM_DATABASE_URL=postgresql+asyncpg://old:old@127.0.0.2:5432/stale\n"  # pragma: allowlist secret
        "SLM_USERS_DATABASE_URL=postgresql+asyncpg://old:old@127.0.0.2:5432/stale_users\n",  # pragma: allowlist secret
    )
    creds = _store(
        tmp_path,
        "db-credentials.env",
        "SLM_DATABASE_URL=postgresql+asyncpg://slm_app:pw@127.0.0.1:5432/slm\n"  # pragma: allowlist secret
        "SLM_USERS_DATABASE_URL=postgresql+asyncpg://slm_app:pw@127.0.0.1:5432/slm_users\n",  # pragma: allowlist secret
    )
    monkeypatch.setattr(admin, "_SECRETS_FILES", (secrets, str(tmp_path / "missing.env"), creds))
    env = admin._secrets_env()
    users = "postgresql://slm_app:pw@127.0.0.1:5432/slm_users"  # pragma: allowlist secret
    control = "postgresql://slm_app:pw@127.0.0.1:5432/slm"  # pragma: allowlist secret
    assert admin._dsn_from(env, "SLM_USERS_DATABASE_URL") == users
    assert admin._dsn_from(env, "SLM_DATABASE_URL") == control


def test_without_urls_each_dsn_falls_back_to_its_own_database(admin, tmp_path, monkeypatch) -> None:
    creds = _store(tmp_path, "db-credentials.env", "SLM_DB_PASSWORD=pw\n")
    monkeypatch.setattr(admin, "_SECRETS_FILES", (creds,))
    env = admin._secrets_env()
    assert admin._dsn_from(env, "SLM_USERS_DATABASE_URL").endswith("/slm_users")
    assert admin._dsn_from(env, "SLM_DATABASE_URL").endswith("/slm")
    assert ":pw@" in admin._dsn_from(env, "SLM_DATABASE_URL")


def test_the_canonical_store_is_in_the_read_list(admin) -> None:
    assert admin._SECRETS_FILES[-1] == "/etc/autobot/db-credentials.env"  # read last, so it wins


def test_the_role_written_database_names_override_the_defaults(admin, tmp_path, monkeypatch) -> None:
    creds = _store(tmp_path, "db-credentials.env", "SLM_DB_NAME=slm_alt\nSLM_DB_SLM_USERS=users_alt\n")
    monkeypatch.setattr(admin, "_SECRETS_FILES", (creds,))
    env = admin._secrets_env()
    assert admin._dsn_from(env, "SLM_DATABASE_URL").endswith("/slm_alt")
    assert admin._dsn_from(env, "SLM_USERS_DATABASE_URL").endswith("/users_alt")


def test_a_blank_database_name_key_uses_the_default(admin, tmp_path, monkeypatch) -> None:
    creds = _store(tmp_path, "db-credentials.env", "SLM_DB_NAME=\nSLM_DB_SLM_USERS=\n")
    monkeypatch.setattr(admin, "_SECRETS_FILES", (creds,))
    env = admin._secrets_env()
    assert admin._dsn_from(env, "SLM_DATABASE_URL").endswith("/slm")
    assert admin._dsn_from(env, "SLM_USERS_DATABASE_URL").endswith("/slm_users")


def test_an_unreadable_store_exits_with_a_message(admin, tmp_path, monkeypatch) -> None:
    creds = _store(tmp_path, "db-credentials.env", "SLM_DB_NAME=slm\n")
    real_read_text = Path.read_text

    def refuse(self, *args, **kwargs):
        if str(self) == creds:
            raise PermissionError(13, "Permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", refuse)
    with pytest.raises(SystemExit, match="cannot read .*db-credentials.env .*root or the autobot user"):
        admin.load_env_file(creds)


def test_a_missing_store_is_empty(admin, tmp_path) -> None:
    assert admin.load_env_file(str(tmp_path / "absent.env")) == {}


def test_a_non_utf8_store_exits_with_a_message_not_a_traceback(admin, tmp_path) -> None:
    store = tmp_path / "slm-secrets.env"
    store.write_bytes(b"SLM_DATABASE_URL=\xff\xfe\n")
    with pytest.raises(SystemExit) as exit_info:
        admin.load_env_file(store)
    assert "not UTF-8" in str(exit_info.value) and "\xff" not in str(exit_info.value)


def test_a_password_with_url_characters_parses_back_from_the_dsn(admin, monkeypatch) -> None:
    """#19812: raw, these end the credentials early and the CLI connects to the wrong host."""
    from urllib.parse import unquote, urlsplit

    monkeypatch.setattr(admin, "_secrets_env", lambda: {"SLM_DB_HOST": "db.local", "SLM_DB_PASSWORD": "@:/%"})
    parts = urlsplit(admin.get_db_url("slm"))
    assert unquote(parts.password) == "@:/%" and parts.hostname == "db.local"
