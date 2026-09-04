# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behavioural test: ``logging.log_sql`` actually gates SQLAlchemy echo (#15587).

Before this fix, ``user_management/database.py`` hardcoded ``echo=False`` on
the app's only production async engine. ``services/config_service.py`` was
the *sole* reader of ``logging.log_sql`` in the whole tree -- the settings UI
toggle persisted a value to ``config.yaml`` and changed nothing.

These tests assert the actual behavioural consequence: whether the engine is
constructed with SQL echo on, driven by what config returns for
``logging.log_sql`` -- not merely that the value round-trips through a getter
(a test asserting that would pass against a toggle that does nothing, which
is the defect #15587 describes).
"""

from dataclasses import dataclass

import pytest

from user_management import database as user_db
from user_management.config import DeploymentMode, FeatureFlags


@dataclass
class _StubDeploymentConfig:
    """Minimal stand-in for ``DeploymentConfig`` -- postgres enabled, fixed URL."""

    mode: DeploymentMode = DeploymentMode.SINGLE_COMPANY
    features: FeatureFlags = None
    postgres_enabled: bool = True
    postgres_host: str = "test-host"
    postgres_port: int = 5432
    postgres_db: str = "test_db"
    postgres_user: str = "test_user"
    postgres_password: str = "test_pw"  # nosec B105 - test fixture, not a real credential

    def __post_init__(self):
        if self.features is None:
            self.features = FeatureFlags()

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@pytest.fixture(autouse=True)
def _isolate_engine_singleton(monkeypatch):
    """Reset the module-level engine singleton and stub its dependencies."""
    monkeypatch.setattr(user_db, "_async_engine", None)
    monkeypatch.setattr(user_db, "get_deployment_config", lambda: _StubDeploymentConfig())
    monkeypatch.setattr(
        user_db,
        "_get_pool_config",
        lambda: {"pool_size": 1, "max_overflow": 0, "pool_recycle": 60, "pool_timeout": 5},
    )
    yield


def _build_engine_and_capture_echo(monkeypatch, log_sql_value: bool) -> bool:
    """Build the engine with ``logging.log_sql`` stubbed, return the ``echo`` kwarg passed."""
    monkeypatch.setattr(
        user_db.config_manager,
        "get_nested",
        lambda key, default=None: log_sql_value if key == "logging.log_sql" else default,
    )

    captured = {}

    def _fake_create_async_engine(*_args, **kwargs):
        captured.update(kwargs)
        return "engine-sentinel"

    monkeypatch.setattr(user_db, "create_async_engine", _fake_create_async_engine)

    user_db.get_async_engine()
    return captured["echo"]


def test_log_sql_true_turns_on_engine_echo(monkeypatch):
    """Config saying log_sql=True must make the engine echo SQL statements."""
    assert _build_engine_and_capture_echo(monkeypatch, True) is True


def test_log_sql_false_keeps_engine_echo_off(monkeypatch):
    """Contrast case: config saying log_sql=False must NOT turn echo on.

    Without this, an engine that always echoed (regardless of config) would
    also pass the first test -- this pins the other side of the behaviour.
    """
    assert _build_engine_and_capture_echo(monkeypatch, False) is False


def test_sql_echo_enabled_reads_the_nested_key_not_a_flat_one(monkeypatch):
    """``ConfigManager.get()`` is a flat top-level lookup; a dotted string like
    "logging.log_sql" never matches a real key through it (see
    autobot_shared/logging_manager.py's log-level read for the same trap).
    Pin that ``_sql_echo_enabled`` uses ``get_nested`` and actually observes
    a change, not a getter that silently falls through to its default.
    """
    monkeypatch.setattr(
        user_db.config_manager,
        "get_nested",
        lambda key, default=None: True if key == "logging.log_sql" else default,
    )
    monkeypatch.setattr(user_db.config_manager, "get", lambda key, default=None: default)

    assert user_db._sql_echo_enabled() is True
