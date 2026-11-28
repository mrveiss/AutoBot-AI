# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test writes chat files into a repo ``data/`` tree (#22259).

``ChatHistoryBase`` reads ``data.chats_directory`` / ``data.chat_history_file`` from the config
manager, falling back to ``misc.chats_directory`` / ``misc.chat_history_file`` (SSOT), and finally to
the cwd-relative ``data/chats`` / ``data/chat_history.json``. CI runs pytest from the repo root, local runs
from ``autobot-backend/``, so the relative default lands in a different tree each time. Two pieces:

* ``isolate_chat_data_paths`` (autouse, per test) sets those config keys to absolute paths under
  ``tmp_path``, so the location no longer depends on the cwd.
  Relative ``TerminalLogger`` data dirs (``data/chats``, no config key) resolve under ``tmp_path`` too.
* ``pytest_sessionstart`` / ``pytest_sessionfinish`` snapshot BOTH ``<repo>/data`` and
  ``autobot-backend/data`` (files and directories) on the xdist controller only, and fail the session
  with the new paths when the run left any. The check reads the filesystem, not ``git status``
  (``.gitignore`` hides ``data/*``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DATA_TREES = (_BACKEND_ROOT.parent / "data", _BACKEND_ROOT / "data")
_SNAPSHOT_KEY = pytest.StashKey[frozenset]()


def snapshot_data_trees(trees=_DATA_TREES) -> frozenset[str]:
    """Every file and directory currently under the given data trees (the roots included)."""
    found: set[str] = set()
    for tree in trees:
        if tree.is_dir():
            found.add(str(tree))
            found.update(str(p) for p in tree.rglob("*"))
    return frozenset(found)


def _is_controller(config) -> bool:
    """True on the single process that owns the session (not an xdist worker)."""
    return not hasattr(config, "workerinput")


def pytest_sessionstart(session):
    """Record the data trees before the first test (controller only)."""
    if _is_controller(session.config):
        session.config.stash[_SNAPSHOT_KEY] = snapshot_data_trees()


def pytest_sessionfinish(session, exitstatus):
    """Fail the session when the run left new paths under a data tree (controller only)."""
    before = session.config.stash.get(_SNAPSHOT_KEY, None)
    if before is None or not _is_controller(session.config):
        return
    leaked = sorted(snapshot_data_trees() - before)
    if leaked:
        listing = "\n  ".join(leaked[:20])
        sys.stderr.write(f"\ntests wrote into a repo data tree (isolate the store to tmp_path):\n  {listing}\n")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


class _DataConfigProxy:
    """The config manager, with ``data.*`` chat paths overridden."""

    def __init__(self, real, overrides: dict):
        self._real = real
        self._overrides = overrides

    def get(self, key, default=None):
        value = self._real.get(key, default) if self._real is not None else default
        if key == "data":
            return {**(value or {}), **self._overrides}
        return value

    def __getattr__(self, name):
        return getattr(self._real, name)


def _isolate_terminal_logger(monkeypatch, root: Path) -> None:
    """Resolve a relative ``TerminalLogger`` data dir (callers pass ``"data/chats"``) under ``root``."""
    module = sys.modules.get("autobot_logging.terminal_logger")
    logger_cls = getattr(module, "TerminalLogger", None)
    if not isinstance(logger_cls, type):
        return
    original = logger_cls.__init__

    def _init(self, redis_client=None, data_dir="data/chats"):
        path = Path(data_dir)
        original(self, redis_client, str(path if path.is_absolute() else root / path))

    monkeypatch.setattr(logger_cls, "__init__", _init)


@pytest.fixture(autouse=True)
def isolate_chat_data_paths(monkeypatch, tmp_path):
    """Point the chat history directory, file and data dir at absolute paths under ``tmp_path``."""
    _isolate_terminal_logger(monkeypatch, tmp_path)
    base_module = sys.modules.get("chat_history.base")
    ssot = getattr(base_module, "_ssot_config", None)
    if ssot is None:  # not imported (or stubbed) in this run: nothing can write there
        return
    chats, history = str(tmp_path / "chats"), str(tmp_path / "data" / "chat_history.json")
    monkeypatch.setattr(ssot.misc, "chats_directory", chats)
    monkeypatch.setattr(ssot.misc, "chat_history_file", history)
    real_getter = base_module.get_config_manager
    overrides = {"chats_directory": chats, "chat_history_file": history}
    monkeypatch.setattr(base_module, "get_config_manager", lambda: _DataConfigProxy(real_getter(), overrides))
