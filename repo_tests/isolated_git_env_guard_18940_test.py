# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A test that builds a throwaway git repo must use `autobot_shared.isolated_git` (#18940).

Fixtures that run `git init`/`git commit` under the developer's global and system git config
pass or fail depending on whose machine they run on (ignore rules, `init.defaultBranch`, signing,
hooks, templates). `isolated_git_env()` is the one place that neutralises all of it; this guard
stops a new test file from hand-rolling the setup again.

The existing offenders are frozen in `isolated_git_env_baseline_18940.py`, which may only shrink.
The detector lives in `_isolated_git_detect.py`; its KNOWN GAP is stated there.
A helper-importing file's raw `git` calls are the call-level gate's job; the tests below pin that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from repo_tests._isolated_git_detect import is_skipped, is_test_file, offends
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.isolated_git_env_baseline_18940 import ALLOWLIST, FROZEN_TOTAL

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: An operational CLI that merely matches the `test_*.py` collection glob; it creates real worktrees
#: on purpose (the same entry is recorded in `check_git_write_env_scrubbed.ALLOWLIST`, #15246).
_NOT_A_TEST = frozenset({"scripts/test_first_remediation.py"})


def _test_files(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if is_test_file(rel) and not is_skipped(rel) and rel not in _NOT_A_TEST]


def _all_python(root: Path) -> int:
    try:
        return len(tracked_paths(root, "*.py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-10-20: 3279 test files of 7153 tracked `.py` (0.46); 0.40 leaves room for the suite
#: to grow slower than the source without the sweep reading as narrower.
REACH = declare(
    "isolated-git-env",
    discover=_test_files,
    reference=_all_python,
    min_fraction=0.40,
    what="test python files",
)


def _offenders(root: Path) -> set[str]:
    found, read = set(), 0
    for rel in REACH.examined(root):
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        read += 1
        if offends(source):
            found.add(rel)
    # Recorded before the caller asserts anything about ``found``: the reach is a property of the
    # sweep, so it is declared complete whether or not offenders turned up.
    REACH.completed(read, root)
    return found


def test_no_new_test_builds_a_git_repo_without_the_isolated_env() -> None:
    new = sorted(_offenders(repo_root()) - ALLOWLIST.keys())
    assert not new, (
        "These test files run `git init`/`git commit` without `autobot_shared.isolated_git`:\n  "
        + "\n  ".join(new)
        + "\nUse `make_repo(tmp_path)` / `git(repo, ...)` / `isolated_git_env()`; do NOT add them to the baseline."
    )


def test_baseline_only_shrinks() -> None:
    root = repo_root()
    stale = sorted(ALLOWLIST.keys() - _offenders(root))
    assert not stale, "Migrated (or removed) files still in the baseline; delete these lines:\n  " + "\n  ".join(stale)
    assert len(ALLOWLIST) == FROZEN_TOTAL, f"baseline has {len(ALLOWLIST)} rows but FROZEN_TOTAL is {FROZEN_TOTAL}"
    assert all(reason.strip() for reason in ALLOWLIST.values())


_RAW_ARGV = "import subprocess\nsubprocess.run(['git', 'init', '-q'])\n"
_RAW_HELPER = "import subprocess\ndef _git(r, *a):\n    subprocess.run(['git', *a])\n_git(r, 'commit', '-m', 'x')\n"
_RAW_SHELL = "import subprocess\nsubprocess.run(['bash', '-c', 'git init && git commit -m x'])\n"
_USES_HELPER = "import subprocess\nfrom autobot_shared.isolated_git import make_repo\nsubprocess.run(['git', 'init'])\n"
_READ_ONLY = "import subprocess\nsubprocess.run(['git', 'status'])\n"
_NOT_GIT = "import subprocess\nsubprocess.run(['terraform', 'init'])\n"
_DOCSTRING_ONLY = 'import subprocess\n"""Runs `git init`."""\nsubprocess.run(["ls"])\n'
_SESSION_COMMIT = "def test_x(session):\n    session.execute('git')\n    session.add('commit')\n"
_SUBPROCESS_PLUS_SESSION = (
    "import subprocess\nsubprocess.run(['git', 'status'])\ndef test_x(session):\n    session.add('commit')\n"
)
_ARGV_C_COMMIT = "import subprocess\nsubprocess.run(['git', '-C', '.', 'commit', '-m', 'x'])\n"


def test_detector_flags_each_raw_shape() -> None:
    for source in (_RAW_ARGV, _RAW_HELPER, _RAW_SHELL, _ARGV_C_COMMIT):
        assert offends(source), source


def test_detector_leaves_alone_what_is_not_a_hand_rolled_repo() -> None:
    for source in (
        _USES_HELPER,
        _READ_ONLY,
        _NOT_GIT,
        _DOCSTRING_ONLY,
        _SESSION_COMMIT,
        _SUBPROCESS_PLUS_SESSION,
        "def (:\n",
    ):
        assert not offends(source), source


def test_skip_dirs_match_repo_relative_parts_not_the_absolute_path() -> None:
    assert is_skipped("node_modules/x/a_test.py")
    assert not is_skipped("tools/node_modules_link_test.py")
    assert not is_skipped("a_test.py")


def test_helper_is_the_only_accepted_import() -> None:
    assert offends(
        "import subprocess\nfrom autobot_shared.paths import scrubbed_git_env\nsubprocess.run(['git','init'])"
    )


_IMPORT_PLAIN = "import subprocess\nimport autobot_shared.isolated_git\nsubprocess.run(['git', 'init'])\n"
_IMPORT_ALIAS = "import subprocess\nimport autobot_shared.isolated_git as ig\nsubprocess.run(['git', 'init'])\n"
_IMPORT_PARENT = "import subprocess\nfrom autobot_shared import isolated_git\nsubprocess.run(['git', 'init'])\n"
_IMPORT_LOOKALIKE = "import subprocess\nimport autobot_shared.isolated_git_other\nsubprocess.run(['git', 'init'])\n"
_HELPER_SHELL_RAW = "import subprocess\nfrom autobot_shared.isolated_git import make_repo\nsubprocess.run(['bash', '-c', 'git commit -m x'])\n"
_HELPER_SHELL_ENV = _HELPER_SHELL_RAW + "from autobot_shared.isolated_git import isolated_git_env\nisolated_git_env()\n"


def test_every_import_form_of_the_helper_is_accepted() -> None:
    for source in (_IMPORT_PLAIN, _IMPORT_ALIAS, _IMPORT_PARENT):
        assert not offends(source), source
    assert offends(_IMPORT_LOOKALIKE)


def test_a_shell_string_write_in_a_helper_importing_file_needs_the_env_helper() -> None:
    assert offends(_HELPER_SHELL_RAW)
    assert not offends(_HELPER_SHELL_ENV)


def _load_gate() -> ModuleType:
    """Load the call-level gate by file path: no ``sys.path`` edit, no bare-name ``sys.modules`` entry."""
    gate_path = repo_root() / "tools" / "lint" / "check_git_write_env_scrubbed.py"
    spec = importlib.util.spec_from_file_location("_gate_check_git_write_env_scrubbed_18940", gate_path)
    assert spec is not None and spec.loader is not None, gate_path
    module = importlib.util.module_from_spec(spec)
    before = list(sys.path)  # the gate inserts its own directory at import; restore exactly what was there
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = before
    return module


def _gate_findings(tmp_path: Path, source: str) -> list:
    gate = _load_gate()
    path = tmp_path / "fixture_test.py"
    path.write_text(source, encoding="utf-8")
    return gate.scan(path, tmp_path)


def test_the_call_level_gate_catches_a_raw_write_in_a_helper_importing_file(tmp_path: Path) -> None:
    """Importing the helper does not excuse a raw `git commit`: `check_git_write_env_scrubbed` flags it."""
    head = "import subprocess\nfrom autobot_shared.isolated_git import isolated_git_env\n"
    assert _gate_findings(tmp_path, head + "subprocess.run(['git', 'commit', '-m', 'x'])\n")
    assert _gate_findings(tmp_path, head + "def _g(r, *a):\n    subprocess.run(['git', '-C', str(r), *a])\n")
    assert not _gate_findings(tmp_path, head + "subprocess.run(['git', 'commit'], env=isolated_git_env())\n")
