# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A floor-only dependency change re-runs the updater's gated pip installs (#19428).

constraints/shared.txt carries security floors. The pre-flight diff watched only */requirements.txt
and autobot_shared/pyproject.toml, so a change confined to the SSOT left python_deps_changed false
and the floor never reached a host. This runs the shipped pathspec through git itself.
"""

from __future__ import annotations

import re
import shlex

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, make_repo

_PLAYBOOK = repo_root() / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"


def _shipped_pathspec() -> list[str]:
    text = _PLAYBOOK.read_text(encoding="utf-8")
    task = text[text.index("[PRE-FLIGHT] Check if Python deps changed") :]
    match = re.search(r"^\s+-- (.+)$", task, re.M)
    assert match, "the pre-flight no longer has a pathspec line"
    return shlex.split(match.group(1))


@pytest.mark.parametrize(
    ("path", "watched"),
    [
        ("constraints/shared.txt", True),
        ("requirements.txt", True),
        ("autobot-backend/requirements.txt", True),
        ("autobot_shared/pyproject.toml", True),
        ("autobot-backend/main.py", False),
    ],
)
def test_pathspec_decides_on_the_changed_file(tmp_path, path: str, watched: bool) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a\n", encoding="utf-8")
    make_repo(tmp_path)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    target.write_text("b\n", encoding="utf-8")
    git(tmp_path, "commit", "-qam", "change")
    changed = git(tmp_path, "diff", "--name-only", "HEAD~1", "HEAD", "--", *_shipped_pathspec()).stdout
    assert bool(changed.strip()) is watched, (path, _shipped_pathspec())
