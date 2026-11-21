# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One record is written once per sink, though a package logger and its module both own handlers (#21773).

Cause: ``chat_workflow/__init__.py`` calls ``get_logger("chat_workflow")``; ``chat_workflow.manager`` calls
``get_logger`` too. Each owns a file handler and console handlers and propagates to its parent, so a record from
the module was written by its own handlers and again by the package's.
"""

from __future__ import annotations

import io
import logging
import sys
import uuid

from autobot_shared.logging_manager import LoggingManager


def _names() -> tuple[str, str]:
    root = f"emitonce{uuid.uuid4().hex[:8]}"
    return root, f"{root}.child"


def test_a_child_record_is_written_once_per_console_stream(monkeypatch, tmp_path):
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(LoggingManager, "_file_logging_enabled", False)
    parent_name, child_name = _names()
    LoggingManager.get_logger(parent_name)
    child = LoggingManager.get_logger(child_name)

    child.info("hello-info")
    child.warning("hello-warning")

    assert out.getvalue().count("hello-info") == 1
    assert err.getvalue().count("hello-warning") == 1
    assert out.getvalue().count("hello-warning") == 0  # stdout still excludes WARNING+


def test_the_order_the_loggers_are_made_in_does_not_matter(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(LoggingManager, "_file_logging_enabled", False)
    parent_name, child_name = _names()
    child = LoggingManager.get_logger(child_name)  # the module first, the package after
    LoggingManager.get_logger(parent_name)

    child.info("late-parent")

    assert out.getvalue().count("late-parent") == 1


def test_a_shared_file_handler_writes_a_propagated_record_once(monkeypatch, tmp_path):
    log_file = tmp_path / "backend.log"
    monkeypatch.setattr("autobot_shared.logging_manager._log_file_path", lambda _t: str(log_file))
    monkeypatch.setattr(LoggingManager, "_file_handlers", {})
    monkeypatch.setattr(LoggingManager, "_file_logging_enabled", True)
    parent_name, child_name = _names()
    parent = LoggingManager.get_logger(parent_name)
    child = LoggingManager.get_logger(child_name)
    handler = next(h for h in child.handlers if h in parent.handlers)

    child.info("to-the-file")
    handler.flush()

    assert log_file.read_text(encoding="utf-8").count("to-the-file") == 1


def test_a_record_rejected_by_the_level_split_is_not_marked_written():
    _, child_name = _names()
    record = logging.LogRecord(child_name, logging.WARNING, __file__, 1, "w", None, None)
    from autobot_shared.stream_logging import build_stdout_handler

    assert build_stdout_handler().filter(record) is False  # the stdout handler drops WARNING+ ...
    assert "stdout" not in record.__dict__.get("_autobot_sinks", set())  # ... and does not claim it
