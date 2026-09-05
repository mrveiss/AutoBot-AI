# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module-level ``int(os.getenv(...))`` crashes a service at import (#15691).

``_TIMEOUT = float(os.getenv("SOME_VAR", "30"))`` at module level raises
``ValueError`` on a malformed value -- not at the call site where the bad
setting is used, but at IMPORT, so a service that imports this module fails
to start entirely. A typo in an env file, a shell quoting slip, or an empty
string all trip it. ``autobot_shared/env_utils.py`` exports
``env_int``/``env_float`` (crash-safe, no clamp) and
``env_int_clamped``/``env_float_clamped`` (crash-safe, optionally bounded)
for exactly this shape.

Three were fixed one reviewer-catch at a time before this guard existed
(#15618, #15688) -- that is how a population of this shape reaches 47 without
anyone deciding it should. #15691 re-derived the population with an AST pass
and converted 36 of the 43 it found; this guard is what keeps the other 36
converted and stops a new bare cast from joining the 7 still recorded in
``env_var_bare_cast_allowlist.py``.

Matches deliberately narrow, the same way ``npm_test_scripts_run_in_ci_test``
narrows to a test-shaped script rather than every npm invocation:

* **module level only** -- a top-level statement in the module body, not one
  inside a function or class. A cast inside a function re-runs and re-raises
  on every call, so a caller already sees it; it is the IMPORT-time crash
  this guard exists for.
* **a direct ``int(...)``/``float(...)`` wrapping ``os.getenv(...)``
  specifically** -- not ``os.environ.get(...)`` (issue #15710 tracks that
  spelling separately: same behaviour, since ``os.getenv`` is implemented as
  ``os.environ.get(key, default)``, but a different population #15691 did not
  size or triage), and not one nested inside another call such as
  ``max(1, int(os.getenv(...)))`` (already partly mitigated -- it has a
  floor -- so it is a smaller, different defect from the bare crash this
  guard tracks).
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from autobot_shared.paths import GitRepoRootUnavailable, git_repo_root, scrubbed_git_env
from repo_tests.env_var_bare_cast_allowlist import BARE_ENV_CASTS, MAX_BARE_ENV_CASTS

#: A path this scan never reaches: tests (whatever their naming convention),
#: this guard's own package, and vendored/agent-worktree copies of the tree.
_EXCLUDED_PATH_FRAGMENTS = ("/tests/", "/test_", "/repo_tests/", "/.claude/", "/.worktrees/")


def _is_scanned(rel: str) -> bool:
    if any(fragment in f"/{rel}" for fragment in _EXCLUDED_PATH_FRAGMENTS):
        return False
    name = Path(rel).name
    return not (name.endswith("_test.py") or name.startswith("test_"))


def repo_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout."""
    try:
        return git_repo_root(Path(__file__).resolve().parent)
    except GitRepoRootUnavailable:
        pytest.skip("not a git checkout -- this check enumerates tracked files")


def tracked_python_files(root: Path) -> list[str]:
    """Tracked ``.py`` files this guard's population covers, relative to *root*."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.split()
    return [rel for rel in out if _is_scanned(rel)]


def _is_bare_getenv_cast(value: ast.expr) -> str | None:
    """``"int"``/``"float"`` when *value* is that cast directly wrapping
    ``os.getenv(...)``; ``None`` otherwise."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not (isinstance(func, ast.Name) and func.id in ("int", "float")):
        return None
    if not value.args:
        return None
    inner = value.args[0]
    if not isinstance(inner, ast.Call):
        return None
    inner_func = inner.func
    is_os_getenv = (
        isinstance(inner_func, ast.Attribute)
        and inner_func.attr == "getenv"
        and isinstance(inner_func.value, ast.Name)
        and inner_func.value.id == "os"
    )
    return func.id if is_os_getenv else None


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


def bare_casts_in_file(path: Path) -> list[str]:
    """Variable names bound to a bare ``int``/``float`` ``os.getenv`` cast at
    module level in *path*, or ``[]`` for an unreadable/unparseable file.

    Module level only: this walks ``tree.body`` directly and never descends
    into a function or class, matching the guard's own stated scope.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    found = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if _is_bare_getenv_cast(node.value):
                found.extend(_assigned_names(node))
    return found


class Measurement(NamedTuple):
    """One sweep of the checkout: every bare cast this guard's scope covers."""

    files_scanned: int
    found: dict[str, list[str]]  # rel path -> variable names

    @property
    def keys(self) -> set[str]:
        return {f"{rel}::{name}" for rel, names in self.found.items() for name in names}


@pytest.fixture(scope="module")
def measurement() -> Measurement:
    root = repo_root()
    rels = tracked_python_files(root)
    found = {rel: names for rel in rels if (names := bare_casts_in_file(root / rel))}
    return Measurement(len(rels), found)


#: Floor on files reached, so a scanner that has stopped walking the tree
#: fails loudly instead of passing on an empty sweep (the #15018 lesson).
#: Measured on Dev_new_gui: comfortably above 1000 tracked, non-test .py files.
MIN_FILES_SCANNED = 500


def test_enumeration_is_not_vacuous(measurement: Measurement) -> None:
    """The floor binds to the sweep's REACH, never to a count of findings."""
    assert measurement.files_scanned >= MIN_FILES_SCANNED, (
        f"only {measurement.files_scanned} tracked, non-test .py files reached; "
        "tracked_python_files has stopped walking the tree"
    )


def test_every_bare_cast_is_allowlisted(measurement: Measurement) -> None:
    """The #15691 assertion: a new bare module-level env cast is a defect."""
    unaccounted = sorted(measurement.keys - set(BARE_ENV_CASTS))
    assert not unaccounted, (
        "these module-level assignments are a bare int()/float() cast directly "
        "wrapping os.getenv(...), which raises ValueError at IMPORT on a "
        "malformed value -- convert to autobot_shared.env_utils's env_int / "
        "env_float / env_int_clamped / env_float_clamped, or record the site "
        f"(with an issue number) in env_var_bare_cast_allowlist.BARE_ENV_CASTS: {unaccounted}"
    )


def test_allowlist_entries_are_live_and_carry_an_issue(measurement: Measurement) -> None:
    """A converted site's entry must be deleted, not left to rot."""
    stale = sorted(set(BARE_ENV_CASTS) - measurement.keys)
    assert not stale, (
        f"BARE_ENV_CASTS entries no longer describe a bare cast in the tree -- the "
        f"site was converted; delete the entry and lower MAX_BARE_ENV_CASTS: {stale}"
    )
    unreferenced = sorted(key for key, reason in BARE_ENV_CASTS.items() if "#" not in reason)
    assert not unreferenced, f"allowlist reasons must name the issue that decided or tracks them: {unreferenced}"


def test_population_has_not_regrown(measurement: Measurement) -> None:
    """Shrink-only (#15691): a converted site must lower the ceiling, never raise it."""
    current = len(measurement.keys)
    assert current <= MAX_BARE_ENV_CASTS, (
        f"{current} bare module-level env casts found, over the recorded ceiling of "
        f"{MAX_BARE_ENV_CASTS}. This ceiling only ever goes down -- convert the new "
        "site(s), or if this run legitimately found fewer than before, lower "
        "MAX_BARE_ENV_CASTS in env_var_bare_cast_allowlist.py to match."
    )


# --------------------------------------------------------------------------
# Contrast fixtures: an input that SHOULD trip the classifier and a near miss
# that should not, so a matcher that matched everything (or nothing) fails
# these instead of passing silently on the real tree.
# --------------------------------------------------------------------------

CAST_CONTRASTS = (
    ('_X = int(os.getenv("VAR", "1"))', "int"),
    ('_X: int = int(os.getenv("VAR", "1"))', "int"),
    ('_X = float(os.getenv("VAR", "1.0"))', "float"),
    # os.environ.get is a different, untracked population (#15710).
    ('_X = int(os.environ.get("VAR", "1"))', None),
    # Already floored via max()/min() -- a smaller, different defect (#15691).
    ('_X = max(1, int(os.getenv("VAR", "1")))', None),
    # A crash-safe reader is not this shape at all.
    ('_X = env_int("VAR", 1)', None),
    # A cast of something other than a bare os.getenv call.
    ('_X = int(some_other_call("VAR"))', None),
    ('_X = int("1")', None),
)


@pytest.mark.parametrize(("source", "expected"), CAST_CONTRASTS)
def test_bare_cast_classifier_discriminates(source: str, expected: str | None) -> None:
    tree = ast.parse(source)
    assert _is_bare_getenv_cast(tree.body[0].value) == expected, source


def test_bare_cast_is_module_level_only(tmp_path: Path) -> None:
    """A cast inside a function body is out of this guard's stated scope."""
    target = tmp_path / "sample.py"
    target.write_text(
        'import os\n\n\ndef f():\n    return int(os.getenv("VAR", "1"))\n',
        encoding="utf-8",
    )
    assert bare_casts_in_file(target) == []


def test_bare_cast_at_module_level_is_found(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text('import os\n\n_TIMEOUT = int(os.getenv("VAR", "1"))\n', encoding="utf-8")
    assert bare_casts_in_file(target) == ["_TIMEOUT"]
