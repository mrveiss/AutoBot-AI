# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fact-forcing path normalization via realpath (GH#11179).

A file read by one path and edited by another that resolve to the SAME real
file (relative vs absolute, or through a symlink) must credit the read and NOT
block the edit. Previously `_norm` used `os.path.normpath` and mismatched.
"""

from agent_loop.fact_forcing import first_uninvestigated_edit, record_investigations


def test_relative_read_then_absolute_edit_is_credited(tmp_path, monkeypatch) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    seen: set[str] = set()
    # Read by RELATIVE path...
    record_investigations([{"tool_name": "read_file", "args": {"file_path": "mod.py"}}], seen)
    # ...edit by ABSOLUTE path — same real file, so not flagged.
    assert first_uninvestigated_edit({"tool_name": "edit_file", "args": {"file_path": str(target)}}, seen) is None


def test_symlink_read_then_target_edit_is_credited(tmp_path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(target)

    seen: set[str] = set()
    record_investigations([{"tool_name": "read_file", "args": {"file_path": str(link)}}], seen)
    assert first_uninvestigated_edit({"tool_name": "edit_file", "args": {"file_path": str(target)}}, seen) is None


def test_unread_existing_file_still_blocked(tmp_path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    # No read recorded → still flagged.
    assert first_uninvestigated_edit({"tool_name": "edit_file", "args": {"file_path": str(target)}}, set()) == str(
        target
    )
