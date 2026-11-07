# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path that changes the SLM admin password revokes the tokens issued before it (#18672).

Startup's SLM_ADMIN_PASSWORD re-sync and `autobot-admin.py reset-password` changed the hash
without recording a password epoch, so an older token stayed valid until it expired. Each test
issues a token, changes the password through the path, and asks the real revocation rule.
"""

import asyncio
import importlib.util
import io
import secrets
import sys
import time
import types
from pathlib import Path

import pytest

from autobot_shared.auth.jwt_core import hash_password
from autobot_shared.user_management import password_epoch
from testkit.fake_async_session import FakeAsyncSession

_ADMIN_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "autobot-admin.py"


def _throwaway() -> str:
    """A fresh random value per test -- nothing credential-like is written in this file."""
    return secrets.token_urlsafe(12)


@pytest.fixture()
def epochs():
    """An in-memory epoch store routed through the real override hook."""
    store: dict[str, int] = {}

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    yield store
    password_epoch.reset_epoch_store()


def _revoked(subject: str, issued_at: int) -> bool:
    return asyncio.run(password_epoch.is_token_revoked_by_password_change({"sub": subject, "iat": issued_at}))


def test_startup_sync_revokes_older_tokens_when_the_password_changed(epochs) -> None:
    from services.admin_password_sync import sync_admin_password

    user = types.SimpleNamespace(username="admin", password_hash=hash_password(_throwaway()))
    issued = int(time.time()) - 5
    assert not _revoked("admin", issued)
    assert asyncio.run(sync_admin_password(FakeAsyncSession(), user, _throwaway())) is True
    assert _revoked("admin", issued), "a token issued before the re-sync still works"


def test_startup_sync_records_nothing_when_the_password_is_unchanged(epochs) -> None:
    from services.admin_password_sync import sync_admin_password

    value = _throwaway()
    user = types.SimpleNamespace(username="admin", password_hash=hash_password(value))
    assert asyncio.run(sync_admin_password(FakeAsyncSession(), user, value)) is False
    assert "admin" not in epochs, "every restart would revoke every admin session"


def test_startup_sync_fails_closed_when_the_epoch_cannot_be_recorded() -> None:
    """01's review: the epoch and the hash are two transactions, so a store failure must leave
    the password unchanged rather than log revoked sessions that are not."""
    from services.admin_password_sync import EpochNotRecordedError, sync_admin_password

    async def get_epoch(subject):
        return None

    async def set_epoch(subject, *, now=None):
        return None  # what password_epoch_store returns after logging a write failure

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    try:
        before = hash_password(_throwaway())
        user = types.SimpleNamespace(username="admin", password_hash=before)
        with pytest.raises(EpochNotRecordedError):
            asyncio.run(sync_admin_password(FakeAsyncSession(), user, _throwaway()))
        assert user.password_hash == before, "the hash changed although no epoch was recorded"
    finally:
        password_epoch.reset_epoch_store()


def test_startup_survives_an_epoch_store_outage_with_the_hash_unchanged(caplog) -> None:
    """CodeRabbit on #18941: an epoch-store outage aborted SLM startup. Startup now logs it
    critical, keeps the old hash (fail closed) and continues."""
    from services.admin_password_sync import sync_admin_password_at_startup

    async def set_epoch(subject, *, now=None):
        return None

    password_epoch.use_epoch_store(get_epoch=lambda subject: None, set_epoch=set_epoch)
    try:
        before = hash_password(_throwaway())
        user = types.SimpleNamespace(username="admin", password_hash=before)
        with caplog.at_level("CRITICAL", logger="services.admin_password_sync"):
            assert asyncio.run(sync_admin_password_at_startup(FakeAsyncSession(), user, _throwaway())) is False
        assert user.password_hash == before, "the hash changed although no epoch was recorded"
        assert "password epoch not recorded" in caplog.text
    finally:
        password_epoch.reset_epoch_store()


_USERS_DSN, _EPOCH_DSN = "postgresql://h:5432/slm_users", "postgresql://h:5432/slm"


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params):
        self.conn.log.append((self.conn.dsn, "execute", sql.split()[0], params))

    def fetchone(self):
        return (1,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, dsn, log):
        self.dsn, self.log = dsn, log

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.log.append((self.dsn, "commit"))

    def close(self):
        return None


def _admin_module(monkeypatch, log):
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda dsn: _Conn(dsn, log)))
    monkeypatch.setitem(
        sys.modules, "bcrypt", types.SimpleNamespace(hashpw=lambda pw, salt: b"hashed", gensalt=lambda rounds: b"s")
    )
    spec = importlib.util.spec_from_file_location("autobot_admin_18672", _ADMIN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "_secrets_env",
        lambda: {
            "SLM_USERS_DATABASE_URL": _USERS_DSN.replace("postgresql://", "postgresql+asyncpg://"),
            "SLM_DATABASE_URL": _EPOCH_DSN.replace("postgresql://", "postgresql+asyncpg://"),
        },
    )
    return module


def test_cli_reset_writes_each_row_to_its_own_database_epoch_first(monkeypatch, epochs) -> None:
    """01's review: users and epochs are separate databases (SLM_USERS_DATABASE_URL vs
    SLM_DATABASE_URL); the epoch must reach the epoch DB and commit before the hash does."""
    log: list = []
    module = _admin_module(monkeypatch, log)
    monkeypatch.setattr(sys, "stdin", io.StringIO(_throwaway() + "\n"))  # not a TTY: one line
    issued = int(time.time()) - 5
    module.cmd_reset_password(types.SimpleNamespace(username="operator"))
    writes = [e for e in log if e[1] == "execute"]
    assert [(e[0], e[2]) for e in writes] == [(_USERS_DSN, "SELECT"), (_EPOCH_DSN, "INSERT"), (_USERS_DSN, "UPDATE")]
    assert log.index((_EPOCH_DSN, "commit")) < log.index((_USERS_DSN, "commit")), "the hash committed first"
    subject, epoch = writes[1][3]
    assert subject == "operator" and epoch >= issued
    epochs[subject] = epoch  # what the upsert wrote, as the SLM's store reads it back
    assert _revoked("operator", issued), "a token issued before the CLI reset still works"


def test_cli_takes_no_password_on_the_command_line() -> None:
    text = _ADMIN_SCRIPT.read_text(encoding="utf-8")
    assert "new_password" not in text, "a password argument is visible in ps and shell history"


def test_the_secrets_file_takes_a_backslash_password_literally(monkeypatch, tmp_path) -> None:
    """27's review: a password used as an re.sub replacement had a backslash or backreference misread."""
    module = _admin_module(monkeypatch, [])
    secrets = tmp_path / "slm-secrets.env"
    secrets.write_text("OTHER=1\nSLM_ADMIN_PASSWORD=old\n", encoding="utf-8")
    value = _throwaway() + "\\1\\"
    module._sync_secrets_file("admin", value, str(secrets))
    assert f"SLM_ADMIN_PASSWORD={value}\n" in secrets.read_text(encoding="utf-8")


def test_cli_reads_env_files_with_the_one_shared_parser(monkeypatch, tmp_path) -> None:
    """#19232: the CLI's own quote-stripping copy is gone; it imports autobot_shared.env_file."""
    from autobot_shared import env_file

    module = _admin_module(monkeypatch, [])
    assert module.parse_env_text is env_file.parse_env_text
    env = tmp_path / "slm.env"
    env.write_text('A="2" # note\nB=a#b\nC=x # c\nD="q\n\n# skip\n', encoding="utf-8")
    assert module.load_env_file(str(env)) == env_file.parse_env_text(env.read_text(encoding="utf-8"))
    assert module.load_env_file(str(tmp_path / "absent.env")) == {}


def test_cli_without_autobot_shared_exits_with_the_install_root_not_a_traceback(monkeypatch) -> None:
    """#19232 review: a host the slm_manager role has not synced gets a message, not an ImportError."""
    from autobot_shared.fleet_constants import FLEET_INSTALL_ROOT

    monkeypatch.setitem(sys.modules, "autobot_shared.env_file", None)  # import of it now raises ImportError
    with pytest.raises(SystemExit) as exited:
        _admin_module(monkeypatch, [])
    message = str(exited.value.code)
    assert str(FLEET_INSTALL_ROOT) in message and "slm_manager role" in message and "builtin updater" in message
