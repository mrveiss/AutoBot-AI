# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's revocation state lives in its own PostgreSQL, and stays fail-closed (#18663).

A completed SLM install could not log in: the jti denylist and the password epoch
lived in Redis, the SLM host has no Redis (the SLM is what deploys it), and the
checks fail closed (#16387). These pin:

- the denylist and epoch stores answer from the SLM database, and refuse (raise)
  when it cannot answer -- "unknown" is never read as "not revoked";
- writes stay fail-open, matching the Redis stores they replace;
- the shared password-epoch rule routes to the installed store, and its own
  fail-closed handling applies to the store's refusal;
- neither SLM store module reaches for Redis at all.

**What these do not cover.** No PostgreSQL runs here: sessions are fakes and the
SQL is checked as compiled text. A login on a fresh SLM host is the end-to-end proof.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from testkit.fake_async_session import FakeAsyncSession

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
for _p in (str(_BACKEND), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autobot_shared.user_management import password_epoch  # noqa: E402
from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: E402

# The slm-backend root conftest stubs ``sqlalchemy`` for the whole suite. Swap the REAL
# package in only while the modules under test (and the stand-in models) are built, then
# restore the stubs -- the system_secrets_vault_test.py pattern. The loaded modules keep
# their bindings to the real select/insert/delete/postgresql objects.
_SWAP = ("sqlalchemy",)


def _swapped(name: str) -> bool:
    return any(name == p or name.startswith(p + ".") for p in _SWAP)


_orig = {n: m for n, m in sys.modules.items() if _swapped(n)}
for _n in list(_orig):
    del sys.modules[_n]
try:
    for _n in ("sqlalchemy", "sqlalchemy.orm", "sqlalchemy.exc", "sqlalchemy.dialects.postgresql"):
        importlib.import_module(_n)
    from sqlalchemy import BigInteger, Column, DateTime, String
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import declarative_base

    _Base = declarative_base()

    class _RevokedToken(_Base):
        __tablename__ = "slm_revoked_tokens"
        jti = Column(String(64), primary_key=True)
        expires_at = Column(DateTime(timezone=True), nullable=False)

    class _PasswordEpoch(_Base):
        __tablename__ = "slm_password_epochs"
        subject = Column(String(255), primary_key=True)
        epoch = Column(BigInteger, nullable=False)

    def _load(name: str):
        spec = importlib.util.spec_from_file_location(f"_{name}_18663", _BACKEND / "services" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _dl = _load("token_denylist")
    _pe = _load("password_epoch_store")
    _REAL_SQLALCHEMY = {n: m for n, m in sys.modules.items() if _swapped(n)}
finally:
    for _n in [n for n in sys.modules if _swapped(n)]:
        del sys.modules[_n]
    sys.modules.update(_orig)


class _FakeSession(FakeAsyncSession):
    """One answer for every query: the row `first()` returns, or else the value `scalar_one_or_none()` returns."""

    def __init__(self, first=None, scalar=None, hang: float = 0.0):
        answer = first if first is not None else scalar
        super().__init__(default_result=[] if answer is None else [answer])
        self._hang = hang

    async def execute(self, stmt, *args, **kwargs):
        if self._hang:
            await asyncio.sleep(self._hang)
        return await super().execute(stmt, *args, **kwargs)

    def sql(self) -> list[str]:
        return [str(s.compile(dialect=postgresql.dialect())) for s in self.statements]


@pytest.fixture
def store(monkeypatch):
    """Point both modules at a fake session and the stand-in models."""
    models = types.ModuleType("models.auth_revocation")
    models.RevokedToken, models.PasswordEpoch = _RevokedToken, _PasswordEpoch
    monkeypatch.setitem(sys.modules, "models.auth_revocation", models)
    for name, module in _REAL_SQLALCHEMY.items():  # the stores' lazy imports run at call time
        monkeypatch.setitem(sys.modules, name, module)
    holder = {"session": _FakeSession()}

    @asynccontextmanager
    async def _session_cm():
        yield holder["session"]

    monkeypatch.setattr(_dl, "_session", _session_cm)
    monkeypatch.setattr(_pe, "_session", _session_cm)
    return holder


def _unavailable(monkeypatch, exc: Exception):
    def _raise():
        raise exc

    monkeypatch.setattr(_dl, "_session", _raise)
    monkeypatch.setattr(_pe, "_session", _raise)


# --- jti denylist -------------------------------------------------------------------------


async def test_a_listed_unexpired_jti_is_revoked(store):
    store["session"] = _FakeSession(first=("abc",))
    assert await _dl.is_jti_revoked("abc") is True
    (sql,) = store["session"].sql()
    assert "slm_revoked_tokens.jti =" in sql and "slm_revoked_tokens.expires_at >" in sql


async def test_an_unlisted_jti_is_not_revoked(store):
    store["session"] = _FakeSession(first=None)
    assert await _dl.is_jti_revoked("abc") is False


async def test_the_check_refuses_when_the_database_cannot_answer(store, monkeypatch):
    """Fail-closed (#16387): an unavailable store raises, it never reads as "not revoked"."""
    _unavailable(monkeypatch, ConnectionError("SLM database not initialized"))
    with pytest.raises(ConnectionError):
        await _dl.is_jti_revoked("abc")


async def test_a_database_error_is_refused_as_store_unavailable(store, monkeypatch):
    """A DB error must reach auth.py as ConnectionError (401), not escape as a 500."""

    async def _boom(stmt):
        raise _dl.SQLAlchemyError("connection lost")

    store["session"].execute = _boom
    with pytest.raises(ConnectionError):
        await _dl.is_jti_revoked("abc")


async def test_a_raw_driver_error_is_refused_as_store_unavailable(store):
    """asyncpg can raise before SQLAlchemy wraps it; that must still be a 401, not a 500."""
    if not _dl._DRIVER_FAILURES:
        pytest.skip("asyncpg is not installed here")

    async def _boom(stmt):
        raise _dl._DRIVER_FAILURES[1]("connection was closed")

    store["session"].execute = _boom
    with pytest.raises(ConnectionError):
        await _dl.is_jti_revoked("abc")


async def test_the_check_refuses_when_the_database_is_too_slow(store, monkeypatch):
    monkeypatch.setattr(_dl, "_STORE_DEADLINE_SECONDS", 0.05)
    store["session"] = _FakeSession(hang=1.0)
    with pytest.raises(asyncio.TimeoutError):
        await _dl.is_jti_revoked("abc")


async def test_revoking_inserts_prunes_and_commits(store):
    await _dl.revoke_jti("abc", ttl_seconds=60)
    insert_sql, prune_sql = store["session"].sql()
    assert insert_sql.startswith("INSERT INTO slm_revoked_tokens") and "ON CONFLICT (jti) DO UPDATE" in insert_sql
    assert (
        "greatest(slm_revoked_tokens.expires_at, excluded.expires_at)" in insert_sql
    ), "a repeat revoke must never shorten"
    assert prune_sql.startswith("DELETE FROM slm_revoked_tokens") and "expires_at <=" in prune_sql
    assert store["session"].commits == 1


async def test_a_revocation_write_failure_does_not_raise(store, monkeypatch):
    """The write stays fail-open (#16387): logout cannot deny against anything else."""
    _unavailable(monkeypatch, ConnectionError("down"))
    await _dl.revoke_jti("abc", ttl_seconds=60)


async def test_the_ttl_is_clamped_to_at_least_one_second(monkeypatch):
    seen = {}

    async def _spy(jti, ttl):
        seen["ttl"] = ttl

    monkeypatch.setattr(_dl, "_revoke", _spy)
    await _dl.revoke_jti("abc", ttl_seconds=-5)
    assert seen["ttl"] == 1


# --- password epoch -----------------------------------------------------------------------


async def test_the_epoch_is_read_from_the_database(store):
    store["session"] = _FakeSession(scalar=1700000000)
    assert await _pe.get_epoch("admin") == 1700000000


async def test_an_unreadable_epoch_store_refuses(store, monkeypatch):
    _unavailable(monkeypatch, ConnectionError("down"))
    with pytest.raises(RevocationCheckUnavailable):
        await _pe.get_epoch("admin")


async def test_recording_an_epoch_upserts(store):
    assert await _pe.set_epoch("admin", now=1700000123) == 1700000123
    (sql,) = store["session"].sql()
    assert sql.startswith("INSERT INTO slm_password_epochs") and "ON CONFLICT (subject) DO UPDATE" in sql
    assert "greatest(slm_password_epochs.epoch, excluded.epoch)" in sql, "an epoch must never move backwards"


async def test_an_epoch_write_failure_returns_none(store, monkeypatch):
    _unavailable(monkeypatch, ConnectionError("down"))
    assert await _pe.set_epoch("admin", now=1) is None


@pytest.fixture
def installed(monkeypatch):
    password_epoch.reset_epoch_store()
    _pe.install()
    yield
    password_epoch.reset_epoch_store()


async def test_the_shared_rule_routes_to_the_installed_store(store, installed):
    store["session"] = _FakeSession(scalar=200)
    assert await password_epoch.is_token_revoked_by_password_change({"sub": "admin", "iat": 100}) is True
    store["session"] = _FakeSession(scalar=50)
    assert await password_epoch.is_token_revoked_by_password_change({"sub": "admin", "iat": 100}) is False


async def test_the_shared_rule_refuses_when_the_installed_store_cannot_answer(store, monkeypatch, installed):
    _unavailable(monkeypatch, ConnectionError("down"))
    with pytest.raises(RevocationCheckUnavailable):
        await password_epoch.is_token_revoked_by_password_change({"sub": "admin", "iat": 100})


async def test_the_shared_writer_routes_to_the_installed_store(store, installed):
    assert await password_epoch.set_password_epoch("admin", now=777) == 777
    assert store["session"].sql()[0].startswith("INSERT INTO slm_password_epochs")


def test_no_slm_revocation_store_reaches_for_redis():
    """The SLM deploys Redis; its own auth must not depend on it (#18663)."""
    for name in ("token_denylist", "password_epoch_store"):
        source = (_BACKEND / "services" / f"{name}.py").read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        assert "redis_client" not in code and "import redis" not in code, name
