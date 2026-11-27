# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No test writes chat files into the repo's ``autobot-backend/data/`` tree (#22259).

``ChatHistoryBase._get_chats_directory`` falls back to the relative default ``data/chats``. A test
that drives a real ``ChatHistoryManager`` without overriding it (for example a turn through
``chat_workflow.graph.prepare_llm``, whose attachment notices are stored by
``attachment_context.persist_notices``) therefore wrote ``s-<id>_chat.json`` and its ``.lock`` into the
checkout. Two fixtures close this:

* ``isolate_default_chats_directory`` (per test) points the unconfigured default at ``tmp_path``. A
  directory a test configured on purpose (absolute, outside the repo data tree) is left alone.
* ``data_tree_stays_clean`` (per session) fails the run if any file appeared under ``data/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _snapshot() -> set[Path]:
    """Every file currently under the repo ``data/`` tree."""
    if not _DATA_DIR.is_dir():
        return set()
    return {p for p in _DATA_DIR.rglob("*") if p.is_file()}


def _inside_repo_data(path: str) -> bool:
    """True for the relative default or any path that resolves under the repo ``data/`` tree."""
    resolved = Path(path).resolve()
    return resolved == _DATA_DIR or _DATA_DIR in resolved.parents


@pytest.fixture(autouse=True)
def isolate_default_chats_directory(monkeypatch, tmp_path):
    """Redirect a chats directory that would land in the repo to ``tmp_path``."""
    base_module = sys.modules.get("chat_history.base")
    ChatHistoryBase = getattr(base_module, "ChatHistoryBase", None)
    if ChatHistoryBase is None:  # not imported (or stubbed) in this run: nothing can write there
        return
    original = ChatHistoryBase._get_chats_directory

    def _isolated(self) -> str:
        configured = original(self)
        return str(tmp_path / "chats") if _inside_repo_data(configured) else configured

    monkeypatch.setattr(ChatHistoryBase, "_get_chats_directory", _isolated)


@pytest.fixture(autouse=True, scope="session")
def data_tree_stays_clean():
    """Fail the session when a test leaves new files under ``autobot-backend/data/``."""
    before = _snapshot()
    yield
    leaked = sorted(str(p.relative_to(_DATA_DIR)) for p in _snapshot() - before)
    if leaked:
        pytest.fail(f"tests wrote into the repo data tree (isolate the store to tmp_path): {leaked[:20]}", pytrace=False)
