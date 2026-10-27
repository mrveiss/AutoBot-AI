# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""update-all must refresh every code_source directory the fresh-install role syncs (#18324).

The backend role's ``main.yml`` is the fresh-install path; ``update-all-nodes.yml``
pulls that role only through ``tasks_from`` files. A directory synced solely from
``main.yml`` is therefore refreshed once, at provision, and then frozen: the
deployed ``docs/`` was 40 commits stale that way. This guard reads both sides, so
the next directory added to the role without an update path fails here instead
of on a host.
"""

import re

from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_ROLE_TASKS = _ANSIBLE / "roles" / "backend" / "tasks"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"

_SRC = re.compile(r'src:\s*"\{\{\s*code_source_dir\s*\}\}/([A-Za-z0-9_.-]+)/')
_INCLUDE_LOCAL = re.compile(r"include_tasks:\s*([A-Za-z0-9_.-]+\.yml)")
_TASKS_FROM = re.compile(r"tasks_from:\s*([A-Za-z0-9_.-]+?)(?:\.yml)?\s*$", re.M)
_BACKEND_ROLE_BLOCK = re.compile(r"name:\s*backend\s*\n\s*tasks_from:\s*([A-Za-z0-9_.-]+?)(?:\.yml)?\s*$", re.M)


def _fresh_install_dirs() -> set[str]:
    """Top-level code_source dirs synced by main.yml and the files it includes."""
    main = (_ROLE_TASKS / "main.yml").read_text(encoding="utf-8")
    texts = [main] + [
        (_ROLE_TASKS / name).read_text(encoding="utf-8")
        for name in _INCLUDE_LOCAL.findall(main)
        if (_ROLE_TASKS / name).is_file()
    ]
    return {d for text in texts for d in _SRC.findall(text)}


def _update_all_dirs() -> set[str]:
    """Top-level code_source dirs update-all reaches: its own, plus backend tasks_from files."""
    playbook = _PLAYBOOK.read_text(encoding="utf-8")
    texts = [playbook]
    for name in _BACKEND_ROLE_BLOCK.findall(playbook):
        path = _ROLE_TASKS / f"{name}.yml"
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for text in texts:
        found.update(_SRC.findall(text))
        found.update(re.findall(r"code_source[^\n]*?\}\}/([A-Za-z0-9_.-]+)[\"'\s]", text))
    return found


def test_the_fresh_install_role_syncs_docs():
    """Control: the extractor sees the directory this issue is about."""
    assert "docs" in _fresh_install_dirs()


def test_the_extractors_see_something_on_both_sides():
    assert len(_fresh_install_dirs()) >= 3
    assert len(_update_all_dirs()) >= 3


def test_update_all_refreshes_every_dir_the_fresh_install_role_syncs():
    missing = sorted(_fresh_install_dirs() - _update_all_dirs())
    assert not missing, (
        f"directories synced from code_source on a fresh install but never on update-all: {missing}. "
        "Pull the role's sync through a tasks_from file (#18324)."
    )
