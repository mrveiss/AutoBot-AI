# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``ls`` operands are contained in the run's working directory after symlinks resolve (#19807)."""

from unattended_commands import unattended_refusal


def test_ls_refuses_a_symlink_that_leaves_the_working_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    (work / "real").mkdir(parents=True)
    (work / "link").symlink_to(outside)
    assert unattended_refusal("ls link", str(work)) is not None
    assert unattended_refusal("ls real", str(work)) is None
