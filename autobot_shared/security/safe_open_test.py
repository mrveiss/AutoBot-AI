# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``open_under_root``: a component swapped for a symlink is refused, an in-root link is followed (#21289)."""

import os
from pathlib import Path

import pytest

from autobot_shared.security.safe_open import open_under_root, read_text_under_root


def test_plain_file_and_in_root_link_are_read(tmp_path: Path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "d" / "l.txt").symlink_to("f.txt")
    assert read_text_under_root(str(tmp_path), ("d", "f.txt")) == "hi"
    fd, final = open_under_root(str(tmp_path), ("d", "l.txt"))
    os.close(fd)
    assert final == ("d", "f.txt")


def test_symlinked_directory_component_is_refused(tmp_path: Path):
    root, outside = tmp_path / "root", tmp_path / "out"
    root.mkdir()
    outside.mkdir()
    (outside / "f.txt").write_text("secret", encoding="utf-8")
    (root / "d").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        read_text_under_root(str(root), ("d", "f.txt"))


@pytest.mark.parametrize("target", ["../out.txt", "/etc/hostname"])
def test_leaf_link_leaving_the_root_is_refused(tmp_path: Path, target: str):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "out.txt").write_text("secret", encoding="utf-8")
    (root / "l.txt").symlink_to(str(tmp_path / "out.txt") if target.startswith("/") else target)
    with pytest.raises(ValueError):
        read_text_under_root(str(root), ("l.txt",))


def test_follow_links_false_refuses_a_leaf_link(tmp_path: Path):
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "l.txt").symlink_to("f.txt")
    with pytest.raises(OSError):
        open_under_root(str(tmp_path), ("l.txt",), follow_links=False)


def test_link_loop_is_bounded(tmp_path: Path):
    (tmp_path / "a").symlink_to("b")
    (tmp_path / "b").symlink_to("a")
    with pytest.raises(ValueError):
        open_under_root(str(tmp_path), ("a",))
