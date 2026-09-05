# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A module-level ``int(os.getenv(...))`` crashes a service at import (#15691, #15710).

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
over the ``os.getenv(...)`` spelling and converted 36 of the 43 it found.
``os.getenv`` is implemented as ``os.environ.get(key, default)`` in CPython,
so the same shape written the other way -- ``int(os.environ.get(...))`` --
is the identical import-time crash, but #15691's own matcher covered only
the literal ``os.getenv`` spelling and never sized or triaged it. #15710
extended the matcher to the ``os.environ.get(...)`` spelling too, re-derived
that population (58 sites across 31 files) and converted every one of them --
there was no operator-run-script or packaging-isolation reason to leave any
of them bare, unlike the #15691 sweep. This guard is what keeps both
spellings' converted sites converted and stops a new bare cast, in either
spelling, from joining the 7 still recorded in
``env_var_bare_cast_allowlist.py`` (all from the original #15691 population).

Matches deliberately narrow, the same way ``npm_test_scripts_run_in_ci_test``
narrows to a test-shaped script rather than every npm invocation:

* **module level only** -- a top-level statement in the module body, not one
  inside a function or class. A cast inside a function re-runs and re-raises
  on every call, so a caller already sees it; it is the IMPORT-time crash
  this guard exists for.
* **an ``int(...)``/``float(...)`` wrapping ``os.getenv(...)`` OR
  ``os.environ.get(...)``**, either directly or through a transparent
  wrapper -- ``max``, ``min``, ``abs``, ``round``, in a positional or a
  keyword argument. A floor does NOT make the cast safe: ``max(1,
  int(os.getenv(...)))`` evaluates the cast first, so it dies at import
  exactly as the bare form does, and the floor applies to the parsed number
  rather than to the parse. An earlier draft of this guard excluded that
  shape as "already partly mitigated", which protected the population it
  drained while leaving eleven converted sites free to come back.

  Not covered: a subscript form (``os.environ["VAR"]``), which raises
  ``KeyError`` rather than silently defaulting and so is a different,
  already-loud failure mode; and a cast embedded in a larger expression
  such as ``int(os.environ.get(...)) * 1024`` (#15717), which is the same
  crash in a shape this classifier does not yet reach.
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


#: Calls that wrap a cast without changing when it raises. ``max(1, int(...))``
#: still evaluates the cast first, so it crashes at import on a malformed value
#: exactly as the bare form does -- the floor applies to the parsed number, not
#: to the parse. #15691 converted eleven of these; without them in scope the
#: guard would protect the sites it drained and not the ones it fixed.
_TRANSPARENT_WRAPPERS = frozenset({"max", "min", "abs", "round"})


def _is_os_getenv_call(call: ast.Call) -> bool:
    """``True`` for ``os.getenv(...)`` specifically."""
    func = call.func
    return isinstance(func, ast.Attribute) and func.attr == "getenv" and _is_os_name(func.value)


def _is_os_environ_get_call(call: ast.Call) -> bool:
    """``True`` for ``os.environ.get(...)`` specifically.

    Not the subscript form ``os.environ["VAR"]`` -- that raises ``KeyError``
    immediately rather than silently accepting a malformed default, so it is
    already a loud failure and not this guard's shape.
    """
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "get"):
        return False
    environ_attr = func.value
    return (
        isinstance(environ_attr, ast.Attribute) and environ_attr.attr == "environ" and _is_os_name(environ_attr.value)
    )


def _is_os_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "os"


def _is_bare_env_cast(value: ast.expr) -> str | None:
    """``"int"``/``"float"`` when *value* is that cast wrapping ``os.getenv(...)``
    or ``os.environ.get(...)`` (#15691, #15710 -- the same crash, two spellings:
    ``os.getenv`` is implemented as ``os.environ.get(key, default)`` in CPython).

    Looks through a transparent wrapper: the cast inside ``max(1, int(os.getenv(
    ...)))`` raises at the same moment the bare one does, so treating the two
    differently would let the shape come back under a floor.
    """
    if not isinstance(value, ast.Call):
        return None
    if isinstance(value.func, ast.Name) and value.func.id in _TRANSPARENT_WRAPPERS:
        # Keywords as well as positionals: `max(0, key=int(os.getenv(...)))`
        # evaluates the cast before the wrapper is called, so it raises at
        # import exactly as a positional one does.
        for arg in [*value.args, *(kw.value for kw in value.keywords)]:
            found = _is_bare_env_cast(arg)
            if found:
                return found
        return None
    func = value.func
    if not (isinstance(func, ast.Name) and func.id in ("int", "float")):
        return None
    if not value.args:
        return None
    inner = value.args[0]
    if not isinstance(inner, ast.Call):
        return None
    is_bare_env_read = _is_os_getenv_call(inner) or _is_os_environ_get_call(inner)
    return func.id if is_bare_env_read else None


def _target_key(target: ast.expr) -> str | None:
    """A stable name for an assignment target, or ``None`` when it has none.

    Plain names are the common case. An ATTRIBUTE target -- `settings.timeout =
    int(os.getenv(...))` -- used to yield nothing, so the site was detected and
    then dropped for want of a key: the guard saw the cast and accepted it
    silently. A subscript (`cfg["t"] = ...`) genuinely has no stable name; it is
    reported under its own marker rather than discarded.
    """
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        base = _target_key(target.value)
        return f"{base}.{target.attr}" if base else target.attr
    if isinstance(target, (ast.Subscript, ast.Tuple, ast.List, ast.Starred)):
        return "<unnamed-target>"
    return None


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [key for key in (_target_key(t) for t in targets) if key]


def bare_casts_in_file(path: Path) -> list[str]:
    """Variable names bound to a bare ``int``/``float`` ``os.getenv``/``os.environ.get``
    cast at module level in *path*.

    Raises rather than returning ``[]`` on an unparseable file. Swallowing the
    error returned "no casts here" while the caller still counted the file as
    scanned, so the reach floor was satisfied by files nothing had read -- a
    parse failure could hide an unallowlisted cast behind a green sweep.

    Module level only: this walks ``tree.body`` directly and never descends
    into a function or class, matching the guard's own stated scope.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if _is_bare_env_cast(node.value):
                found.extend(_assigned_names(node))
    return found


class Measurement(NamedTuple):
    """One sweep of the checkout: every bare cast this guard's scope covers."""

    files_scanned: int  # files actually PARSED, not files listed
    found: dict[str, list[str]]  # rel path -> variable names
    unparsed: tuple[str, ...]  # tracked files the walk could not read

    @property
    def keys(self) -> set[str]:
        return {f"{rel}::{name}" for rel, names in self.found.items() for name in names}


@pytest.fixture(scope="module")
def measurement() -> Measurement:
    root = repo_root()
    found: dict[str, list[str]] = {}
    unparsed: list[str] = []
    parsed = 0
    for rel in tracked_python_files(root):
        try:
            names = bare_casts_in_file(root / rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            unparsed.append(rel)
            continue
        parsed += 1
        if names:
            found[rel] = names
    return Measurement(parsed, found, tuple(unparsed))


#: Floor on files reached, so a scanner that has stopped walking the tree
#: fails loudly instead of passing on an empty sweep (the #15018 lesson).
#: Measured on Dev_new_gui: comfortably above 1000 tracked, non-test .py files.
MIN_FILES_SCANNED = 500


def test_every_tracked_file_was_actually_parsed(measurement: Measurement) -> None:
    """A file the walk could not read is not a file with no casts.

    Swallowing the parse error returned "nothing here" while the file still
    counted toward the reach floor, so an unallowlisted cast could sit behind a
    green sweep in a file nothing had read. Reach now counts files PARSED, and
    a failure is named rather than absorbed.
    """
    assert not measurement.unparsed, (
        "these tracked Python files could not be parsed, so the sweep cannot "
        f"speak for them: {list(measurement.unparsed)}"
    )


def test_enumeration_is_not_vacuous(measurement: Measurement) -> None:
    """The floor binds to the sweep's REACH, never to a count of findings."""
    assert measurement.files_scanned >= MIN_FILES_SCANNED, (
        f"only {measurement.files_scanned} tracked, non-test .py files reached; "
        "tracked_python_files has stopped walking the tree"
    )


def test_every_bare_cast_is_allowlisted(measurement: Measurement) -> None:
    """The #15691/#15710 assertion: a new bare module-level env cast is a defect,
    in either the ``os.getenv(...)`` or ``os.environ.get(...)`` spelling."""
    unaccounted = sorted(measurement.keys - set(BARE_ENV_CASTS))
    assert not unaccounted, (
        "these module-level assignments are a bare int()/float() cast directly "
        "wrapping os.getenv(...) or os.environ.get(...), which raises ValueError "
        "at IMPORT on a malformed value -- convert to autobot_shared.env_utils's "
        "env_int / env_float / env_int_clamped / env_float_clamped, or record "
        f"the site (with an issue number) in env_var_bare_cast_allowlist.BARE_ENV_CASTS: {unaccounted}"
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
    # os.environ.get is the same defect, the other spelling (#15710):
    # os.getenv is implemented as os.environ.get(key, default) in CPython.
    ('_X = int(os.environ.get("VAR", "1"))', "int"),
    ('_X: int = int(os.environ.get("VAR", "1"))', "int"),
    ('_X = float(os.environ.get("VAR", "1.0"))', "float"),
    # A floor does not make the cast safe: max() evaluates int() first, so this
    # dies at import on a malformed value exactly as the bare form does. #15691
    # converted eleven of these, so the classifier must see them or the guard
    # would protect the population it drained and not the sites it fixed.
    ('_X = max(1, int(os.getenv("VAR", "1")))', "int"),
    ('_X = min(60.0, float(os.getenv("VAR", "1.0")))', "float"),
    ('_X = max(1, int(os.environ.get("VAR", "1")))', "int"),
    # The wrapper is only transparent when a cast is actually inside it.
    ('_X = max(1, int(some_other_call("VAR")))', None),
    ('_X = max(1, 2)', None),
    # A keyword argument is evaluated before the wrapper is called, so a cast
    # hidden there raises at import exactly as a positional one does.
    ('_X = max(0, key=int(os.getenv("VAR", "1")))', "int"),
    ('_X = max(0, key=int(os.environ.get("VAR", "1")))', "int"),
    ('_X = max(0, key=len)', None),
    # A crash-safe reader is not this shape at all.
    ('_X = env_int("VAR", 1)', None),
    # A cast of something other than a bare os.getenv/os.environ.get call.
    ('_X = int(some_other_call("VAR"))', None),
    ('_X = int("1")', None),
    # The subscript form raises KeyError immediately -- already loud, and not
    # the ".get(...)" silent-default shape this guard tracks.
    ('_X = int(os.environ["VAR"])', None),
    # "environ" must resolve through "os" specifically, not any object that
    # happens to expose a same-named attribute chain.
    ('_X = int(other.environ.get("VAR", "1"))', None),
)


@pytest.mark.parametrize(("source", "expected"), CAST_CONTRASTS)
def test_bare_cast_classifier_discriminates(source: str, expected: str | None) -> None:
    tree = ast.parse(source)
    assert _is_bare_env_cast(tree.body[0].value) == expected, source


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


def test_bare_cast_at_module_level_is_found_os_environ_get_spelling(tmp_path: Path) -> None:
    """#15710: the file-level sweep, not just the classifier unit, catches this
    spelling -- a new ``os.environ.get(...)`` violation must fail the same way
    a new ``os.getenv(...)`` one does, end to end through ``bare_casts_in_file``."""
    target = tmp_path / "sample.py"
    target.write_text('import os\n\n_TIMEOUT = int(os.environ.get("VAR", "1"))\n', encoding="utf-8")
    assert bare_casts_in_file(target) == ["_TIMEOUT"]


def test_an_attribute_target_is_reported_not_dropped(tmp_path: Path) -> None:
    """A detected cast must never be discarded for want of a name.

    `settings.timeout = int(os.getenv(...))` reaches the classifier, but an
    attribute target yielded no key, so the finding was collected and then
    thrown away -- the guard saw the defect and accepted it. Reported under its
    dotted name now.
    """
    target = tmp_path / "attr.py"
    target.write_text('import os\nsettings.timeout = int(os.getenv("VAR", "1"))\n', encoding="utf-8")
    assert bare_casts_in_file(target) == ["settings.timeout"]


def test_an_unparseable_file_raises_rather_than_reading_as_clean(tmp_path: Path) -> None:
    """The contrast to the reach floor: 'cannot read' is not 'nothing here'."""
    target = tmp_path / "broken.py"
    target.write_text("def (:\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        bare_casts_in_file(target)
