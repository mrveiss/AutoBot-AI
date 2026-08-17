# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /health must reflect Redis, not just Postgres (#14299).

Before this fix, ``api/health.py``'s ``/health`` endpoint checked ONLY the SQL
database. A backend whose circuit breaker was permanently open on its 'main'
Redis database (see ``connection_manager_pool_test.py`` for the "log once,
open once" half of #14299) still reported ``status="healthy"`` — the node
stayed ``online`` and this endpoint answered normally, which is exactly the
"invisible to every roll-up" shape the issue reports.

``_check_redis_health`` also has to distinguish a config error ("resolved to
nothing configured" — will not fix itself without an operator setting
REDIS_HOST/vm.redis) from every other reason a client can be unavailable
(disabled, transient connection failure) — collapsing both into a bare
"unhealthy" is the same undiagnosable-status shape #14299 calls out for the
log line itself.

Real-load prologue (pattern: tests/api/test_drift_resolve.py): the root
conftest stubs ``models.schemas`` as a MagicMock, and FastAPI validates
``response_model=HealthResponse`` at *decoration* time — importing
``api/health.py`` under the stub raises there, before a single test runs.
This module swaps in the REAL ``models.schemas`` (pydantic model, decoration
succeeds), execs a private copy of ``api/health.py`` against it, and restores
the stub — ``models.database`` / ``services.auth`` / ``services.database``
stay stubbed throughout, since every handler under test here is called
directly with an explicit ``db`` stand-in and never actually reaches them.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# #14299: models.schemas has a real field annotated `NodeStatus | None`
# (line ~178) sourced from models.database — loading schemas.py with
# models.database still stubbed makes that annotation a MagicMock, and
# pydantic cannot build a validator for it. Both must be real together,
# exactly like tests/api/test_drift_resolve.py's swap list.
_SWAP_KEYS = ("models.database", "models.schemas")


def _is_swap_key(name: str) -> bool:
    return name in _SWAP_KEYS or name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_orig_modules = {name: mod for name, mod in sys.modules.items() if _is_swap_key(name)}
for _name in list(_orig_modules):
    del sys.modules[_name]
try:
    for _name in ("sqlalchemy", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"):
        importlib.import_module(_name)

    _load_real_module("models.database", _BACKEND_ROOT / "models" / "database.py")
    _load_real_module("models.schemas", _BACKEND_ROOT / "models" / "schemas.py")

    _health_spec = importlib.util.spec_from_file_location("_health_redis_test", _BACKEND_ROOT / "api" / "health.py")
    health = importlib.util.module_from_spec(_health_spec)
    _health_spec.loader.exec_module(health)
finally:
    for _name in [name for name in sys.modules if _is_swap_key(name)]:
        del sys.modules[_name]
    for _name, _mod in _orig_modules.items():
        sys.modules[_name] = _mod


def _run(coro):
    """Run an async handler synchronously — matches tests/api/test_drift_resolve.py."""
    return asyncio.run(coro)


class TestCheckRedisHealth:
    def test_healthy_when_client_available(self, monkeypatch):
        async def _fake_client(database="main"):
            return object()

        monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _fake_client)

        assert _run(health._check_redis_health()) == "healthy"

    def test_configuration_error_is_distinguishable_from_generic_unhealthy(self, monkeypatch):
        """The failing path: a blank-host config error must not read the same
        as a transient connection failure — an operator needs to know which
        one they are looking at (#14299)."""

        async def _fake_client(database="main"):
            return None

        monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _fake_client)
        monkeypatch.setattr(
            "autobot_shared.redis_client.get_redis_health",
            lambda: {
                "databases": {
                    "main": {
                        "metrics": {
                            "last_error": (
                                "Redis host for database 'main' is empty — configuration "
                                "error (set REDIS_HOST / vm.redis); refusing to retry"
                            )
                        }
                    }
                }
            },
        )

        result = _run(health._check_redis_health())

        assert result != "unhealthy", "a config error collapsed into the generic bare status"
        assert "configuration error" in result

    def test_generic_connection_failure_stays_the_generic_status(self, monkeypatch):
        """The success path this test suite must not fake-pass on: a
        transient connection failure — not a config error — must NOT trip the
        "configuration error" branch (verify against the reproduction AND the
        case that must stay caught, not just the reported one)."""

        async def _fake_client(database="main"):
            return None

        monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _fake_client)
        monkeypatch.setattr(
            "autobot_shared.redis_client.get_redis_health",
            lambda: {"databases": {"main": {"metrics": {"last_error": "Error 111 connecting to host:6379."}}}},
        )

        assert _run(health._check_redis_health()) == "unhealthy"

    def test_missing_metrics_do_not_raise(self, monkeypatch):
        """No prior call has touched 'main' yet — get_redis_health() has no
        entry for it. Must degrade to the generic status, never raise."""

        async def _fake_client(database="main"):
            return None

        monkeypatch.setattr("autobot_shared.redis_client.get_async_redis_client", _fake_client)
        monkeypatch.setattr("autobot_shared.redis_client.get_redis_health", lambda: {"databases": {}})

        assert _run(health._check_redis_health()) == "unhealthy"


class TestHealthCheckEndpoint:
    def test_degrades_when_redis_is_unhealthy_even_if_db_is_fine(self, monkeypatch):
        """The endpoint-level invariant: Postgres alone can no longer make
        /health say "healthy" — Redis has to agree too (#14299)."""

        class _FakeScalarResult:
            def scalar(self):
                return 1

        class _FakeDB:
            async def execute(self, *_a, **_kw):
                return _FakeScalarResult()

        async def _unhealthy_redis():
            return "unhealthy"

        monkeypatch.setattr(health, "_check_redis_health", _unhealthy_redis)

        result = _run(health.health_check(db=_FakeDB()))

        assert result.database == "healthy"
        assert result.redis == "unhealthy"
        assert result.status != "healthy", "Postgres-only health must not mask a broken Redis"

    def test_healthy_when_both_db_and_redis_agree(self, monkeypatch):
        class _FakeScalarResult:
            def scalar(self):
                return 1

        class _FakeDB:
            async def execute(self, *_a, **_kw):
                return _FakeScalarResult()

        async def _healthy_redis():
            return "healthy"

        monkeypatch.setattr(health, "_check_redis_health", _healthy_redis)

        result = _run(health.health_check(db=_FakeDB()))

        assert result.status == "healthy"
