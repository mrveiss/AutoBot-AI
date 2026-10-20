# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18953: the LangGraph checkpointer's Redis URL comes from the SSOT builder.

Scheme, ACL credentials, TLS port and db index are asserted against a config
built from a controlled environment; the TLS-off / TLS-on pair contrasts the
scheme and port. No log record may carry the password.
"""

import logging
import os
import ssl
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import pytest

from autobot_shared import tls as shared_tls
from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_config import AutoBotConfig
from autobot_shared.tls import resolve_redis_mtls_paths
from chat_workflow import checkpointer_connection as cc

_PASSWORD = "pw-18953-s3cret"  # pragma: allowlist secret
_USER = "chat-acl-user"
_BASE_ENV = {"AUTOBOT_REDIS_PASSWORD": _PASSWORD, "AUTOBOT_REDIS_USERNAME": _USER}


def _config(tls: bool) -> AutoBotConfig:
    env = dict(_BASE_ENV, AUTOBOT_REDIS_TLS_ENABLED="true" if tls else "false")
    with patch.dict(os.environ, env, clear=True):
        return AutoBotConfig(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def plain(monkeypatch):
    cfg = _config(tls=False)
    monkeypatch.setattr(cc, "ssot", cfg)
    return cfg


@pytest.fixture
def secure(monkeypatch):
    monkeypatch.delenv("AUTOBOT_SKIP_TLS_VERIFY", raising=False)
    cfg = _config(tls=True)
    monkeypatch.setattr(cc, "ssot", cfg)
    return cfg


def test_tls_off_uses_redis_scheme_with_ssot_credentials_and_db(plain) -> None:
    url, args = cc.get_checkpointer_connection()
    parts = urlsplit(url)
    assert parts.scheme == "redis"
    assert unquote(parts.username) == _USER
    assert unquote(parts.password) == _PASSWORD
    assert parts.hostname == plain.vm.redis
    assert parts.port == plain.port.redis
    assert parts.path == f"/{DATABASE_MAPPING[cc.CHECKPOINTER_DB_NAME]}"
    assert url == plain.get_redis_url_for_db(DATABASE_MAPPING[cc.CHECKPOINTER_DB_NAME])
    assert args == {}


def test_tls_on_uses_rediss_scheme_tls_port_and_ssl_args(secure, monkeypatch) -> None:
    # Hermetic: the real context loads cert files this checkout may not have.
    strict = SimpleNamespace(verify_mode=ssl.CERT_REQUIRED, check_hostname=True)
    monkeypatch.setattr(shared_tls, "get_internal_tls_context", lambda **_: strict)
    url, args = cc.get_checkpointer_connection()
    parts = urlsplit(url)
    assert parts.scheme == "rediss"
    assert parts.port == secure.tls.redis_tls_port
    assert unquote(parts.username) == _USER
    assert unquote(parts.password) == _PASSWORD
    assert set(args) >= {"ssl_ca_certs", "ssl_certfile", "ssl_keyfile"}
    assert args["ssl_cert_reqs"] == "required"
    assert args["ssl_check_hostname"] is True


@pytest.mark.parametrize(
    "verify_mode, check_hostname, reqs",
    [(ssl.CERT_REQUIRED, True, "required"), (ssl.CERT_NONE, False, "none")],
)
def test_ssl_args_mirror_the_shared_context_policy(secure, monkeypatch, verify_mode, check_hostname, reqs) -> None:
    """Hostname and cert policy are celery's: whatever get_internal_tls_context sets, never hardcoded."""
    ctx = SimpleNamespace(verify_mode=verify_mode, check_hostname=check_hostname)
    monkeypatch.setattr(shared_tls, "get_internal_tls_context", lambda **_: ctx)
    args = cc.get_checkpointer_connection()[1]
    assert args["ssl_cert_reqs"] == reqs
    assert args["ssl_check_hostname"] is check_hostname


def test_tls_off_has_no_ssl_args(plain) -> None:
    assert cc.get_checkpointer_connection()[1] == {}


def test_skip_verify_opt_out_is_mirrored_not_hardcoded(secure, monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_SKIP_TLS_VERIFY", "true")
    monkeypatch.delenv("AUTOBOT_TLS_CA_PATH", raising=False)
    args = cc.get_checkpointer_connection()[1]
    assert args["ssl_check_hostname"] is False
    assert args["ssl_cert_reqs"] == "none"


def test_mtls_paths_use_explicit_settings_before_cert_dir(monkeypatch) -> None:
    cfg = _config(tls=True)
    monkeypatch.setattr(cfg.misc, "tls_ca_path", "/x/ca.pem")
    monkeypatch.setattr(cfg.misc, "tls_cert_path", "/x/c.pem")
    monkeypatch.setattr(cfg.misc, "tls_key_path", "/x/k.pem")
    monkeypatch.setattr("autobot_shared.ssot_config.config", cfg)
    assert resolve_redis_mtls_paths() == ("/x/ca.pem", "/x/c.pem", "/x/k.pem")
    monkeypatch.setattr(cfg.misc, "tls_key_path", "")
    ca, cert, key = resolve_redis_mtls_paths()
    assert ca.endswith("ca/ca-cert.pem") and key.endswith("main-host/server-key.pem")


def test_describe_connection_masks_credentials(plain) -> None:
    url, _ = cc.get_checkpointer_connection()
    shown = cc.describe_connection(url)
    assert _PASSWORD not in shown
    assert _USER not in shown
    assert urlsplit(shown).hostname == plain.vm.redis


@pytest.mark.asyncio
async def test_no_log_record_contains_the_password(plain, monkeypatch, caplog) -> None:
    import chat_workflow.graph as graph

    captured = {}

    class _FakeSaver:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def asetup(self):
            return None

    monkeypatch.setattr(graph, "_ssot_config", plain)
    monkeypatch.setattr(graph, "AsyncRedisSaver", _FakeSaver, raising=False)
    monkeypatch.setattr(graph, "_REDIS_CHECKPOINTER_AVAILABLE", True)
    monkeypatch.setattr(graph, "_checkpointer", None)
    with caplog.at_level(logging.DEBUG):
        await graph.get_redis_checkpointer()
    assert _PASSWORD in captured["redis_url"]  # the saver does get the real URL
    assert caplog.records, "expected the init log line"
    for record in caplog.records:
        assert _PASSWORD not in record.getMessage()
        assert _PASSWORD not in str(record.args)


@pytest.mark.asyncio
async def test_failed_setup_leaks_no_password_and_caches_nothing(plain, monkeypatch, caplog) -> None:
    import chat_workflow.graph as graph

    class _FailingSaver:
        def __init__(self, **kwargs):
            self.url = kwargs["redis_url"]

        async def asetup(self):
            raise ConnectionError(f"cannot reach {self.url}")

        async def adelete_thread(self, thread_id):  # pragma: no cover - never reached
            raise AssertionError

    monkeypatch.setattr(graph, "_ssot_config", plain)
    monkeypatch.setattr(graph, "AsyncRedisSaver", _FailingSaver, raising=False)
    monkeypatch.setattr(graph, "_REDIS_CHECKPOINTER_AVAILABLE", True)
    monkeypatch.setattr(graph, "_checkpointer", None)
    with caplog.at_level(logging.DEBUG):
        await graph.delete_thread_checkpoints("thread-1")
    assert graph._checkpointer is None
    assert any("Failed to clear checkpoints" in r.getMessage() for r in caplog.records)
    for record in caplog.records:
        assert _PASSWORD not in record.getMessage()
        assert _PASSWORD not in str(record.args)
