# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared atomic write and dry-run report (#18964)."""

import os
import stat
from pathlib import Path

import pytest

from autobot_shared.generated_file_output import report_output, write_atomically


def test_write_atomically_replaces_content_and_keeps_the_mode(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o600)
    write_atomically(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_write_atomically_gives_a_new_file_the_default_mode(tmp_path: Path) -> None:
    target = tmp_path / "b.txt"
    write_atomically(target, "fresh")
    assert target.read_text(encoding="utf-8") == "fresh"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_write_atomically_failure_leaves_the_original_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "c.txt"
    target.write_text("original", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash before the rename")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        write_atomically(target, "corrupted")
    assert target.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".*.tmp")) == []


@pytest.mark.parametrize(
    ("existing", "apply_changes", "expected"),
    [
        (None, False, "Would write"),
        (None, True, "Wrote"),
        ("same", True, "(unchanged)"),
        ("different", False, "existing file would be replaced"),
    ],
)
def test_report_output_describes_each_case(
    tmp_path: Path, capsys: pytest.CaptureFixture, existing, apply_changes, expected
) -> None:
    target = tmp_path / "d.txt"
    if existing is not None:
        target.write_text(existing, encoding="utf-8")
    report_output(target, "same", apply_changes)
    assert expected in capsys.readouterr().out
