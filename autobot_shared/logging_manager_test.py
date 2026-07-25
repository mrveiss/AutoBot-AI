# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for LoggingManager's console handler (#12506).

Prior to this fix, the console handler in ``LoggingManager.get_logger`` was
gated on ``_get_config_manager().get("deployment.mode", "local") ==
"local"`` — a dead/no-op condition (flat-key lookup, key never set) that
always fell through to the ``"local"`` default. Per #12488 the console
handler is meant to be unconditional in every mode (systemd captures
stdout/stderr into the real log files), so this test proves:

1. ``get_logger()`` always attaches a console handler (no mode gate).
2. That handler still routes DEBUG/INFO -> stdout, WARNING+ -> stderr
   (the #12488 split), with no regression from removing the gate.
"""

import logging
import logging.handlers

from autobot_shared.logging_manager import LoggingManager
from autobot_shared.stream_logging import MaxLevelFilter


def _console_handlers(logger: logging.Logger) -> list[logging.StreamHandler]:
    return [
        h
        for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)
    ]


def test_get_logger_always_attaches_console_handlers():
    """Console handler is unconditional — no deployment-mode gate (#12506)."""
    logger = LoggingManager.get_logger("logging_manager_test.always_on", "debug")
    console_handlers = _console_handlers(logger)

    assert len(console_handlers) == 2, "expected one stdout + one stderr handler regardless of mode"


def test_console_handlers_split_info_to_stdout_and_warning_to_stderr(capsys):
    """No regression from removing the gate: #12488 level split still holds."""
    logger = LoggingManager.get_logger("logging_manager_test.level_split", "debug")
    logger.propagate = False

    logger.info("info-line-12506")
    logger.warning("warn-line-12506")

    captured = capsys.readouterr()
    assert "info-line-12506" in captured.out
    assert "warn-line-12506" not in captured.out
    assert "warn-line-12506" in captured.err
    assert "info-line-12506" not in captured.err


def test_exactly_one_console_handler_carries_the_max_level_filter():
    """Exactly one of the two console handlers is the stdout side (belt-and-
    suspenders MaxLevelFilter rejecting WARNING+), the other is the stderr
    side (setLevel(WARNING), no filter)."""
    logger = LoggingManager.get_logger("logging_manager_test.filter_check", "debug")
    console_handlers = _console_handlers(logger)

    with_filter = [h for h in console_handlers if any(isinstance(f, MaxLevelFilter) for f in h.filters)]
    without_filter = [h for h in console_handlers if h not in with_filter]

    assert len(with_filter) == 1
    assert len(without_filter) == 1
    assert without_filter[0].level == logging.WARNING
