# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every guard that asks git for the repository root must scrub the git env first (#15176).

A git hook run in a **worktree** — this repository's entire workflow — is handed
``GIT_DIR=<main>/.git/worktrees/<name>`` and no ``GIT_WORK_TREE`` (measured on
git 2.34.1, for both ``pre-commit`` and ``pre-push``; a plain checkout on that
version exports neither). Git then treats the *current directory* as the work
tree, so ``git rev-parse --show-toplevel`` answers with wherever the caller
happens to be standing rather than the repository root.

Git chdirs the hook to the top level before running it, even when the commit
was made from a subdirectory, so a hook's own first call still lands on the
root. The reproduction below is therefore run from ``repo_tests/``: the
environment is the hook's, the working directory is any of the places a
hook-spawned helper, an imported test module or a direct CI invocation actually
runs from.

The reason this is a test and not a note is that the wrong answer is not an
error. Measured on this branch's parent, run from ``repo_tests/`` with
``GIT_DIR`` exported:

============================================= ================================
site                                          behaviour before the scrub
============================================= ================================
``pipeline-scripts/check_hook_exec_bits``     exit 0, **reported clean** over a
                                              planted ``100644`` hook entry,
                                              having read zero hook configs
``pipeline-scripts/check_requirements_...``   exit 0, **reported clean** over a
                                              planted ``openpyxl`` conflict,
                                              having opened zero requirements
                                              files
``tools/lint/check_port_fallbacks_...``       exit 1, ``FATAL: ... ssot_config.py
                                              not found``
``repo_tests/sdk_defaults_match_ssot_test``   2 failures, "SDK defaults is
                                              missing"
``autobot-slm-backend/ansible/tests/...``     exit 1, uncaught
                                              ``FileNotFoundError``
============================================= ================================

Three of the five failed loudly and two passed wrongly, which is exactly why
"all five behave alike" was not assumable — and why the two silent ones are the
reason the family was worth fixing rather than noting.

The static half of the guard is ``tools/lint/check_git_toplevel_env_scrubbed.py``,
which blocks a sixth unscrubbed ``--show-toplevel`` from being added. This module
is the behavioural half: it re-runs the reproduction against every site.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from autobot_shared.paths import (
    AMBIENT_GIT_VARS,
    GitRepoRootUnavailable,
    git_repo_root,
    scrubbed_git_env,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The directory every reproduction is run from. Any tracked subdirectory of
#: the repository does; this one is where #15018 first observed the defect.
SUBDIR = "repo_tests"

#: ``(label, sys.path entry relative to the root, module, resolver attribute)``
#: for every site that asks git where the repository is. Adding a seventh site
#: without adding it here is what the static guard blocks.
SITES = [
    ("check_hook_exec_bits", "pipeline-scripts", "check_hook_exec_bits", "_repo_root"),
    (
        "check_requirements_no_conflicting_dupes",
        "pipeline-scripts",
        "check_requirements_no_conflicting_dupes",
        "_repo_root",
    ),
    ("check_port_fallbacks_match_ssot", "tools/lint", "check_port_fallbacks_match_ssot", "_repo_root"),
    (
        "check_ssh_key_path_defined",
        "autobot-slm-backend/ansible/tests",
        "check_ssh_key_path_defined",
        "_repo_root",
    ),
    ("sdk_defaults_match_ssot_test", "repo_tests", "sdk_defaults_match_ssot_test", "project_root"),
    ("collection_coverage_test", "repo_tests", "collection_coverage_test", "project_root"),
]


def _ambient_git_dir() -> str:
    """The ``GIT_DIR`` a hook would export here, or a skip outside a checkout."""
    out = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        env=scrubbed_git_env(),
        check=False,
    )
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip("not a git checkout — there is no ambient GIT_DIR to reproduce")
    return out.stdout.strip()


def _hook_env() -> dict[str, str]:
    """A child environment shaped like the one a git hook hands its children."""
    env = scrubbed_git_env()
    env["GIT_DIR"] = _ambient_git_dir()
    # The repository root has to be importable for ``autobot_shared``; the
    # scripts bootstrap that themselves, but the two pytest modules are
    # imported here directly.
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _require_the_defect_is_reproducible(env: dict[str, str]) -> None:
    """Skip unless an unscrubbed ``--show-toplevel`` really does answer the CWD.

    Asserting git's own behaviour would make this suite fail the day git stops
    misreading a bare ``GIT_DIR`` — a change that would make the scrub
    unnecessary rather than broken. Skipping keeps the positive assertions
    below honest: they only claim to have reproduced something when the
    environment can still produce it.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT / SUBDIR),
        env=env,
        check=False,
    )
    if out.stdout.strip() != str(REPO_ROOT / SUBDIR):
        pytest.skip(f"an ambient GIT_DIR no longer redirects --show-toplevel here (got {out.stdout.strip()!r})")


def test_scrubbed_git_env_drops_every_ambient_variable() -> None:
    scrubbed = scrubbed_git_env({"GIT_DIR": "/x", "GIT_WORK_TREE": "/y", "PATH": "/bin"})
    assert scrubbed == {"PATH": "/bin"}
    assert set(AMBIENT_GIT_VARS) == {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}


def test_git_repo_root_ignores_an_ambient_git_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shared helper answers the root even when asked from a subdirectory."""
    env = _hook_env()
    _require_the_defect_is_reproducible(env)
    monkeypatch.setenv("GIT_DIR", env["GIT_DIR"])
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)
    assert git_repo_root(REPO_ROOT / SUBDIR) == REPO_ROOT


def test_git_repo_root_raises_rather_than_guessing(tmp_path: Path) -> None:
    """Outside any checkout the helper raises; no caller receives a wrong path."""
    with pytest.raises(GitRepoRootUnavailable):
        git_repo_root(tmp_path / "does-not-exist")


@pytest.mark.parametrize(
    ("label", "path_entry", "module", "attribute"),
    SITES,
    ids=[site[0] for site in SITES],
)
def test_site_resolves_the_repo_root_under_an_ambient_git_dir(
    label: str, path_entry: str, module: str, attribute: str
) -> None:
    """Each site's own resolver, run from a subdirectory with ``GIT_DIR`` exported.

    Run out of process on purpose: ``GIT_DIR`` has to be in the *environment* of
    the git subprocess the site starts, and several of these modules exit the
    interpreter on failure.
    """
    env = _hook_env()
    _require_the_defect_is_reproducible(env)
    program = (
        "import sys;"
        f"sys.path.insert(0, {str(REPO_ROOT / path_entry)!r});"
        f"import {module} as m;"
        f"print(m.{attribute}())"
    )
    out = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT / SUBDIR),
        env=env,
        check=False,
    )
    assert out.returncode == 0, f"{label} could not resolve a root: {out.stderr.strip()}"
    assert out.stdout.strip() == str(REPO_ROOT), (
        f"{label} resolved {out.stdout.strip()!r} instead of the repository root. "
        "An ambient GIT_DIR made git call the caller's CWD the work tree — the "
        "site is asking git for the root without scrubbing the environment (#15176)."
    )
