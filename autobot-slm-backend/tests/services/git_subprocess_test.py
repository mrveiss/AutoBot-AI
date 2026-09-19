# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services/git_subprocess.py's shallow-clone helpers (#16310).

``is_shallow_repository`` and ``ensure_full_history`` are the OTHER half of
#16310's fix: even with ``compute_bootstrap_plan``'s own shallow-clone guard
(``tests/services/sync_deletions_shallow_bootstrap_test.py``), a checkout
that came from initial provisioning stays shallow forever unless something
actually unshallows it -- a plain ``git fetch`` on an already-shallow repo
does not deepen it. These tests exercise a real, disposable git repository
(a real shallow clone, made with git itself) rather than a mock, same
rationale as the sibling shallow-bootstrap test file.

Lives under tests/services/, not co-located with git_subprocess.py in
services/, for the same pytest-collection reason as
tests/services/sync_deletions_test.py's own module docstring: services/ has
its own __init__.py, so a test module living there would import the REAL
services package before this file's own sys.modules bootstrap runs.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from autobot_shared.paths import scrubbed_git_env

_SERVICES_DIR = Path(__file__).parent.parent.parent / "services"

# Captured at import time, before tests/api/conftest.py's process-wide
# asyncio.create_subprocess_exec block can apply -- same bypass as
# tests/services/sync_deletions_shallow_bootstrap_test.py's _real_git().
_REAL_SUBPROCESS_EXEC = asyncio.create_subprocess_exec


def _real_git():
    return patch.object(asyncio, "create_subprocess_exec", _REAL_SUBPROCESS_EXEC)


def _real_load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SWAPPED = ("services", "services.git_subprocess")
_prev_modules = {name: sys.modules.get(name) for name in _SWAPPED}
try:
    _gs = _real_load("services.git_subprocess", _SERVICES_DIR / "git_subprocess.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

is_shallow_repository = _gs.is_shallow_repository
ensure_full_history = _gs.ensure_full_history

_GIT_ENV = {
    **scrubbed_git_env(),
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@e",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@e",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, env=_GIT_ENV, capture_output=True, text=True)
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=_GIT_ENV)


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "--allow-empty", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _shallow_clone(source: Path, dest: Path) -> None:
    """A REAL shallow clone -- git itself decides what --depth 1 keeps."""
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--branch", "main", f"file://{source}", str(dest)],
        check=True,
        env=_GIT_ENV,
    )


async def test_is_shallow_repository_true_for_a_shallow_clone(tmp_path) -> None:
    origin = tmp_path / "origin"
    _init_repo(origin)
    _commit_all(origin, "seed")
    _commit_all(origin, "second")

    clone = tmp_path / "clone"
    _shallow_clone(origin, clone)

    with _real_git():
        assert await is_shallow_repository(str(clone)) is True


async def test_is_shallow_repository_false_for_an_ordinary_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_all(repo, "seed")

    with _real_git():
        assert await is_shallow_repository(str(repo)) is False


async def test_ensure_full_history_unshallows_a_shallow_clone(tmp_path) -> None:
    origin = tmp_path / "origin"
    _init_repo(origin)
    _commit_all(origin, "one")
    _commit_all(origin, "two")
    _commit_all(origin, "three")

    clone = tmp_path / "clone"
    _shallow_clone(origin, clone)

    with _real_git():
        assert await is_shallow_repository(str(clone)) is True

        ok, message = await ensure_full_history(str(clone))

        assert ok is True
        assert "unshallow" in message.lower()
        assert await is_shallow_repository(str(clone)) is False

    # Full history really did arrive, not just the shallow flag flipping.
    log = subprocess.run(
        ["git", "-C", str(clone), "log", "--oneline"], check=True, env=_GIT_ENV, capture_output=True, text=True
    )
    assert len(log.stdout.strip().splitlines()) == 3


async def test_ensure_full_history_is_a_no_op_on_a_full_depth_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_all(repo, "seed")

    with _real_git():
        ok, message = await ensure_full_history(str(repo))

    assert ok is True
    assert "already" in message.lower()


async def test_ensure_full_history_surfaces_failure_instead_of_swallowing_it(tmp_path) -> None:
    """A shallow clone whose origin remote has since gone away must fail the
    unshallow attempt loudly (ok=False), never come back as a silently
    swallowed success -- #16310's "never swallow it" requirement for the
    fetch step."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    _commit_all(origin, "seed")
    _commit_all(origin, "second")
    clone = tmp_path / "clone"
    _shallow_clone(origin, clone)
    shutil.rmtree(origin)

    with _real_git():
        ok, message = await ensure_full_history(str(clone))

    assert ok is False
    assert "unshallow" in message.lower()
