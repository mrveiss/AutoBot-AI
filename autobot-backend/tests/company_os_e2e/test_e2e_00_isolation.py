# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scenario's isolation contract (#19253), tested without booting anything.

A developer's shell may export the URL of a live database or Redis. Neither the migration
subprocess nor the server may inherit it.
"""

import re
from pathlib import Path

import pytest

from tests.company_os_e2e import _stack as stack

pytestmark = pytest.mark.e2e

SCRATCH = stack.Endpoints(
    "pg.scratch.invalid", 5555, "scratch", "scratch-pw", "redis.scratch.invalid", 6666
)  # pragma: allowlist secret
LIVE = "live.example.invalid"
HOSTILE = {
    "AUTOBOT_DATABASE_URL": f"postgresql://x@{LIVE}/live",
    "AUTOBOT_REDIS_URL": f"redis://{LIVE}:6379",
    "AUTOBOT_REDIS_HOST": LIVE,
    "AUTOBOT_SLM_HOST": LIVE,
    "AUTOBOT_OLLAMA_ENDPOINT": f"http://{LIVE}:11434",
    "REDIS_URL": f"redis://{LIVE}",
    "REDISCLI_AUTH": "live",  # pragma: allowlist secret
    "POSTGRES_PASSWORD": "live",  # pragma: allowlist secret
    "PGHOST": LIVE,
    "PGPASSWORD": "live",  # pragma: allowlist secret
    "OLLAMA_HOST": LIVE,
    "OLLAMA_MODELS": "/live",
    "LLC_AGENT_API_BASE_URL": f"http://{LIVE}/api",
    "LLC_DEFAULT_BUDGET_LIMIT": "999999",
}
STRIPPED = re.compile(r"^(AUTOBOT_|REDIS|POSTGRES|PG|OLLAMA|LLC_)")


@pytest.fixture
def hostile_env(monkeypatch):  # noqa: ANN001, ANN201
    for name, value in HOSTILE.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", "/usr/bin")


def _leaks(env: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in env.items() if LIVE in v or v in ("live", "/live", "999999")]


def test_clean_env_keeps_only_the_allowlist(hostile_env):  # noqa: ANN001
    env = stack.clean_env()
    assert set(env) <= set(stack.ENV_ALLOWLIST)
    assert env["PATH"] == "/usr/bin"
    assert not [k for k in env if STRIPPED.match(k)]


def test_server_env_cannot_be_steered_by_the_callers_shell(hostile_env, tmp_path):  # noqa: ANN001
    env = stack._server_env(SCRATCH, "scratchdb", 7777, tmp_path / "stub.jsonl", tmp_path)
    assert not _leaks(env)
    assert SCRATCH.redis_host in env["AUTOBOT_REDIS_URL"] and env["AUTOBOT_REDIS_HOST"] == SCRATCH.redis_host
    assert env["AUTOBOT_DATABASE_URL"] == SCRATCH.sqlalchemy_url("scratchdb")
    assert env["LLC_AGENT_API_BASE_URL"].endswith(":7777/api")
    assert "LLC_DEFAULT_BUDGET_LIMIT" not in env and "REDIS_URL" not in env and "PGHOST" not in env
    assert env["HOME"] == str(tmp_path)


def test_migration_env_cannot_be_steered_by_the_callers_shell(hostile_env, tmp_path):  # noqa: ANN001
    env = stack._alembic_env(SCRATCH, "scratchdb", tmp_path)
    assert not _leaks(env)
    assert env["AUTOBOT_DATABASE_URL"] == SCRATCH.sqlalchemy_url("scratchdb")
    assert not [k for k in env if STRIPPED.match(k) and k != "AUTOBOT_DATABASE_URL"]


def test_refuses_a_redis_that_holds_data(monkeypatch):  # noqa: ANN001
    monkeypatch.setattr(stack, "redis_is_empty", lambda ep: False)
    with pytest.raises(RuntimeError, match="not empty"):
        stack.require_scratch_services(SCRATCH)
    monkeypatch.setattr(stack, "redis_is_empty", lambda ep: True)
    stack.require_scratch_services(SCRATCH)


def test_teardown_runs_every_step_and_reports_the_first_failure(monkeypatch, tmp_path):  # noqa: ANN001
    calls: list[str] = []

    def boom(*_a):  # noqa: ANN002
        calls.append("process")
        raise RuntimeError("process would not die")

    monkeypatch.setattr(stack, "_end_process", boom)
    monkeypatch.setattr(stack, "keep_logs", lambda *a: calls.append("logs"))
    monkeypatch.setattr(stack, "_remove_database", lambda *a: calls.append("database"))
    monkeypatch.setattr(stack, "_remove_role", lambda *a: calls.append("role"))
    with pytest.raises(RuntimeError, match="would not die"):
        stack._teardown(SCRATCH, SCRATCH, "db", object(), (Path(tmp_path / "a"), Path(tmp_path / "b")))
    assert calls == ["process", "logs", "database", "role"]
