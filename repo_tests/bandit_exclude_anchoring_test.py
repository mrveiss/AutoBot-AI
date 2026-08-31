# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14489 — every ``.bandit`` ``exclude_dirs`` entry must mean the path it was written for.

bandit's matcher (``bandit/core/manager.py``, ``_is_file_included``) tests every
``exclude_dirs`` entry with ``x in path for x in excluded_path_strings`` — a raw
**substring** test against the full candidate path, with no path-component
boundary. A bare entry therefore excludes any path that merely *contains* the
string anywhere, including mid-filename — broader than flake8's #14419 defect,
which at least compares against ``os.path.basename()``.

Written bare, ``temp``, ``logs``, ``reports``, ``archive`` and ``venv`` silently
excluded 34 tracked production files that none of them named as a real
*tracked* directory anywhere in the repo — every file under
``autobot-backend/workflow_templates/`` among them, via ``temp``. Nothing
reported them as unscanned; a planted hardcoded-password literal in one of
those paths was silently skipped by the old config and caught by the new one.

ABSENT FROM ``git ls-files`` IS NOT ABSENT: bandit walks the filesystem, not
the git index. A first pass at this fix dropped ``venv`` and ``logs``
entirely on that exact confusion. Checked against the real filesystem
instead: ``venv`` is a real, gitignored, ~26k-file dependency tree at the
repo root (walked in full by any local ``bandit -c .bandit -r .``), and
``logs`` is a real, gitignored, ``.gitignore``-documented runtime log
directory that exists inside ``autobot-backend/`` and
``autobot-slm-backend/`` — the trees CI actually scans. Both are restored,
anchored (``/venv/``, ``/logs/``). ``temp``, ``reports`` and ``archive`` are
confirmed absent everywhere on disk (via ``find``, not ``git ls-files``), so
those three stay dropped.

The invariant enforced here:

* a bare entry is allowed only if it covers **no tracked Python anywhere in
  the repo**, tested with bandit's own substring rule
  (:func:`entries_covering_tracked_python`) — not a path-component rule,
  because bandit does not use one. This is the point of divergence from
  #14419's flake8 guard: ``venv`` passes a component check (no directory
  named ``venv`` holds tracked Python) but fails bandit's real substring
  check (``check_venv_producers.py`` carries "venv" in its filename), so a
  bare ``venv`` cannot pass this guard even though flake8's guard could keep
  it bare — hence ``venv`` is restored ANCHORED, not bare;
* every other entry must be wrapped in ``/`` on both sides — bandit never
  rewrites an entry into an absolute path the way flake8 does, so an entry
  with only a trailing ``/`` (``tests/``) is still an unbounded substring
  test and still matches ``repo_tests/foo.py``.

A second divergence from #14419: an anchored entry is not required to name a
directory that currently exists. ``/venv/`` and ``/logs/`` name gitignored
runtime directories that a fresh clone or a CI runner legitimately does not
have yet — the same "guard cannot demand something CI can never have" reason
:func:`entries_covering_tracked_python` is not applied to anchored entries.

The discrimination tests at the bottom run the checker against the config as
it stood before #14489. A guard that has never been shown to reject anything
is an assertion about nothing.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]
BANDIT_CONFIG = REPO_ROOT / ".bandit"
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_bandit_exclude_anchoring.py"


def _load_checker():
    """Import the checker by path.

    The decision lives in the script `code-quality` runs, not here. Restating
    it would give the guard two definitions that could drift, and the copy CI
    executes is the one that matters — a test agreeing with a second copy of
    the rule proves nothing about the check that blocks the merge.
    """
    spec = importlib.util.spec_from_file_location("check_bandit_exclude_anchoring", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()

ARTIFACT_DIR_NAMES = checker.ARTIFACT_DIR_NAMES
read_exclude_entries = checker.read_exclude_entries
bare_entries = checker.bare_entries
unanchored_source_entries = checker.unanchored_source_entries
unanchored_path_entries = checker.unanchored_path_entries
entries_covering_tracked_python = checker.entries_covering_tracked_python
is_glob_pattern = checker.is_glob_pattern

#: Floor for the tracked-Python enumeration. An enumeration that returns
#: nothing must not read as "no source is covered by a bare name".
_TRACKED_PY_FLOOR = checker.TRACKED_PY_FLOOR


@pytest.fixture(scope="module")
def entries() -> list[str]:
    return read_exclude_entries(BANDIT_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tracked_py_files() -> list[str]:
    """Every tracked ``*.py`` path, enumerated by git rather than by bandit."""
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(paths) >= _TRACKED_PY_FLOOR, (
        f"git ls-files returned only {len(paths)} Python files — the enumeration "
        "broke; these tests would otherwise pass having checked nothing"
    )
    return paths


# --------------------------------------------------------------------------
# The invariant
# --------------------------------------------------------------------------


def test_no_bare_directory_name_is_excluded(entries):
    """A bare name is an unbounded substring test — anchor it, or justify it as an artifact."""
    offenders = unanchored_source_entries(entries)
    assert offenders == [], (
        f"unanchored .bandit exclude_dirs entries {offenders} — bandit matches a "
        "separator-free entry as a raw substring of the full path, so each of "
        "these excludes any file whose path merely contains the string, at any "
        "depth (#14489). Wrap the path the entry was meant for in `/`, e.g. "
        "`/tests/` not `tests`."
    )


def test_path_entries_are_anchored_on_both_sides(entries):
    """A trailing-only separator (``tests/``) is still an unbounded substring test."""
    offenders = unanchored_path_entries(entries)
    assert offenders == [], (
        f"exclude_dirs entries anchored on only one side: {offenders}. bandit never "
        "rewrites an entry into an absolute path the way flake8 does, so `tests/` "
        "still matches `repo_tests/foo.py` as a raw substring — wrap it as `/tests/`."
    )


def test_artifact_names_cover_no_tracked_python(entries, tracked_py_files):
    """The artifact allowlist stays honest: none of its names may cover source.

    This is what stops the allowlist becoming the new hiding place, and it
    uses bandit's own substring rule rather than a path-component rule — the
    exact distinction that lets ``venv`` slip through a component-based check
    while still being unsafe under bandit's real matcher.
    """
    covered = entries_covering_tracked_python(entries, tracked_py_files)
    assert covered == {}, (
        f"bare exclude_dirs entries cover tracked Python: {covered}. These files are "
        "silently unscanned for security findings. Either the entry is not an "
        "artifact directory and must be wrapped in `/`, or the source under it "
        "does not belong there."
    )


def test_the_workflow_templates_package_is_scanned(entries, tracked_py_files):
    """The regression this issue was filed for, asserted on the outcome.

    ``autobot-backend/workflow_templates/`` is production code. It was
    unscanned purely because its directory name contains ``temp`` as a
    substring.
    """
    package = "autobot-backend/workflow_templates"
    assert (REPO_ROOT / package).is_dir(), f"{package} moved — update this test"
    files = [p for p in tracked_py_files if p.startswith(package + "/")]
    assert files, f"{package} has no tracked Python — update this test"
    bare = set(bare_entries(entries))
    for path in files:
        assert not any(entry in path for entry in bare), f"{path} is excluded by a bare entry"


def test_venv_and_logs_are_restored_anchored_not_dropped(entries):
    """Regression pin: a name real on disk must not be dropped as if absent.

    ``git ls-files`` never sees ``venv/`` or ``logs/`` (both gitignored), but
    both are real directories on disk — ``venv/`` a ~26k-file dependency tree
    at the repo root, ``logs/`` a runtime log directory nested inside the
    trees CI scans. Dropping either (as a first pass at this fix did) reads
    as clean against the git-tracked measurement while a local
    ``bandit -c .bandit -r .`` would walk all 26k dependency files. They must
    be present, anchored on both sides — not bare, because bandit's substring
    matcher still catches ``venv`` through a filename alone (see
    ``test_venv_fails_the_bandit_matcher_even_though_no_venv_directory_exists``
    below).
    """
    assert "/venv/" in entries, "venv must be excluded, anchored — it is a real, gitignored dependency tree"
    assert "/logs/" in entries, "logs must be excluded, anchored — it is a real, gitignored runtime directory"
    assert "venv" not in bare_entries(entries), "venv must not be bare: it still matches a filename substring"
    assert "logs" not in bare_entries(entries), "logs must not be bare, for the same reason as venv"


def test_guard_and_config_agree_on_venv_and_logs(entries, tracked_py_files):
    """The guard and ``.bandit`` must not disagree about ``venv``/``logs``.

    The guard fails a BARE ``venv``/``logs`` (they cover tracked Python via
    bandit's substring rule) but has no opinion on the ANCHORED form used in
    the live config — ``entries_covering_tracked_python`` only ever inspects
    :func:`bare_entries`. Pinned explicitly so the two conditions this test
    name promises are both checked, not just implied by the fixture parsing
    the live file.
    """
    assert unanchored_source_entries(entries) == [], "an anchored venv/logs must not be flagged as unanchored"
    covered = entries_covering_tracked_python(entries, tracked_py_files)
    assert "venv" not in covered and "logs" not in covered, (
        "entries_covering_tracked_python only inspects bare entries, so an anchored "
        "/venv//logs/ correctly never appears here"
    )


# --------------------------------------------------------------------------
# Discrimination — the guard must reject the config it was written against
# --------------------------------------------------------------------------

#: The exclude_dirs list exactly as it stood before #14489, kept as a fixed
#: reference point. Do NOT "sync" this to the current config: its whole job
#: is to be the thing the guard says no to.
PRE_FIX_EXCLUDE_DIRS = """
exclude_dirs:
  - node_modules
  - .venv
  - venv
  - __pycache__
  - temp
  - logs
  - reports
  - archive
  - tests
  - "*_test.py"
  - "*/test_*.py"

skips:
  - B101
"""


def test_guard_rejects_the_pre_fix_config():
    """Against the old list the guard must go red, naming the bare directories."""
    offenders = unanchored_source_entries(read_exclude_entries(PRE_FIX_EXCLUDE_DIRS))
    for expected in ("temp", "logs", "reports", "archive", "venv", "tests"):
        assert expected in offenders, f"guard failed to flag bare `{expected}`"


def test_guard_rejects_a_bare_name_smuggled_into_the_artifact_list(tracked_py_files):
    """Widening ARTIFACT_DIR_NAMES must not be a way to re-hide source."""
    covered = entries_covering_tracked_python(["temp", "archive"], tracked_py_files)
    assert covered.get("temp", 0) > 0
    assert covered.get("archive", 0) > 0


def test_venv_fails_the_bandit_matcher_even_though_no_venv_directory_exists(tracked_py_files):
    """The exact divergence from #14419's component-based flake8 guard.

    No directory named ``venv`` holds tracked Python anywhere in the repo, so
    a component-based check would call ``venv`` safe. bandit's real matcher
    is a substring test, and it still catches two files through their
    filename alone — proving the check below must use bandit's rule, not
    flake8's.
    """
    covered = entries_covering_tracked_python(["venv"], tracked_py_files)
    assert covered.get("venv", 0) >= 2, covered
    component_hits = [p for p in tracked_py_files if "venv" in p and "venv" in p.split("/")]
    assert component_hits == [], "a real venv/ directory now exists with tracked Python — update this test"


def test_guard_accepts_the_current_config(entries, tracked_py_files):
    """Both directions on the live config, so a passing suite means something."""
    assert unanchored_source_entries(entries) == []
    assert unanchored_path_entries(entries) == []
    assert entries_covering_tracked_python(entries, tracked_py_files) == {}


def test_test_file_globs_are_unaffected_by_the_substring_bug(entries):
    """``*_test.py`` and ``*/test_*.py`` are globs, not bare directory names.

    bandit's substring test never matches a literal ``*`` against a real
    path, so these two entries were never part of #14489 — pinned so a future
    edit does not fold them into the anchoring requirement by mistake.
    """
    globs = [entry for entry in entries if is_glob_pattern(entry)]
    assert set(globs) == {"*_test.py", "*/test_*.py"}
    for glob in globs:
        assert glob not in bare_entries(entries)


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_audit_entrypoint_is_clean_on_the_current_config():
    """Exercise the exact call `code-quality` makes, not a paraphrase of it."""
    reached, problems = checker.audit_excludes()
    assert problems == []
    assert reached == len(checker.load_entries()), "the audit did not reach every entry"
    assert reached >= 4, f"only {reached} entries reached — the parse silently collapsed"


def test_audit_entrypoint_fails_on_the_pre_fix_config(tmp_path):
    """The audit must go red on the list this issue was filed against.

    Run against a real config on disk rather than an in-memory list, because
    that is the path CI takes and it is where a cwd- or root-resolution bug
    would hide.
    """
    (tmp_path / ".bandit").write_text(PRE_FIX_EXCLUDE_DIRS, encoding="utf-8")
    subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        # #15246: scrubbed -- an inherited GIT_DIR would init the real repo
        # instead of tmp_path.
        ["git", "init", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    reached, problems = checker.audit_excludes(tmp_path)

    assert reached > 0, "the audit reached no entries — it would pass having checked nothing"
    joined = "\n".join(problems)
    assert "unanchored exclude_dirs entries" in joined, f"the anchoring violation was not reported: {problems}"
    for expected in ("temp", "logs", "reports", "archive", "venv", "tests"):
        assert expected in joined, f"the audit did not name bare `{expected}`"


def test_code_quality_runs_the_audit():
    """A guard nothing invokes is documentation.

    This is the whole reason the checker is a script: the required
    `code-quality` job must call it. The failure direction makes it
    necessary — re-adding a bare name excludes MORE files, so bandit reports
    FEWER findings and the job goes greener. Without this invocation nothing
    that can block a merge would notice.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")

    assert "check_bandit_exclude_anchoring.py --audit-excludes" in workflow, (
        "code-quality.yml no longer runs the bandit exclude-anchoring audit — the guard "
        "would stop blocking merges while these tests kept passing (#14489)"
    )
    assert _CHECKER.is_file(), f"{_CHECKER} is gone but the workflow still calls it"
