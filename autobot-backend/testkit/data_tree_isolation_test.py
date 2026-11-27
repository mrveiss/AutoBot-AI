# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat-data isolation fixture and the data-tree snapshot (#22259)."""

from pathlib import Path

import pytest

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
