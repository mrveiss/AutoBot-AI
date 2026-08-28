# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical project-root resolution for Python code (#13149).

Every call site used to paste the shell placeholder
``"${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}"`` into a Python string
literal. Python does not expand shell syntax inside string literals, so those
paths resolved to a *literal directory name* — reads missed and ``mkdir``
either failed on the missing parent or created a junk tree actually named
``${AUTOBOT_PROJECT_ROOT:-``.

That defect was fixed once for ``sys.path`` manipulation (#4945) and once for a
single shell script (#13092), but neither fix propagated, because there was no
shared way to ask "where is the project root?". This module is that way.

Deliberately **stdlib-only**. ``autobot_shared.ssot_config`` is the natural home
for the logic and already owned it, but importing it pulls in pydantic and
builds every settings model — far too heavy for the standalone tooling scripts
that make up most of the call sites, and a circular import for
``ssot_config`` itself. ``ssot_config`` now delegates here, so there is exactly
one implementation rather than two that can drift.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from collections.abc import Mapping
from pathlib import Path

#: Markers that identify a source checkout root and nothing below it. Both must
#: be present: ``autobot_shared`` alone also matches the package directory's own
#: parent in some layouts, and ``.git`` alone would match an unrelated repo if
#: this package were ever vendored into one.
#:
#: ``.git`` is tested with ``exists()`` rather than ``is_dir()`` on purpose — in
#: a ``git worktree`` it is a *file* pointing at the real git directory, and
#: this repository's whole workflow runs from worktrees.
CHECKOUT_MARKERS = (".git", "autobot_shared")

#: Prefix of the component directories a deployed install places beside
#: ``autobot_shared`` (``autobot-backend``, ``autobot-npu-worker``, ...).
#:
#: A PREFIX, not a list of names. The first version of this enumerated four
#: components and would have left a node carrying only, say, ``autobot-npu-worker``
#: unable to resolve — precisely the minimal fleet nodes most likely to hit it.
#: This install alone has twelve such directories, and the set grows with every
#: new component (#14624).
INSTALL_COMPONENT_PREFIX = "autobot-"

#: Environment variable naming an explicit project root. This is the same name
#: the shell scripts honour, so exporting it once governs both languages.
PROJECT_ROOT_ENV = "AUTOBOT_PROJECT_ROOT"

#: Environment variable naming an explicit deployed-install location. Distinct
#: from ``PROJECT_ROOT_ENV``: this one is read only as the last resort, after
#: the walk in step 2 has found neither a ``.env`` nor a checkout.
BASE_DIR_ENV = "AUTOBOT_BASE_DIR"


class ProjectRootUndeterminable(RuntimeError):
    """No override, ``.env`` or checkout marker identifies the project root.

    #14544: this module used to answer that question with a hardcoded
    ``/opt/autobot`` guess. A wrong-but-plausible path is exactly how 18
    ``sys.path`` bootstraps silently imported the live deployed install
    instead of the checkout under test, and stayed invisible for as long as
    they did — the guess always looked like a working answer. Raising here
    forces every caller to say explicitly where it is running (via
    ``AUTOBOT_PROJECT_ROOT`` or ``AUTOBOT_BASE_DIR``) instead of getting one
    handed to it silently.
    """


def is_checkout_root(path: Path) -> bool:
    """True when *path* looks like the root of a source checkout."""
    return all((path / marker).exists() for marker in CHECKOUT_MARKERS)


def is_install_root(path: Path) -> bool:
    """True when *path* looks like a deployed install root (#14624).

    A deployed install satisfies none of the other arms, which took down a live
    SLM backend: `/opt/autobot` has no `.git` (so `is_checkout_root` is False,
    correctly — it is not a checkout) and no top-level `.env` either, because
    the per-component files live one level down (`autobot-backend/.env`,
    `autobot-ai-stack/.env`, ...). `resolve_project_root` therefore raised on
    import and uvicorn exited 1 in a restart loop.

    The deployment does normally set ``AUTOBOT_PROJECT_ROOT`` — the unit
    template renders it — but the raise then depends on every host's systemd
    unit being current, and the host this was found on had one from two months
    earlier. A resolution that only works where deployed state is fresh is not
    a resolution; this arm makes the layout recognisable on its own terms.

    Deliberately narrow, and NOT a relaxation of ``CHECKOUT_MARKERS``: those
    require both markers for reasons that still hold (see their comment). An
    install is identified by `autobot_shared` sitting beside at least one
    deployed component directory — a shape a package's own parent does not
    have, and one that never appears above a checkout or worktree root.
    """
    if not (path / "autobot_shared").exists():
        return False
    return any(child.is_dir() and child.name.startswith(INSTALL_COMPONENT_PREFIX) for child in path.iterdir())


def project_root() -> Path:
    """Resolve the project root: explicit env, configured deployment, checkout, install.

    Resolution order, first match wins:

    1. ``AUTOBOT_PROJECT_ROOT`` — an operator saying so outranks any inference,
       and matches what the shell scripts already do.
    2. Walking up from this file, the nearest ancestor that either holds a
       ``.env`` (a configured deployment) **or** looks like a source checkout.
    3. ``AUTOBOT_BASE_DIR`` — an operator naming the deployed install
       explicitly. There is no further, unconditional fallback: on a real
       checkout or a real install, step 1 or step 2 always resolves first
       (an install always carries a ``.env``), so reaching here at all means
       the environment is too broken to place. Raises
       :class:`ProjectRootUndeterminable` rather than guessing (#14544).

    Step 2 is a *single* walk on purpose, and a checkout root is a hard
    boundary. The two-pass form — all ancestors for ``.env``, then all
    ancestors for the checkout markers — looks equivalent and is not: this
    repository's worktrees live at ``<main-tree>/.worktrees/<name>/`` and are
    git-ignored, so a worktree has no ``.env`` of its own. The ``.env`` pass
    would climb straight past the worktree root and match the **main tree's**
    ``.env``, resolving every worktree's project root to the main checkout.
    Since the whole workflow runs from worktrees, that pointed each one's
    config, log and results paths at another tree (#13149).

    Stopping at the first checkout root also bounds the walk correctly for the
    deployment case: an install has a ``.env`` and no ``.git``, so it matches on
    the ``.env`` arm before any checkout marker is ever seen.

    Deliberately **not** cached. Caching looks free — the answer rarely changes
    within a process — but it silently defeats any caller that sets
    ``AUTOBOT_PROJECT_ROOT`` or ``AUTOBOT_BASE_DIR`` after the first call, which
    is exactly what the drift detector's own fallback test does. The walk is a
    handful of ``stat`` calls against a short ancestor chain; hidden state is
    the more expensive of the two.
    """
    return resolve_project_root(Path(__file__).resolve())


def resolve_project_root(start: Path) -> Path:
    """The resolution itself, walking upward from *start*.

    Split out from :func:`project_root` so the walk can be exercised against a
    temporary directory tree — the entry point is pinned to this file's own
    location and cannot be pointed at a fixture.
    """
    # ssot-config-exempt: bootstrap — this module resolves the root that
    # ssot_config itself needs, so it cannot import config.
    configured = os.environ.get(PROJECT_ROOT_ENV)
    if configured:
        return Path(configured).resolve()

    # #14640 review: an OSError while inspecting a candidate is remembered rather
    # than swallowed. Returning False on a permissions failure still fails loud
    # (nothing else matches, so the raise below fires), but the message would
    # blame an unrecognised layout when the real cause was an unreadable
    # directory that IS the right root. This module already cost one long
    # outage; the diagnosis should not have to be reconstructed twice.
    inspection_errors: list[str] = []

    for parent in [start] + list(start.parents):
        try:
            if (parent / ".env").exists() or is_checkout_root(parent) or is_install_root(parent):
                return parent
        except OSError as exc:
            inspection_errors.append(f"{parent}: {exc.__class__.__name__}: {exc}")

    # ssot-config-exempt: bootstrap self-reference (carried from the
    # implementation this replaced, landed in #13646).
    base_dir = os.environ.get(BASE_DIR_ENV)
    if base_dir:
        return Path(base_dir)

    raise ProjectRootUndeterminable(
        f"cannot determine the project root by walking up from {start}: no "
        f"{PROJECT_ROOT_ENV} override, no {BASE_DIR_ENV} override, and no "
        "ancestor holds a .env or looks like a source checkout "
        f"({', '.join(CHECKOUT_MARKERS)}). Set one of those two environment "
        "variables — a silent guess is the defect this raise replaces (#14544)."
        + (
            "\n\nNote: some candidates could not be inspected, which may be the real "
            "cause rather than an unrecognised layout: " + "; ".join(inspection_errors)
            if inspection_errors
            else ""
        )
    )


#: Git variables a hook exports into every process it starts. With ``GIT_DIR``
#: set and ``GIT_WORK_TREE`` unset — exactly what a ``pre-commit``/``pre-push``
#: hook hands its children — git treats the **current directory** as the work
#: tree, so ``rev-parse --show-toplevel`` answers with wherever the caller
#: happens to be rather than the repository root.
#:
#: The answer is wrong without being an error, which is the whole reason this
#: is a named constant rather than a line inside one caller: a guard that
#: resolves the wrong root reads a different (usually empty) set of files and
#: reports clean. #15018 hit the raising half of that — ``pytest.ini`` read from
#: ``repo_tests/`` and ``FileNotFoundError`` — and #15176 measured the silent
#: half: two pre-commit guards printed their success line having inspected
#: nothing at all.
#:
#: Measured on git 2.34.1 rather than assumed. A hook run in a **git worktree**
#: -- this repository's entire workflow -- is handed
#: ``GIT_DIR=<main>/.git/worktrees/<name>`` with no ``GIT_WORK_TREE``, for both
#: ``pre-commit`` and ``pre-push``; a hook in a plain checkout on that version is
#: handed neither. Git also chdirs the hook to the worktree top level, even when
#: the user ran ``git commit`` from a subdirectory, so the *hook itself* still
#: gets the right answer. What breaks is anything the hook then runs from
#: somewhere else -- a helper passing ``cwd=``, a test module, a CI step
#: invoking a guard directly. That is the whole distance between "correct today"
#: and "correct".
AMBIENT_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


class GitRepoRootUnavailable(RuntimeError):
    """``git rev-parse --show-toplevel`` could not name a repository root.

    Raised rather than returning ``None`` so a caller has to decide what an
    absent root means for it: the tooling scripts exit fatally, the pytest
    guards skip. Both are correct answers; silently continuing with a
    plausible-looking wrong path is not (#14544 records what that costs).
    """


def scrubbed_git_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """*env* (default :data:`os.environ`) minus every :data:`AMBIENT_GIT_VARS` entry.

    Use for **any** git subprocess whose answer depends on the work tree, not
    only ``rev-parse``: ``ls-files`` inherits the same confusion.
    """
    source = os.environ if env is None else env
    return {key: value for key, value in source.items() if key not in AMBIENT_GIT_VARS}


def git_repo_root(start: Path | str | None = None) -> Path:
    """Repository root containing *start*, asked of git with the environment scrubbed.

    *start* is the directory the question is asked from (default: the process
    working directory). It selects which checkout answers — this repository's
    workflow runs from worktrees, so "the repository root" is genuinely
    caller-relative — while :data:`AMBIENT_GIT_VARS` scrubbing is what stops an
    inherited hook environment from turning that directory into the answer.

    Deliberately git-driven rather than :func:`project_root`: every caller here
    goes on to run ``git ls-files`` against the result, so the root and the file
    enumeration must come from the same checkout. Resolving the root by walking
    for markers and then enumerating with git is two answers that can disagree.

    Raises:
        GitRepoRootUnavailable: git is absent, failed, or named nothing.
    """
    try:
        result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=None if start is None else str(start),
            env=scrubbed_git_env(),
            check=False,
        )
    except OSError as exc:  # git not installed, or *start* is not a directory
        raise GitRepoRootUnavailable(f"could not run git rev-parse: {exc}") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise GitRepoRootUnavailable(f"git rev-parse --show-toplevel exit {result.returncode}: {result.stderr.strip()}")
    return Path(result.stdout.strip())
