# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the #15176 ``--show-toplevel`` environment-scrub guard.

The behavioural half — that each of the six real sites still resolves the
repository root under an ambient ``GIT_DIR`` — lives in
``repo_tests/git_repo_root_scrub_test.py``. This half pins the guard's own
judgement: what it flags, what it accepts, and what it deliberately ignores.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_git_toplevel_env_scrubbed import (  # noqa: E402
    ALLOWLIST,
    main,
    scan,
    subprocess_names,
)

_UNSCRUBBED = """
import subprocess

def root():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return out.stdout.strip()
"""

_SCRUBBED = """
import subprocess

from autobot_shared.paths import scrubbed_git_env

def root():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        env=scrubbed_git_env(),
    )
    return out.stdout.strip()
"""

_ENV_BUT_NOT_SCRUBBED = """
import os
import subprocess

def root():
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], env=os.environ.copy())
    return out.stdout.strip()
"""

_PROSE_ONLY = '''
"""This module explains why ``git rev-parse --show-toplevel`` is dangerous."""

TOPLEVEL_NOTE = "--show-toplevel answers with the CWD under an ambient GIT_DIR"
'''

_OTHER_GIT_CALL = """
import subprocess

def tracked(root):
    return subprocess.run(["git", "ls-files"], cwd=root).stdout
"""


_ALIASED_MODULE = """
import subprocess as sp

def root():
    return sp.run(["git", "rev-parse", "--show-toplevel"]).stdout
"""

_ALIASED_MODULE_SCRUBBED = """
import subprocess as sp

from autobot_shared.paths import scrubbed_git_env

def root():
    return sp.run(["git", "rev-parse", "--show-toplevel"], env=scrubbed_git_env()).stdout
"""

_FROM_IMPORT = """
from subprocess import run

def root():
    return run(["git", "rev-parse", "--show-toplevel"]).stdout
"""

_FROM_IMPORT_ALIASED = """
from subprocess import check_output as _co

def root():
    return _co(["git", "rev-parse", "--show-toplevel"])
"""

_FROM_IMPORT_SCRUBBED = """
from subprocess import run

from autobot_shared.paths import scrubbed_git_env

def root():
    return run(["git", "rev-parse", "--show-toplevel"], env=scrubbed_git_env()).stdout
"""

_FUNCTION_LOCAL_IMPORT = """
def root():
    import subprocess as sp

    return sp.run(["git", "rev-parse", "--show-toplevel"]).stdout
"""

# --- documented gaps (see the guard's KNOWN GAPS section) --------------------

_VARIABLE_ARGV = """
import subprocess

CMD = ["git", "rev-parse", "--show-toplevel"]

def root():
    return subprocess.run(CMD).stdout
"""

_WRAPPER = """
import subprocess

def git(*args):
    return subprocess.run(["git", *args]).stdout

def root():
    return git("rev-parse", "--show-toplevel")
"""

_SHADOWED_SCRUB_HELPER = """
import os
import subprocess

def scrubbed_git_env():
    return dict(os.environ)

def root():
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], env=scrubbed_git_env()).stdout
"""


def _write(tmp_path: Path, source: str, name: str = "sample.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_unscrubbed_call_is_reported(tmp_path: Path) -> None:
    findings = scan(_write(tmp_path, _UNSCRUBBED), tmp_path)
    assert len(findings) == 1
    assert "#15176" in findings[0][1]


def test_scrubbed_call_is_accepted(tmp_path: Path) -> None:
    assert scan(_write(tmp_path, _SCRUBBED), tmp_path) == []


def test_an_env_that_is_not_the_helper_is_still_reported(tmp_path: Path) -> None:
    """``env=os.environ.copy()`` carries GIT_DIR straight back in."""
    assert len(scan(_write(tmp_path, _ENV_BUT_NOT_SCRUBBED), tmp_path)) == 1


def test_prose_mentioning_the_flag_is_not_a_finding(tmp_path: Path) -> None:
    """Only calls are inspected, so documentation needs no allowlist entry."""
    assert scan(_write(tmp_path, _PROSE_ONLY), tmp_path) == []


def test_other_git_subprocesses_are_left_alone(tmp_path: Path) -> None:
    assert scan(_write(tmp_path, _OTHER_GIT_CALL), tmp_path) == []


def test_allowlisted_files_are_skipped(tmp_path: Path) -> None:
    """The allowlist is keyed on the repo-relative POSIX path."""
    entry = sorted(ALLOWLIST)[0]
    path = tmp_path / entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_UNSCRUBBED, encoding="utf-8")
    assert scan(path, tmp_path) == []


def test_every_allowlist_entry_still_exists() -> None:
    """A stranded exemption exempts nothing and says nothing while it does it."""
    repo_root = Path(__file__).resolve().parents[2]
    missing = [entry for entry in ALLOWLIST if not (repo_root / entry).is_file()]
    assert not missing, f"allowlist entries no longer in the tree: {missing}"


def test_main_exits_nonzero_on_a_violation(tmp_path: Path) -> None:
    assert main([str(_write(tmp_path, _UNSCRUBBED))]) == 1


def test_main_exits_zero_on_the_scrubbed_form(tmp_path: Path) -> None:
    assert main([str(_write(tmp_path, _SCRUBBED))]) == 0


def test_the_whole_repository_is_clean() -> None:
    """The guard's own subject: no seventh unscrubbed call is in the tree."""
    assert main([]) == 0


@pytest.mark.parametrize("source", [_UNSCRUBBED, _SCRUBBED])
def test_unparseable_neighbours_do_not_crash_the_scan(tmp_path: Path, source: str) -> None:
    broken = _write(tmp_path, "def (:\n", "broken.py")
    assert scan(broken, tmp_path) == []
    _write(tmp_path, source)


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("import subprocess as sp", _ALIASED_MODULE),
        ("from subprocess import run", _FROM_IMPORT),
        ("from subprocess import check_output as _co", _FROM_IMPORT_ALIASED),
        ("function-local aliased import", _FUNCTION_LOCAL_IMPORT),
    ],
)
def test_the_import_binding_is_resolved_not_matched_literally(tmp_path: Path, label: str, source: str) -> None:
    """Review finding: matching the literal ``subprocess`` missed these spellings."""
    assert len(scan(_write(tmp_path, source), tmp_path)) == 1, label


@pytest.mark.parametrize("source", [_ALIASED_MODULE_SCRUBBED, _FROM_IMPORT_SCRUBBED])
def test_the_scrubbed_form_is_accepted_under_every_import_spelling(tmp_path: Path, source: str) -> None:
    assert scan(_write(tmp_path, source), tmp_path) == []


def test_subprocess_names_reads_the_bindings() -> None:
    modules, functions = subprocess_names(ast.parse(_ALIASED_MODULE))
    assert modules == {"subprocess", "sp"} and functions == set()
    modules, functions = subprocess_names(ast.parse(_FROM_IMPORT_ALIASED))
    assert functions == {"_co"}


def test_the_bare_name_stays_covered_when_nothing_imports_it() -> None:
    """Seeding ``"subprocess"`` can only add a finding, never suppress one."""
    modules, _ = subprocess_names(ast.parse("x = 1\n"))
    assert "subprocess" in modules


@pytest.mark.parametrize(
    ("gap", "source"),
    [
        ("argv built through a variable", _VARIABLE_ARGV),
        ("flag supplied to a wrapper by its caller", _WRAPPER),
        ("a locally shadowed scrubbed_git_env", _SHADOWED_SCRUB_HELPER),
    ],
)
def test_documented_gaps_stay_documented(tmp_path: Path, gap: str, source: str) -> None:
    """These three are NOT reported, and the guard's docstring says so.

    Pinned rather than left implicit: closing them needs dataflow analysis,
    which is out of proportion here. If a future change starts catching one,
    this test fails and the KNOWN GAPS section has to be corrected with it —
    which is the point. The behavioural suite
    (``repo_tests/git_repo_root_scrub_test.py``) is what actually covers the
    real sites, whatever shape their calls take.
    """
    assert scan(_write(tmp_path, source), tmp_path) == [], gap


def test_the_docstring_lists_every_pinned_gap() -> None:
    """An unstated gap is the defect class this whole backlog exists to fix."""
    import check_git_toplevel_env_scrubbed as guard

    doc = guard.__doc__ or ""
    assert "KNOWN GAPS" in doc
    for phrase in ("through a variable", "Wrappers", "shadowed scrub helper"):
        assert phrase in doc, phrase
