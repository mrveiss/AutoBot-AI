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

from _scan_helpers import scan_python_files  # noqa: E402
from check_git_toplevel_env_scrubbed import (  # noqa: E402
    ALLOWLIST,
    GIT_CALL_FLOOR,
    main,
    scan,
    scan_with_counts,
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

# `git ls-files` used to live here: it was the example of a git call the guard
# deliberately let through. #14896 gated it -- an inherited GIT_DIR outranks
# `cwd=` and enumerates the wrong index -- so the un-gated example is now a
# subcommand whose answer does not depend on which work tree git picks.
_OTHER_GIT_CALL = """
import subprocess

def head(root):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root).stdout
"""

_UNSCRUBBED_LS_FILES = """
import subprocess

def tracked(root):
    return subprocess.run(["git", "ls-files"], cwd=root).stdout
"""

_SCRUBBED_LS_FILES = """
import subprocess

from autobot_shared.paths import scrubbed_git_env

def tracked(root):
    return subprocess.run(["git", "ls-files"], cwd=root, env=scrubbed_git_env()).stdout
"""

_LS_FILES_VIA_A_LOCAL_SCRUB_WRAPPER = """
import subprocess

from autobot_shared.paths import scrubbed_git_env

def _test_git_env():
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null"}

def tracked(root):
    return subprocess.run(["git", "ls-files"], cwd=root, env=_test_git_env()).stdout
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


def test_other_git_subprocesses_are_reported_in_production_code(tmp_path: Path) -> None:
    """#15783 widened the gate: in production, every git call must say env=."""
    findings = scan(_write(tmp_path, _OTHER_GIT_CALL), tmp_path)
    assert len(findings) == 1
    assert "#15783" in findings[0][1]


def test_other_git_subprocesses_are_left_alone_in_tests(tmp_path: Path) -> None:
    """The contrast: a test reading the real repository on purpose is ordinary.

    Without this half the widened gate would read as "gate everything", which
    is the version that forces an allowlist entry onto every
    ``repo_tests/*_anchoring_test.py`` and gets switched off a month later.
    Test-side *writes* are covered instead by check_git_write_env_scrubbed.
    """
    assert scan(_write(tmp_path, _OTHER_GIT_CALL, name="sample_test.py"), tmp_path) == []
    assert scan(_write(tmp_path, _OTHER_GIT_CALL, name="test_sample.py"), tmp_path) == []


def test_the_wrapper_gap_is_closed_for_the_call_itself(tmp_path: Path) -> None:
    """A ``def git(*args): subprocess.run(["git", *args])`` wrapper is caught.

    It used to be a documented gap outright. The flag half is still invisible —
    the guard cannot attribute ``--show-toplevel`` supplied by a caller — but
    the wrapper's own unscrubbed git call is now a finding, which is the half
    that carries the defect.
    """
    findings = scan(_write(tmp_path, _WRAPPER), tmp_path)
    assert len(findings) == 1
    assert "#15783" in findings[0][1]


_ASYNC_UNSCRUBBED = """
import asyncio

async def status(path):
    proc = await asyncio.create_subprocess_exec("git", "-C", path, "status", "--porcelain")
    return await proc.communicate()
"""

_ASYNC_SCRUBBED = """
import asyncio

from autobot_shared.paths import scrubbed_git_env

async def status(path):
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", path, "status", "--porcelain", env=scrubbed_git_env()
    )
    return await proc.communicate()
"""

_ASYNC_ALIASED = """
import asyncio as aio

async def status(path):
    return await aio.create_subprocess_exec("git", "-C", path, "status")
"""


def test_asyncio_git_call_is_a_finding(tmp_path: Path) -> None:
    """The #15777 shape: the fourth recurrence was an async call site."""
    findings = scan(_write(tmp_path, _ASYNC_UNSCRUBBED), tmp_path)
    assert len(findings) == 1
    assert "#15783" in findings[0][1]


def test_scrubbed_asyncio_git_call_is_accepted(tmp_path: Path) -> None:
    assert scan(_write(tmp_path, _ASYNC_SCRUBBED), tmp_path) == []


def test_asyncio_alias_is_resolved(tmp_path: Path) -> None:
    assert len(scan(_write(tmp_path, _ASYNC_ALIASED), tmp_path)) == 1


def test_discovered_count_rises_with_git_call_sites(tmp_path: Path) -> None:
    """The vacuity floor counts what was inspected, not what was wrong."""
    _, none_found = scan_with_counts(_write(tmp_path, _PROSE_ONLY), tmp_path)
    _, one_found = scan_with_counts(_write(tmp_path, _OTHER_GIT_CALL, name="a.py"), tmp_path)
    _, scrubbed_still_counts = scan_with_counts(_write(tmp_path, _SCRUBBED, name="b.py"), tmp_path)

    assert none_found == 0
    assert one_found == 1
    assert scrubbed_still_counts == 1, "a compliant call site is still a call site inspected"


def test_the_repository_is_above_the_discovered_floor() -> None:
    """A sweep that parses nothing reports clean; this is what catches that."""
    repo_root = Path(__file__).resolve().parents[2]
    py_files, _ = scan_python_files([], repo_root)
    discovered = sum(scan_with_counts(path, repo_root)[1] for path in py_files)

    assert discovered >= GIT_CALL_FLOOR, f"only {discovered} git call sites reached"


def test_unscrubbed_ls_files_is_a_finding(tmp_path: Path) -> None:
    """#14896: `cwd=` loses to an inherited GIT_DIR, so a correct cwd still
    enumerates the other checkout's index -- and answers without erroring."""
    findings = scan(_write(tmp_path, _UNSCRUBBED_LS_FILES), tmp_path)
    assert len(findings) == 1
    assert "ls-files" in findings[0][1]


def test_scrubbed_ls_files_is_not_a_finding(tmp_path: Path) -> None:
    """The green direction, so the test above cannot be met by flagging every
    ls-files call and telling correct code to fix itself."""
    assert scan(_write(tmp_path, _SCRUBBED_LS_FILES), tmp_path) == []


def test_ls_files_through_a_local_scrub_wrapper_is_not_a_finding(tmp_path: Path) -> None:
    """A suite that needs the scrub plus a pinned GIT_CONFIG_GLOBAL wraps the
    helper. Rejecting the wrapper would push those callers back onto an inline
    repeat of the scrub, which is the duplication this guard exists to stop."""
    assert scan(_write(tmp_path, _LS_FILES_VIA_A_LOCAL_SCRUB_WRAPPER), tmp_path) == []


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


_ARGS_KEYWORD = """
import subprocess

def status(path):
    return subprocess.run(args=["git", "-C", path, "status"]).stdout
"""

_ARGS_KEYWORD_TOPLEVEL = """
import subprocess

def root():
    return subprocess.run(args=["git", "rev-parse", "--show-toplevel"]).stdout
"""

_ABSOLUTE_GIT = """
import subprocess

def status(path):
    return subprocess.run(["/usr/bin/git", "-C", path, "status"]).stdout
"""


def test_args_keyword_is_inspected(tmp_path: Path) -> None:
    """`subprocess.run(args=[...])` is an ordinary spelling, not an evasion."""
    findings = scan(_write(tmp_path, _ARGS_KEYWORD), tmp_path)

    assert len(findings) == 1
    assert "#15783" in findings[0][1]


def test_args_keyword_reaches_the_token_gate_too(tmp_path: Path) -> None:
    """A --show-toplevel behind args= gets the toplevel message, not the generic one."""
    findings = scan(_write(tmp_path, _ARGS_KEYWORD_TOPLEVEL, name="sample_test.py"), tmp_path)

    assert len(findings) == 1
    assert "#15176" in findings[0][1]


def test_an_absolute_git_path_is_not_skipped_by_the_pre_gate(tmp_path: Path) -> None:
    """The cheap gate must admit every spelling `_names_git` accepts."""
    findings = scan(_write(tmp_path, _ABSOLUTE_GIT), tmp_path)

    assert len(findings) == 1


def test_the_args_keyword_and_absolute_paths_count_toward_discovery(tmp_path: Path) -> None:
    """A call the matcher cannot see is also missing from the vacuity floor."""
    _, args_form = scan_with_counts(_write(tmp_path, _ARGS_KEYWORD, name="a.py"), tmp_path)
    _, absolute_form = scan_with_counts(_write(tmp_path, _ABSOLUTE_GIT, name="b.py"), tmp_path)

    assert args_form == 1
    assert absolute_form == 1
