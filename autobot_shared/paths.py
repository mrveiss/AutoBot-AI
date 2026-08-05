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

#: Environment variable naming an explicit project root. This is the same name
#: the shell scripts honour, so exporting it once governs both languages.
PROJECT_ROOT_ENV = "AUTOBOT_PROJECT_ROOT"

#: Where a deployed install lives when nothing else identifies the root.
DEFAULT_INSTALL_ROOT = "/opt/autobot"


def is_checkout_root(path: Path) -> bool:
    """True when *path* looks like the root of a source checkout."""
    return all((path / marker).exists() for marker in CHECKOUT_MARKERS)


def project_root() -> Path:
    """Resolve the project root: explicit env, configured deployment, checkout, install.

    Resolution order, first match wins:

    1. ``AUTOBOT_PROJECT_ROOT`` — an operator saying so outranks any inference,
       and matches what the shell scripts already do.
    2. Walking up from this file, the nearest ancestor that either holds a
       ``.env`` (a configured deployment) **or** looks like a source checkout.
    3. ``AUTOBOT_BASE_DIR``/``/opt/autobot`` — the deployed install.

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
    configured = os.environ.get(PROJECT_ROOT_ENV)
    if configured:
        return Path(configured).resolve()

    for parent in [start] + list(start.parents):
        if (parent / ".env").exists() or is_checkout_root(parent):
            return parent

    return Path(os.environ.get("AUTOBOT_BASE_DIR", DEFAULT_INSTALL_ROOT))
