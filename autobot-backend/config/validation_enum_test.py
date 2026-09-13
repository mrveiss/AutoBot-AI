# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Closed-vocabulary config validation (#12750).

The orphaned models/settings.py was the only place in the tree that rejected an
out-of-vocabulary task transport or log level.  Those checks were consolidated
onto config.validation, which already validates ports and runs at startup via
initialization.lifespan.  These tests hold the migrated capability on the
canonical surface.
"""

import pytest

from config.defaults import get_default_config
from config.validation import _VALID_LOG_LEVELS, _VALID_TASK_TRANSPORTS, validate_startup_config


def _config(**sections):
    """Build a minimal raw config tree with the given sections."""
    base = {"memory": {"redis": {"enabled": True, "host": "127.0.0.1"}}}
    base.update(sections)
    return base


@pytest.mark.parametrize("transport", ["local", "redis"])
def test_recognised_task_transport_is_accepted(transport):
    """Both documented transports pass validation."""
    result = validate_startup_config(_config(task_transport={"type": transport}))

    assert result.errors == []


def test_unrecognised_task_transport_is_rejected():
    """worker_node silently degraded to local dispatch on a typo; now it errors."""
    result = validate_startup_config(_config(task_transport={"type": "rabbitmq"}))

    assert result.valid is False
    assert any("task_transport.type" in error and "rabbitmq" in error for error in result.errors)


def test_task_transport_comparison_is_case_insensitive():
    """A config written as "Redis" is the redis transport, not an error."""
    result = validate_startup_config(_config(task_transport={"type": "Redis"}))

    assert result.errors == []


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_recognised_log_level_is_accepted(level):
    """Every stdlib level name config/defaults.py can publish is accepted."""
    result = validate_startup_config(_config(logging={"log_level": level}))

    assert result.errors == []


def test_unrecognised_log_level_is_rejected():
    """logging_manager does getattr(logging, value.upper()); a typo must not reach it."""
    result = validate_startup_config(_config(logging={"log_level": "verbose"}))

    assert result.valid is False
    assert any("logging.log_level" in error and "verbose" in error for error in result.errors)


def test_log_level_accepts_the_orphan_lowercase_spelling():
    """The orphan normalised to lowercase; the canonical set is uppercase."""
    result = validate_startup_config(_config(logging={"log_level": "info"}))

    assert result.errors == []


def test_absent_enum_keys_produce_no_error():
    """A config that omits the sections entirely is still valid."""
    result = validate_startup_config(_config())

    assert result.errors == []


def test_enum_and_port_errors_are_reported_together():
    """Structured accumulation: one pass reports every problem, not the first."""
    raw = _config(
        task_transport={"type": "kafka"},
        logging={"log_level": "chatty"},
        backend={"server_port": 99999},
    )

    result = validate_startup_config(raw)

    assert len(result.errors) == 3


def test_task_transport_vocabulary_is_pinned():
    """worker_node dispatches on "redis" and defaults to "local"; both must stay legal."""
    assert _VALID_TASK_TRANSPORTS == ("local", "redis")


def test_log_level_vocabulary_is_pinned():
    """The set is the stdlib level names, in the canonical UPPERCASE spelling."""
    assert _VALID_LOG_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_shipped_default_config_passes_the_migrated_checks():
    """The tree config/defaults.py publishes must satisfy the new vocabularies."""
    result = validate_startup_config(get_default_config())

    assert result.errors == []
