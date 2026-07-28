# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for stdout/stderr log-stream routing (#12488).

Proves the two independent misroutes are fixed:

1. Uvicorn's own logging config (``uvicorn_log_config.json``, loaded via
   ``load_uvicorn_log_config()``) — an INFO record on ``uvicorn.error``
   (the logger uvicorn uses for connection-lifecycle lines such as
   "WebSocket ... [accepted]" and websockets' "connection open") must land
   on stdout, while WARNING+ lands on stderr.
2. ``build_stdout_handler``/``build_stderr_handler`` (used by
   ``autobot_shared.logging_manager``'s per-module console handler and by
   ``autobot-slm-backend/main.py``'s root-logger ``basicConfig``) split any
   logger's output the same way.
"""

import json
import logging
import logging.config
from pathlib import Path

from autobot_shared.stream_logging import (
    MaxLevelFilter,
    build_stderr_handler,
    build_stdout_handler,
    load_uvicorn_log_config,
)


def _make_record(level: int) -> logging.LogRecord:
    return logging.LogRecord("test", level, __file__, 1, "msg", None, None)


def test_max_level_filter_allows_below_threshold():
    f = MaxLevelFilter(logging.WARNING)
    assert f.filter(_make_record(logging.DEBUG)) is True
    assert f.filter(_make_record(logging.INFO)) is True


def test_max_level_filter_rejects_at_or_above_threshold():
    f = MaxLevelFilter(logging.WARNING)
    assert f.filter(_make_record(logging.WARNING)) is False
    assert f.filter(_make_record(logging.ERROR)) is False


def test_build_stdout_handler_emits_info_not_warning(capsys):
    logger = logging.getLogger("stream_logging_test.stdout")
    logger.handlers = [build_stdout_handler()]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    logger.info("info-line")
    logger.warning("warn-line")

    captured = capsys.readouterr()
    assert "info-line" in captured.out
    assert "warn-line" not in captured.out
    assert captured.err == ""


def test_build_stderr_handler_emits_warning_not_info(capsys):
    logger = logging.getLogger("stream_logging_test.stderr")
    logger.handlers = [build_stderr_handler()]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    logger.info("info-line")
    logger.warning("warn-line")

    captured = capsys.readouterr()
    assert "warn-line" in captured.err
    assert "info-line" not in captured.err
    assert captured.out == ""


def test_load_uvicorn_log_config_matches_json_on_disk():
    """Guards against the JSON file and the loader drifting apart."""
    disk_path = Path(__file__).parent / "uvicorn_log_config.json"
    with disk_path.open(encoding="utf-8") as f:
        expected = json.load(f)
    assert load_uvicorn_log_config() == expected


def test_uvicorn_log_config_routes_info_to_stdout_and_warning_to_stderr(capsys):
    """#12488: 'WebSocket ... [accepted]' (uvicorn.error, INFO) -> stdout;
    real problems (WARNING+) -> stderr — proves the systemd
    StandardOutput=append:/StandardError=append: split lands each line in
    the log file it belongs in.
    """
    logging.config.dictConfig(load_uvicorn_log_config())
    try:
        logger = logging.getLogger("uvicorn.error")
        logger.info('%s - "WebSocket %s" [accepted]', "127.0.0.1:1", "/ws")
        logger.warning("some real problem")

        captured = capsys.readouterr()
        assert "[accepted]" in captured.out
        assert "some real problem" not in captured.out
        assert "some real problem" in captured.err
        assert "[accepted]" not in captured.err
    finally:
        # Reset so this test doesn't leak uvicorn's dictConfig into others.
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
