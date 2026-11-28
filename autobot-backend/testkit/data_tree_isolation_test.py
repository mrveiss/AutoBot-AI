# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-data isolation fixture and the data-tree snapshot (#22259)."""

from pathlib import Path

import pytest

from autobot_logging.terminal_logger import TerminalLogger  # in sys.modules so the wrapper applies
from chat_history.base import ChatHistoryBase  # imported at collection so the autouse fixture sees it
from testkit import data_tree_isolation as dti

_ROOT = Path(dti.__file__).resolve().parent.parent.parent


@pytest.mark.parametrize("cwd", [_ROOT, _ROOT / "autobot-backend"])
def test_paths_under_tmp_path_whatever_the_cwd(monkeypatch, tmp_path, cwd):
    monkeypatch.chdir(cwd)
    mgr = ChatHistoryBase(history_file=None, use_redis=False)
    assert Path(mgr._get_chats_directory()) == tmp_path / "chats"
    assert Path(mgr.history_file) == tmp_path / "data" / "chat_history.json"
    assert Path(mgr.history_file).parent.is_dir()


def test_snapshot_reports_new_files_and_dirs(tmp_path):
    tree = tmp_path / "data"
    tree.mkdir()
    (tree / "old.json").write_text("{}", encoding="utf-8")
    before = dti.snapshot_data_trees((tree,))
    (tree / "sub").mkdir()
    (tree / "sub" / "new.json").write_text("{}", encoding="utf-8")
    new = dti.snapshot_data_trees((tree,)) - before
    assert new == {str(tree / "sub"), str(tree / "sub" / "new.json")}


def test_missing_tree_is_empty(tmp_path):
    assert dti.snapshot_data_trees((tmp_path / "absent",)) == frozenset()


def test_workers_are_not_the_controller():
    class _Worker:
        workerinput = {}

    assert dti._is_controller(object()) is True
    assert dti._is_controller(_Worker()) is False


def test_terminal_logger_relative_dir_goes_under_tmp_path(tmp_path):
    assert TerminalLogger().data_dir == tmp_path / "data" / "chats"
    assert TerminalLogger(data_dir="other/dir").data_dir == tmp_path / "other" / "dir"


def test_terminal_logger_absolute_dir_is_left_alone(tmp_path):
    target = tmp_path / "elsewhere"
    assert TerminalLogger(data_dir=str(target)).data_dir == target


class _RealManager:
    marker = "real-attribute"

    def get(self, key, default=None):
        return {"data": {"keep": 1, "chats_directory": "x"}, "other": 7}.get(key, default)


def test_proxy_overrides_only_the_chat_paths():
    proxy = dti._DataConfigProxy(_RealManager(), {"chats_directory": "c", "chat_history_file": "h"})
    assert proxy.get("data") == {"keep": 1, "chats_directory": "c", "chat_history_file": "h"}


def test_proxy_passes_other_keys_and_attributes_through():
    proxy = dti._DataConfigProxy(_RealManager(), {"chats_directory": "c"})
    assert proxy.get("other") == 7
    assert proxy.get("missing", "dflt") == "dflt"
    assert proxy.marker == "real-attribute"


def test_proxy_without_a_real_manager_still_overrides():
    proxy = dti._DataConfigProxy(None, {"chats_directory": "c"})
    assert proxy.get("data") == {"chats_directory": "c"}
    assert proxy.get("other", 3) == 3
