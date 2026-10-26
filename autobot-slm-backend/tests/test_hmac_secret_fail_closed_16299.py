# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""API-key pepper: no published default, transparent legacy migration (#16299).

conftest stubs ``config`` and sibling modules, so the real ``api_key_service``
source is loaded by path against a stand-in ``settings`` and an in-memory
"table" of key hashes.
"""

import asyncio
import hashlib
import hmac
import importlib.util
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from testkit.fake_async_session import FakeAsyncSession

_ROOT = Path(__file__).resolve().parents[1]
_VAR = "SLM_HMAC_API_KEY_SECRET"
_LITERAL = "autobot-api-key-v1"


class _IntegrityError(Exception):
    pass


class _Store:
    """In-memory stand-in for the main-DB SystemSecret table plus the System vault."""

    def __init__(self, stored=None):
        self.rows = {}
        if stored is not None:
            self.rows["slm_hmac_api_key_secret"] = stored
        self.events = []
        self.sessions_opened = 0
        self.race_value = None  # set => the next insert loses to this operator value

    async def retrieve_secret(self, session, key):
        assert isinstance(session, _FakeSession), "must read the main-DB session"
        return self.rows.get(key)

    async def mirror_secret_to_vault(self, key, value):
        self.events.append("mirror")
        return True

    def session(self):
        self.sessions_opened += 1
        return _SessionCtx(_FakeSession(self))


class _SessionCtx:
    def __init__(self, sess):
        self.sess = sess

    async def __aenter__(self):
        return self.sess

    async def __aexit__(self, *exc):
        return False


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession(FakeAsyncSession):
    """Canonical fake (#18883) whose ``add`` replays an insert race against ``store``."""

    def __init__(self, store):
        super().__init__()
        self.store = store

    def begin_nested(self):
        return _Nested()

    def add(self, row):
        if self.store.race_value is not None:
            self.store.rows[row.key] = self.store.race_value
            raise _IntegrityError()
        self.store.rows[row.key] = row.encrypted_value

    async def commit(self):
        self.store.events.append("commit")

    async def rollback(self):
        self.store.events.append("rollback")


class _CallerSession(FakeAsyncSession):
    """The slm_users session APIKeyService is given: any use is a bug (#19117 review).

    Extends the canonical fake (#18883) but refuses every public attribute except ``flush``,
    so an inherited ``execute``/``add``/``get`` cannot silently serve the service.
    """

    async def flush(self, objects=None):  # the service's own row updates are legitimate
        return None

    def __getattribute__(self, name):
        if name.startswith("_") or name == "flush":
            return object.__getattribute__(self, name)
        raise AssertionError(f"caller's slm_users session was used: {name}")


def _load(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, _ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def svc(monkeypatch):
    cfg = SimpleNamespace(hmac_api_key_secret="")
    store = _Store()
    fakes = {
        "config": SimpleNamespace(settings=cfg),
        "sqlalchemy.exc": SimpleNamespace(IntegrityError=_IntegrityError),
        "services.database": SimpleNamespace(db_service=SimpleNamespace(session=store.session)),
        "models.database": SimpleNamespace(SystemSecret=lambda **kw: SimpleNamespace(**kw)),
        "services.encryption": SimpleNamespace(encrypt_data=lambda v: v),
        "services.system_secrets_vault": SimpleNamespace(
            retrieve_secret=store.retrieve_secret,
            mirror_secret_to_vault=store.mirror_secret_to_vault,
        ),
        "user_management.models.api_key": SimpleNamespace(APIKey=object),
        "user_management.services.base_service": SimpleNamespace(BaseService=object),
    }
    for name, mod in fakes.items():
        m = types.ModuleType(name)
        m.__dict__.update(vars(mod))
        monkeypatch.setitem(sys.modules, name, m)
    pepper = _load("_api_key_pepper_19120", "services/api_key_pepper.py", monkeypatch)
    pepper.invalidate_pepper_cache()
    monkeypatch.setitem(sys.modules, "services.api_key_pepper", pepper)
    mod = _load("_api_key_service_16299", "user_management/services/api_key_service.py", monkeypatch)
    return mod, cfg, store, pepper


def _resolve(pepper):
    return asyncio.run(pepper.resolve_hmac_api_key_secret())


def _hm(secret: str, key: str) -> str:
    return hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()


def _service(mod, rows, store):
    """Service whose lookup is an in-memory dict of hash -> row."""
    s = mod.APIKeyService.__new__(mod.APIKeyService)
    s.session = _CallerSession()

    async def find(h):
        return rows.get(h)

    s._find_by_hash = find
    return s


async def _noop():
    return None


def _row():
    return SimpleNamespace(id=1, key_hash="", is_valid=True, record_usage=lambda: None)


def test_config_default_is_empty():
    src = (_ROOT / "config.py").read_text(encoding="utf-8")
    assert 'os.getenv("SLM_HMAC_API_KEY_SECRET", "")' in src
    assert _LITERAL not in src


def test_store_value_wins_over_env(svc):
    _, cfg, store, pepper = svc
    store.rows[pepper.HMAC_PEPPER_KEY] = "from-store"  # pragma: allowlist secret
    cfg.hmac_api_key_secret = "from-env"  # pragma: allowlist secret
    assert _resolve(pepper) == "from-store"
    assert store.rows[pepper.HMAC_PEPPER_KEY] == "from-store"
    assert "mirror" not in store.events


def test_env_only_imports_once_and_never_logs_value(svc, caplog):
    _, cfg, store, pepper = svc
    cfg.hmac_api_key_secret = "env-pepper-value"  # pragma: allowlist secret
    with caplog.at_level(logging.DEBUG):
        assert _resolve(pepper) == "env-pepper-value"
        assert store.rows[pepper.HMAC_PEPPER_KEY] == "env-pepper-value"
        assert store.events == ["commit", "mirror"]  # mirror only after the commit
        # second call after the cache is dropped reads the store: no re-import
        pepper.invalidate_pepper_cache()
        assert _resolve(pepper) == "env-pepper-value"
    assert store.events == ["commit", "mirror"]
    assert caplog.text.count("imported SLM_HMAC_API_KEY_SECRET") == 1
    assert "env-pepper-value" not in caplog.text


def test_neither_set_fails_closed_and_warning_names_the_page(svc, caplog):
    mod, _, store, pepper = svc
    s = _service(mod, {}, store)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(mod.APIKeyPepperNotConfiguredError, match=pepper.SECRETS_PAGE_PATH) as exc:
            asyncio.run(s.create_key(None, "n", []))
    assert pepper.HMAC_PEPPER_KEY in str(exc.value) and _LITERAL not in str(exc.value)
    assert pepper.SECRETS_PAGE_PATH in caplog.text and pepper.HMAC_PEPPER_KEY in caplog.text
    assert store.rows == {}


def test_new_hash_never_uses_the_literal(svc):
    mod, *_ = svc
    h = mod.APIKeyService._hash_key("abot_x", "s1")  # pragma: allowlist secret
    assert h == _hm("s1", "abot_x") and h != _hm(_LITERAL, "abot_x")
    with pytest.raises(RuntimeError):
        mod.APIKeyService._hash_key("abot_x", "")


def test_literal_hashed_key_verifies_and_is_rehashed(svc):
    mod, _, store, pepper = svc
    store.rows[pepper.HMAC_PEPPER_KEY] = "s1"  # pragma: allowlist secret
    row = _row()
    row.key_hash = _hm(_LITERAL, "abot_x")
    s = _service(mod, {row.key_hash: row}, store)
    assert asyncio.run(s.validate_key("abot_x")) is row
    assert row.key_hash == _hm("s1", "abot_x")


def test_bare_sha256_key_still_verifies_and_is_rehashed(svc):
    mod, _, store, pepper = svc
    store.rows[pepper.HMAC_PEPPER_KEY] = "s1"  # pragma: allowlist secret
    row = _row()
    row.key_hash = hashlib.sha256(b"abot_x").hexdigest()
    s = _service(mod, {row.key_hash: row}, store)
    assert asyncio.run(s.validate_key("abot_x")) is row
    assert row.key_hash == _hm("s1", "abot_x")


def test_no_pepper_verify_works_warns_and_does_not_rehash(svc, caplog):
    mod, _, store, pepper = svc
    row = _row()
    row.key_hash = _hm(_LITERAL, "abot_x")
    old = row.key_hash
    s = _service(mod, {old: row}, store)
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(s.validate_key("abot_x")) is row
    assert row.key_hash == old
    assert pepper.SECRETS_PAGE_PATH in caplog.text and _LITERAL not in caplog.text


def test_rotation_is_not_supported_old_pepper_hash_stops_verifying(svc):
    """Documented limitation: the store keeps ONE value, so no dual-verify window."""
    mod, _, store, pepper = svc
    store.rows[pepper.HMAC_PEPPER_KEY] = "old"  # pragma: allowlist secret
    row = _row()
    row.key_hash = _hm("old", "abot_x")
    s = _service(mod, {row.key_hash: row}, store)
    store.rows[pepper.HMAC_PEPPER_KEY] = "new"  # pragma: allowlist secret
    pepper.invalidate_pepper_cache()
    assert asyncio.run(s.validate_key("abot_x")) is None


def test_resolver_uses_the_main_db_session_not_the_callers(svc):
    mod, _, store, pepper = svc
    store.rows[pepper.HMAC_PEPPER_KEY] = "s1"  # pragma: allowlist secret
    row = _row()
    row.key_hash = _hm(_LITERAL, "abot_x")
    s = _service(mod, {row.key_hash: row}, store)  # session = _CallerSession (raises on use)
    assert asyncio.run(s.validate_key("abot_x")) is row
    assert store.sessions_opened == 1
    import inspect

    assert not inspect.signature(pepper.resolve_hmac_api_key_secret).parameters


def test_race_loser_uses_the_stored_value_not_its_env_value(svc):
    _, cfg, store, pepper = svc
    cfg.hmac_api_key_secret = "env-value"  # pragma: allowlist secret
    store.race_value = "operator-value"  # pragma: allowlist secret
    assert _resolve(pepper) == "operator-value"
    assert "mirror" not in store.events and "rollback" in store.events


def test_resolution_is_cached_until_invalidated_and_warns_once(svc, caplog):
    _, _, store, pepper = svc
    with caplog.at_level(logging.WARNING):
        for _i in range(3):
            assert _resolve(pepper) is None
    assert store.sessions_opened == 1
    assert caplog.text.count(pepper.SECRETS_PAGE_PATH) == 1
    store.rows[pepper.HMAC_PEPPER_KEY] = "s1"  # pragma: allowlist secret
    pepper.invalidate_pepper_cache()
    assert _resolve(pepper) == "s1" and store.sessions_opened == 2


def test_literal_lives_only_in_the_named_constant():
    src = (_ROOT / "user_management/services/api_key_service.py").read_text(encoding="utf-8")
    assert src.count(_LITERAL) == 1
    assert f'_LEGACY_PUBLIC_PEPPER = "{_LITERAL}"' in src
