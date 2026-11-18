# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-file sinks built from a session id go through validate_relative_path (#20611)."""

import asyncio
import importlib

import pytest

_BAD_IDS = ["../escape", "a/../../escape", "/abs/escape", "..\\escape"]


def _terminal_logger(tmp_path):
    module = importlib.import_module("autobot_logging.terminal_logger")
    return module.TerminalLogger(data_dir=str(tmp_path))


@pytest.mark.parametrize("session_id", _BAD_IDS)
def test_terminal_logger_refuses_an_escaping_session_id(tmp_path, session_id):
    tl = _terminal_logger(tmp_path)
    for suffix in ("chat.json", "terminal.log"):
        with pytest.raises(ValueError):
            tl._session_file(session_id, suffix)
    with pytest.raises(ValueError):
        asyncio.run(tl._ensure_chat_json_exists(session_id))
    assert not list(tmp_path.parent.glob("escape*"))


def test_terminal_logger_resolves_a_plain_session_id_under_the_data_dir(tmp_path):
    tl = _terminal_logger(tmp_path)
    assert tl._session_file("abc", "chat.json") == tmp_path.resolve() / "abc_chat.json"


@pytest.mark.parametrize("session_id", _BAD_IDS)
def test_orphan_recovery_refuses_an_escaping_session_id(tmp_path, session_id):
    listing = importlib.import_module("chat_history.session_listing")
    mixin = next(c for c in vars(listing).values() if isinstance(c, type) and hasattr(c, "_create_orphaned_session"))
    with pytest.raises(ValueError):
        asyncio.run(mixin._create_orphaned_session(object.__new__(mixin), session_id, "f", str(tmp_path)))
    assert not list(tmp_path.parent.glob("escape*"))
