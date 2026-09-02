# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14419 — every ``.flake8`` exclude entry must mean the path it was written for.

flake8 normalises an exclude entry that contains a path separator into an
absolute path rooted at the config file's directory, and matches it against the
absolute path of each candidate. An entry with **no** separator is matched
against the candidate's *basename* instead, so a bare name prunes every
directory of that name at any depth.

Written as bare names, the list pruned 973 tracked ``*.py`` files no entry was
written for — including three production packages called ``monitoring``, the
``autobot-backend/tools/`` tool-registry subsystem, and the SDK's
``autobot_sdk/resources/``. Nothing reported them as unlinted; a planted
``SyntaxError`` in ``autobot_shared/monitoring/`` was silently skipped while the
identical error elsewhere was reported as ``E999``.

A neighbouring hazard falls out of the same parsing. configparser strips a
*full-line* ``#`` from inside a multi-line value, so the section markers in
``.flake8`` are safe — but it does not strip a *trailing* one, and flake8 then
splits what is left on commas **and whitespace**, so ``debug/,  # auxiliary``
yields the three patterns ``debug/``, ``#`` and ``auxiliary``. The pre-#14419
config only ever used full-line comments and so did not leak; the check below
covers the case anyway, because a leaked word is indistinguishable from a bare
directory name and both should go red.

The invariant enforced here covers both, because both produce the same artefact
— an entry that is neither an anchored path nor a deliberate artifact name:

* a bare entry is allowed only if it is a listed build/VCS/runtime artifact
  directory, and only while it covers **no tracked Python** (:func:`bare_entries`
  plus :func:`entries_covering_tracked_python`);
* every other entry must be anchored, and must name a directory that exists —
  an entry stranded by a rename exempts nothing while looking authoritative.

The discrimination tests at the bottom run the checker against the config as it
stood before this change. A guard that has never been shown to reject anything
is an assertion about nothing.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]
FLAKE8_CONFIG = REPO_ROOT / ".flake8"
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_flake8_exclude_anchoring.py"


def _load_checker():
    """Import the checker by path.

    The decision lives in the script `code-quality` runs, not here. Restating
    it would give the guard two definitions that could drift, and the copy CI
    executes is the one that matters — a test agreeing with a second copy of
    the rule proves nothing about the check that blocks the merge.
    """
    spec = importlib.util.spec_from_file_location("check_flake8_exclude_anchoring", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()

ARTIFACT_DIR_NAMES = checker.ARTIFACT_DIR_NAMES
read_exclude_entries = checker.read_exclude_entries
split_exclude_value = checker.split_exclude_value
bare_entries = checker.bare_entries
unanchored_source_entries = checker.unanchored_source_entries
entries_covering_tracked_python = checker.entries_covering_tracked_python

#: Floor for the tracked-Python enumeration. An enumeration that returns
#: nothing must not read as "no source is covered by a bare name".
_TRACKED_PY_FLOOR = checker.TRACKED_PY_FLOOR


@pytest.fixture(scope="module")
def entries() -> list[str]:
    return read_exclude_entries(FLAKE8_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tracked_py_files() -> list[str]:
    """Every tracked ``*.py`` path, enumerated by git rather than by flake8."""
    completed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
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
    """A bare name prunes at every depth — anchor it, or justify it as an artifact."""
    offenders = unanchored_source_entries(entries)
    assert offenders == [], (
        f"unanchored .flake8 exclude entries {offenders} — flake8 matches a "
        "separator-free entry against the basename, so each of these prunes "
        "every directory of that name at any depth (#14419). Write the path "
        "the entry was meant for, e.g. `autobot-backend/tests/` not `tests`. "
        "Note that flake8 splits this option on whitespace too, so a `#` line "
        "inside the value leaks each of its words as an entry and shows up here."
    )


def test_artifact_names_cover_no_tracked_python(entries, tracked_py_files):
    """The artifact allowlist stays honest: none of its names may cover source.

    This is what stops the allowlist becoming the new hiding place. Adding
    ``monitoring`` to :data:`ARTIFACT_DIR_NAMES` does not buy silence — it fails
    here instead, and keeps failing the day someone adds a Python file under a
    directory that a listed name happens to match.
    """
    covered = entries_covering_tracked_python(entries, tracked_py_files)
    assert covered == {}, (
        f"bare exclude entries cover tracked Python: {covered}. These files are "
        "silently unlinted. Either the entry is not an artifact directory and "
        "must be anchored, or the source under it does not belong there."
    )


def test_anchored_entries_name_directories_that_exist(entries):
    """An entry stranded by a rename exempts nothing while looking authoritative."""
    anchored = [entry for entry in entries if entry not in bare_entries(entries)]
    assert anchored, "no anchored entries — the exclude list lost its paths"
    missing = [entry for entry in anchored if not (REPO_ROOT / entry.rstrip("/")).is_dir()]
    assert missing == [], (
        f"exclude entries naming no directory: {missing}. Remove them, or fix "
        "the path — a dead entry cannot exclude and cannot warn."
    )


def test_the_three_monitoring_packages_are_linted(entries, tracked_py_files):
    """The regression this issue was filed for, asserted on the outcome.

    ``autobot_shared/monitoring/prometheus_metrics.py`` is production code
    imported across the platform. It was unlinted purely because of its
    directory's name.
    """
    packages = [
        "autobot_shared/monitoring",
        "autobot-backend/monitoring",
        "autobot-slm-backend/monitoring",
    ]
    prefixes = tuple(entry.rstrip("/") + "/" for entry in entries if "/" in entry)
    bare = set(bare_entries(entries))
    for package in packages:
        assert (REPO_ROOT / package).is_dir(), f"{package} moved — update this test"
        assert not package.startswith(prefixes), f"{package} is excluded by an anchored entry"
        assert not set(package.split("/")) & bare, f"{package} is excluded by a bare name"


# --------------------------------------------------------------------------
# Discrimination — the guard must reject the config it was written against
# --------------------------------------------------------------------------

#: The exclude list exactly as it stood before #14419, kept as a fixed
#: reference point. Do NOT "sync" this to the current config: its whole job is
#: to be the thing the guard says no to.
PRE_FIX_EXCLUDE = """
[flake8]
exclude =
    node_modules,
    .venv,
    venv,
    __pycache__,
    .git,
    temp,
    logs,
    reports,
    archive,
    archives,
    backups,
    tests,
    tools,
    scripts,
    monitoring,
    mcp-tools,
    .tox,
    build,
    dist,
    *.egg-info,
    # Auxiliary directories (not production code)
    debug,
    docker,
    code-analysis-suite,
    code_analysis,
    resources,
    analysis,
    # Separate deployable components with own standards
    slm-server,
    slm-admin,
    # Infrastructure contains tests, analysis, tools (not production code)
    infrastructure,
    autobot-infrastructure
"""


def test_guard_rejects_the_pre_fix_config():
    """Against the old list the guard must go red, naming the bare directories."""
    offenders = unanchored_source_entries(read_exclude_entries(PRE_FIX_EXCLUDE))
    for expected in ("monitoring", "tests", "tools", "scripts", "resources", "code_analysis"):
        assert expected in offenders, f"guard failed to flag bare `{expected}`"


def test_full_line_comments_survive_but_trailing_ones_leak():
    """Pin which comment style is safe inside the value, in both directions.

    The distinction is invisible in the file and decides whether a comment is
    documentation or three extra exclude patterns.
    """
    safe = "[flake8]\nexclude =\n    .git,\n    # a full-line note (not production)\n    debug/,\n"
    assert read_exclude_entries(safe) == [".git", "debug/"]

    leaky = "[flake8]\nexclude =\n    .git,\n    debug/,  # trailing note\n"
    leaked = read_exclude_entries(leaky)
    assert leaked == [".git", "debug/", "#", "trailing", "note"]
    for word in ("#", "trailing", "note"):
        assert word in unanchored_source_entries(leaked), f"guard missed leaked word `{word}`"


def test_guard_rejects_a_bare_name_smuggled_into_the_artifact_list(tracked_py_files):
    """Widening ARTIFACT_DIR_NAMES must not be a way to re-hide source."""
    covered = entries_covering_tracked_python(["monitoring", "tests"], tracked_py_files)
    assert covered.get("monitoring", 0) > 0
    assert covered.get("tests", 0) > 0


def test_guard_accepts_the_current_config(entries, tracked_py_files):
    """Both directions on the live config, so a passing suite means something."""
    assert unanchored_source_entries(entries) == []
    assert entries_covering_tracked_python(entries, tracked_py_files) == {}


def test_split_matches_flake8s_own_parser():
    """Pin the mirrored splitter to flake8's, wherever flake8 is importable."""
    flake8_utils = pytest.importorskip("flake8.utils")
    sample = "a,\n b/,\t*.egg-info\n # comment (word)\n c/d/\n"
    assert split_exclude_value(sample) == flake8_utils.parse_comma_separated_list(sample)


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_audit_entrypoint_is_clean_on_the_current_config():
    """Exercise the exact call `code-quality` makes, not a paraphrase of it."""
    reached, problems = checker.audit_excludes()
    assert problems == []
    assert reached == len(checker.load_entries()), "the audit did not reach every entry"
    assert reached >= 30, f"only {reached} entries reached — the parse silently collapsed"


def test_audit_entrypoint_fails_on_the_pre_fix_config(tmp_path):
    """The audit must go red on the list this issue was filed against.

    Run against a real config on disk rather than an in-memory list, because
    that is the path CI takes and it is where a cwd- or root-resolution bug
    would hide.
    """
    (tmp_path / ".flake8").write_text(PRE_FIX_EXCLUDE, encoding="utf-8")
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
    assert "unanchored exclude entries" in joined, f"the anchoring violation was not reported: {problems}"
    for expected in ("monitoring", "tests", "tools", "resources"):
        assert expected in joined, f"the audit did not name bare `{expected}`"


def test_code_quality_runs_the_audit():
    """A guard nothing invokes is documentation.

    This is the whole reason the checker is a script: the required `code-quality`
    job must call it. The failure direction makes it necessary — re-adding a
    bare name lints FEWER files, so every lint step reports fewer violations and
    goes greener. Without this invocation nothing that can block a merge would
    notice (#14353 tracks the wider gap: the pytest suite is not a required
    check).
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")

    assert "check_flake8_exclude_anchoring.py --audit-excludes" in workflow, (
        "code-quality.yml no longer runs the exclude-anchoring audit — the guard "
        "would stop blocking merges while these tests kept passing (#14419)"
    )
    assert _CHECKER.is_file(), f"{_CHECKER} is gone but the workflow still calls it"


def test_the_checker_needs_no_third_party_import():
    """It runs in a job that installs linters, not the application's dependencies.

    An import of anything outside the stdlib would fail at runtime in
    `code-quality`, which is the one place this must not break.
    """
    source = _CHECKER.read_text(encoding="utf-8")
    third_party = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and not line.startswith("from __future__")
        and line.split()[1].split(".")[0]
        # `_scan_helpers` is repo-local and itself stdlib-only (it imports
        # `autobot_shared.paths`, which is stdlib-only by design). It is the
        # SSOT for the git enumeration this checker needs (#14896), so
        # excluding it would mean re-pasting the scrubbed `git ls-files` call
        # here -- the duplication the helper exists to end.
        not in {"argparse", "configparser", "logging", "pathlib", "re", "subprocess", "sys", "_scan_helpers"}
    ]
    assert third_party == [], f"the checker imports non-stdlib modules: {third_party}"
