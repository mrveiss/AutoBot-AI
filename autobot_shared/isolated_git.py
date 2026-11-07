# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One isolated git environment for every test that builds a throwaway repo (#18940).

A fixture that runs ``git init``/``add``/``commit`` in ``tmp_path`` with the
developer's global and system git config does not test the same thing on two
machines: a personal ignore rule can untrack a fixture file, ``init.defaultBranch``
renames the branch an assertion names, a commit template, ``commit.gpgsign`` or a
global ``core.hooksPath`` changes whether the commit lands at all.

:func:`scrubbed_git_env` (``autobot_shared.paths``, #15783) answers "which
repository does git act on" by dropping the ambient ``GIT_DIR`` family.
This module answers the second question, "whose configuration does git read",
and composes the first rather than repeating it.

Home: ``autobot_shared`` is the one package the backend, the SLM backend,
``repo_tests`` and ``tools/lint`` tests already import (``scrubbed_git_env``
lives beside it), so no ``sys.path`` or conftest wiring is needed anywhere.

``core.hooksPath`` and the init template directory are not set here: both come
from configuration, and the global and system files are cut off, so a developer's
value never reaches git. Hooks a test installs into ``.git/hooks`` itself still
run, which the hook suites rely on.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

DEFAULT_BRANCH = "main"
IDENTITY_NAME = "AutoBot Test"
IDENTITY_EMAIL = "test@autobot.invalid"

#: Config forced through ``GIT_CONFIG_COUNT`` (git >= 2.31), which outranks every
#: file. ``core.excludesFile``/``core.attributesFile`` default to a path under
#: ``$XDG_CONFIG_HOME`` even with no config file, so cutting off the files alone
#: would not stop a personal ignore rule.
_FORCED_CONFIG = (
    ("core.excludesFile", os.devnull),
    ("core.attributesFile", os.devnull),
    ("commit.gpgsign", "false"),
    ("tag.gpgsign", "false"),
)
_OWNED_PREFIXES = ("GIT_CONFIG_", "GIT_AUTHOR_", "GIT_COMMITTER_")


def _forced_config(default_branch: str) -> dict[str, str]:
    pairs = (("init.defaultBranch", default_branch), *_FORCED_CONFIG)
    env = {"GIT_CONFIG_COUNT": str(len(pairs))}
    for index, (key, value) in enumerate(pairs):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _identity() -> dict[str, str]:
    return {
        "GIT_AUTHOR_NAME": IDENTITY_NAME,
        "GIT_AUTHOR_EMAIL": IDENTITY_EMAIL,
        "GIT_COMMITTER_NAME": IDENTITY_NAME,
        "GIT_COMMITTER_EMAIL": IDENTITY_EMAIL,
    }


def isolated_git_env(
    base: Mapping[str, str] | None = None,
    *,
    default_branch: str = DEFAULT_BRANCH,
    identity: bool = True,
) -> dict[str, str]:
    """*base* (default :data:`os.environ`) made safe for a throwaway-repo fixture.

    Drops the ambient ``GIT_DIR`` family and every inherited ``GIT_CONFIG_*``,
    ``GIT_AUTHOR_*`` and ``GIT_COMMITTER_*`` name, cuts off the global and
    system config files, and pins the default branch, signing and a fixed
    author/committer. ``identity=False`` leaves author/committer to the repo's
    own ``user.*`` config, for a test that asserts on the author it configured
    (the environment would otherwise outrank it).

    A repo-local ``core.hooksPath`` is NOT forced off: only the global and system
    files are cut. That is fine for a fresh tmp repo, which has none; a fixture that
    copies a real repository's ``.git/config`` must account for it itself.
    """
    env = {k: v for k, v in scrubbed_git_env(base).items() if not k.startswith(_OWNED_PREFIXES)}
    env.pop("GIT_TEMPLATE_DIR", None)
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    env.update(_forced_config(default_branch))
    if identity:
        env.update(_identity())
    return env


def git(repo: str | os.PathLike[str], *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <repo> <args>`` under :func:`isolated_git_env`; text output captured.

    There is no ``env`` parameter on purpose: a caller needing extra variables builds
    ``{**isolated_git_env(), ...}`` and calls ``subprocess.run`` itself.
    """
    return subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "-C", os.fspath(repo), *args],
        capture_output=True,
        text=True,
        check=check,
        env=isolated_git_env(),
    )


def make_repo(path: Path, *, default_branch: str = DEFAULT_BRANCH) -> Path:
    """``git init`` *path* (created if absent) under the isolated env and return it.

    The fixed identity is also written to the repo's own config, so a later
    ``git commit`` run with a different environment still has an author.
    """
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", default_branch)
    git(path, "config", "user.name", IDENTITY_NAME)
    git(path, "config", "user.email", IDENTITY_EMAIL)
    return path
