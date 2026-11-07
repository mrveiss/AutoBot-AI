# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Loggers writing to one file share one rotating handler per process (#20139).

Before, ``get_logger`` built a ``RotatingFileHandler`` per logger name. Handlers on one file share
no lock, so after one renamed the file the others kept writing into the renamed file through their
old handle, saw it over the cap, and rotated again: one rotation shifted the backups once per
handler and history aged out early.

NOT covered, and not fixable here: several *processes* on one file. Each process has its own handler,
and stdlib ``RotatingFileHandler`` has no cross-process lock. Measured with 4 processes writing 8000
numbered lines each into a 20 kB-cap file with room for every backup, 3 runs lost 4280, 2852 and 2285
of 32000 lines (7-13%) with ``FileNotFoundError`` on the rename; the same run with 1 process lost 0.
The backend runs ``--workers 1``; the repo has no multi-process rotating handler to reuse.
"""

import logging
import logging.handlers
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from autobot_shared import logging_manager
from autobot_shared.logging_manager import LoggingManager

_ROTATING = logging.handlers.RotatingFileHandler  # captured: a test patches the module attribute
_CAP = 2000
_LINE = "x" * 90


class _Config:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def get_nested(self, path: str, default: object = None) -> object:
        return self._values.get(path, default)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("AUTOBOT_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(logging_manager, "_warned_config_keys", set())
    monkeypatch.setattr(LoggingManager, "_file_handlers", {})
    monkeypatch.setattr(LoggingManager, "_loggers", {})
    config = _Config({"logging.rotation.max_bytes": _CAP, "logging.rotation.backup_count": 200})
    with patch.object(logging_manager, "_get_config_manager", return_value=config):
        yield
    for handler in LoggingManager._file_handlers.values():
        handler.close()


def _logger(log_type: str = "backend") -> logging.Logger:
    return LoggingManager.get_logger(f"shared_20139.{uuid.uuid4().hex}", log_type)


def _file_handlers(logger: logging.Logger) -> list[logging.handlers.RotatingFileHandler]:
    return [h for h in logger.handlers if isinstance(h, _ROTATING)]


def _lines(tmp_path: Path, log_type: str = "backend") -> list[str]:
    files = (tmp_path / "logs").glob(f"{log_type}.log*")
    return [line for f in files for line in f.read_text(encoding="utf-8").splitlines()]


def test_two_logger_names_share_one_handler_instance() -> None:
    first, second = _logger(), _logger()
    assert len(_file_handlers(first)) == len(_file_handlers(second)) == 1
    assert _file_handlers(first)[0] is _file_handlers(second)[0]


def test_log_types_with_different_files_keep_their_own_handlers(tmp_path: Path) -> None:
    backend, frontend = _logger("backend"), _logger("frontend")
    assert _file_handlers(backend)[0] is not _file_handlers(frontend)[0]
    backend.info("to-backend")
    frontend.info("to-frontend")
    assert any("to-backend" in x for x in _lines(tmp_path, "backend"))
    assert any("to-frontend" in x for x in _lines(tmp_path, "frontend"))
    assert not any("to-frontend" in x for x in _lines(tmp_path, "backend"))
    assert not any("to-backend" in x for x in _lines(tmp_path, "frontend"))


def test_handler_level_and_formatter_are_unchanged_for_callers() -> None:
    handler = _file_handlers(_logger())[0]
    assert handler.level == logging.NOTSET
    assert handler.formatter is not None and handler.formatter._fmt == logging_manager._DEFAULT_FORMAT
    assert handler.maxBytes == _CAP


def test_failed_handler_build_is_not_cached(tmp_path: Path) -> None:
    with patch.object(logging.handlers, "RotatingFileHandler", side_effect=OSError("read-only")):
        assert _file_handlers(_logger()) == []
    assert LoggingManager._file_handlers == {}
    assert len(_file_handlers(_logger())) == 1


def test_one_rotation_shifts_the_backups_once(tmp_path: Path) -> None:
    loggers = [_logger() for _ in range(3)]
    for i in range(60):
        loggers[i % 3].info("%03d %s", i, _LINE)
    backups = sorted((tmp_path / "logs").glob("backend.log.*"))
    assert len(backups) >= 3, "the run must cross the cap several times to say anything"
    assert all(
        b.stat().st_size > _CAP - 2 * len(_LINE) for b in backups
    ), "a backup far under the cap means a second handler rotated a file another had just rotated"


def test_no_line_is_lost_across_rotations_with_threads(tmp_path: Path) -> None:
    loggers = [_logger() for _ in range(3)]

    def write(index: int) -> None:
        for n in range(150):
            loggers[index].info("t%d-%03d %s", index, n, _LINE)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    found = {line.split()[-2] for line in _lines(tmp_path)}
    assert len(found) == 450
