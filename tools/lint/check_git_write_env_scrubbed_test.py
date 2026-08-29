# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the #15246 git-write environment-scrub guard.

Mirrors ``tools/lint/check_git_toplevel_env_scrubbed_test.py``'s structure: one
half pins the guard's own judgement (what it flags, what it accepts, what it
deliberately ignores) with synthetic source fixtures written to ``tmp_path``,
never with a real ``git`` subprocess. Nothing here shells out to git.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_git_write_env_scrubbed import (  # noqa: E402
    ALLOWLIST,
    TEST_FILE_FLOOR,
    _is_git_write,
    main,
    scan,
    scan_repo,
    trusted_names,
)

# --------------------------------------------------------------------------
# The #15246 contrast mutation: one real shape (the `_git` helper this issue
# fixed in pipeline-scripts/check_baseline_no_growth_test.py and a dozen
# siblings), scrubbed and not, differing by exactly the `env=` keyword.
# --------------------------------------------------------------------------

_HELPER_SCRUBBED = """
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=scrubbed_git_env()
    )


def _init_repo(repo):
    _git(repo, "init", "--quiet")
    _git(repo, "add", "-A")
"""

_HELPER_UNSCRUBBED = """
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _init_repo(repo):
    _git(repo, "init", "--quiet")
    _git(repo, "add", "-A")
"""

_LOCAL_WRAPPER_SCRUBBED = """
import subprocess

from autobot_shared.paths import scrubbed_git_env


def _test_git_env():
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null"}


def _make_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=_test_git_env())
"""

_MODULE_CONSTANT_SCRUBBED = """
import subprocess

from autobot_shared.paths import scrubbed_git_env

_ENV = scrubbed_git_env()


def _make_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=_ENV)
"""

_READ_VERB_UNSCRUBBED = """
import subprocess


def tracked(root):
    return subprocess.run(["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True)
"""

_DASH_C_COMMIT_UNSCRUBBED = """
import subprocess


def _commit(repo):
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"], cwd=repo, check=True
    )
"""

_SHELL_STRING_GAP = """
import subprocess

RANGE_LOGIC = "git rev-list --count HEAD"


def run(repo):
    return subprocess.run(["bash", "-c", RANGE_LOGIC], cwd=repo, capture_output=True, text=True)
"""

_HERMETIC_ALIAS_SCRUBBED = """
import subprocess

from code_intelligence.co_change_test import hermetic_git_env


def _init(repo):
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=hermetic_git_env())
"""


_DYNAMIC_PATH_AFTER_A_READ_VERB = """
import subprocess


def tracked(root):
    return subprocess.run(["git", "-C", str(root), "ls-files", "*.py"], capture_output=True, text=True)
"""

_NO_SPREAD_DICT_ACCEPTED = """
import subprocess


def _commit(repo, name, email):
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "x"],
        check=True,
        env={"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email},
    )
"""

_TWO_LEVEL_INDIRECTION_SCRUBBED = """
import subprocess

from autobot_shared.paths import scrubbed_git_env


def _test_git_env():
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null"}


def _run(tmp_path):
    env = _test_git_env()
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env=env)
"""


def _write(tmp_path: Path, source: str, name: str = "sample_test.py") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_the_unscrubbed_helper_is_reported(tmp_path: Path) -> None:
    """The mutation: reads reintroduce the exact incident this issue fixed.

    One finding, not two: `_git(repo, "init", ...)` and `_git(repo, "add", ...)`
    are calls to the local `_git` name, not to `subprocess`/an imported
    subprocess entry point, so only the `subprocess.run` inside `_git`'s own
    body is a node this scanner classifies as a subprocess call at all.
    """
    findings = scan(_write(tmp_path, _HELPER_UNSCRUBBED), tmp_path)
    assert len(findings) == 1, findings
    assert all("#15246" in message for _, message in findings)


def test_the_scrubbed_helper_is_accepted(tmp_path: Path) -> None:
    """The fix: identical shape, `env=scrubbed_git_env()` added."""
    assert scan(_write(tmp_path, _HELPER_SCRUBBED), tmp_path) == []


def test_a_local_wrapper_that_calls_the_helper_is_accepted(tmp_path: Path) -> None:
    """`_test_git_env()` — the pattern this issue's PR used across ~17 files."""
    assert scan(_write(tmp_path, _LOCAL_WRAPPER_SCRUBBED), tmp_path) == []


def test_a_module_constant_built_from_the_helper_is_accepted(tmp_path: Path) -> None:
    """`_ENV = scrubbed_git_env()`, referenced by name at the call site."""
    assert scan(_write(tmp_path, _MODULE_CONSTANT_SCRUBBED), tmp_path) == []


def test_an_imported_hermetic_git_env_alias_is_accepted(tmp_path: Path) -> None:
    """`hermetic_git_env` is the second canonical helper this codebase has."""
    assert scan(_write(tmp_path, _HERMETIC_ALIAS_SCRUBBED), tmp_path) == []


def test_an_unscrubbed_read_verb_is_left_alone(tmp_path: Path) -> None:
    """`git ls-files` is not in WRITE_VERBS -- reads against a real root are
    common and correct elsewhere in this suite (see the module docstring)."""
    assert scan(_write(tmp_path, _READ_VERB_UNSCRUBBED), tmp_path) == []


def test_a_dynamic_path_after_a_resolved_read_verb_is_left_alone(tmp_path: Path) -> None:
    """`git -C str(root) ls-files "*.py"` -- #15246 review found this shape
    misclassified as a write by an earlier version of `_is_git_write`, which
    treated ANY dynamic argv element as making the verb unknowable rather
    than only a dynamic element AT the verb's own position."""
    assert scan(_write(tmp_path, _DYNAMIC_PATH_AFTER_A_READ_VERB), tmp_path) == []


def test_a_hand_built_dict_with_no_environ_spread_is_accepted(tmp_path: Path) -> None:
    """`env={"PATH": ..., "GIT_AUTHOR_NAME": ...}` -- scripts/lint_conventions_test.py's
    `_bot_commit` shape. No `**os.environ`/`**scrubbed_git_env()` anywhere in
    it, so it cannot carry an ambient GIT_DIR regardless of what built it."""
    assert scan(_write(tmp_path, _NO_SPREAD_DICT_ACCEPTED), tmp_path) == []


def test_a_local_variable_holding_a_trusted_wrapper_call_is_accepted(tmp_path: Path) -> None:
    """`env = _test_git_env()` followed by `env=env` at each call site --
    pre-commit-hardcoded-values_test.py's actual shape. Needs trusted_names'
    second pass: the Assign's value is a call to an ALREADY-trusted function,
    not a call that itself mentions scrubbed_git_env textually."""
    assert scan(_write(tmp_path, _TWO_LEVEL_INDIRECTION_SCRUBBED), tmp_path) == []


def test_a_dash_c_config_flag_does_not_hide_the_verb_behind_it(tmp_path: Path) -> None:
    """`git -c commit.gpgsign=false commit ...` -- the verb is the 4th element,
    not the 2nd; the flag-skipping walk must still find it."""
    findings = scan(_write(tmp_path, _DASH_C_COMMIT_UNSCRUBBED), tmp_path)
    assert len(findings) == 1


def test_a_git_write_inside_a_shell_string_is_a_documented_gap(tmp_path: Path) -> None:
    """Pinned rather than silently passing: the verb is in a string literal,
    not an argv element, and closing this needs the shell parsed too."""
    assert scan(_write(tmp_path, _SHELL_STRING_GAP), tmp_path) == []


def test_a_non_test_file_is_out_of_scope_even_with_a_bare_write(tmp_path: Path) -> None:
    """This guard is scoped to test files; production git use is a different
    review (see the module docstring's SCOPE section)."""
    assert scan(_write(tmp_path, _HELPER_UNSCRUBBED, name="sample.py"), tmp_path) == []


def test_allowlisted_files_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The mechanism, proven with a synthetic entry independent of whatever
    is in the real ALLOWLIST today (see test_every_allowlist_entry_still_exists
    for that)."""
    entry = "repo_tests/synthetic_allowlist_entry_test.py"
    monkeypatch.setattr("check_git_write_env_scrubbed.ALLOWLIST", frozenset({entry}))
    path = tmp_path / entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HELPER_UNSCRUBBED, encoding="utf-8")
    assert scan(path, tmp_path) == []


def test_every_allowlist_entry_still_exists() -> None:
    """A stranded exemption exempts nothing and says nothing while it does it."""
    repo_root = Path(__file__).resolve().parents[2]
    missing = [entry for entry in ALLOWLIST if not (repo_root / entry).is_file()]
    assert not missing, f"allowlist entries no longer in the tree: {missing}"


def test_the_operational_remediation_tool_is_the_documented_allowlist_entry() -> None:
    """`scripts/test_first_remediation.py` is real code, not a fixture: a real
    worktree, a real push. It is allowlisted for exactly that reason -- pinned
    here so the entry cannot silently start covering something else."""
    assert ALLOWLIST == frozenset({"scripts/test_first_remediation.py"})


def test_main_exits_nonzero_on_a_violation(tmp_path: Path) -> None:
    assert main([str(_write(tmp_path, _HELPER_UNSCRUBBED))]) == 1


def test_main_exits_zero_on_the_scrubbed_form(tmp_path: Path) -> None:
    assert main([str(_write(tmp_path, _HELPER_SCRUBBED))]) == 0


def test_the_whole_repository_is_clean() -> None:
    """The guard's own subject: no unscrubbed git write is left in the tree."""
    assert main([]) == 0


def test_the_reach_floor_is_met_by_the_real_tree() -> None:
    """#15246's own lesson: a walk that finds nothing must first prove it
    looked. `scan_repo` reaching fewer than TEST_FILE_FLOOR test files is the
    same "checked nothing, reported clean" shape as the bug this backlog
    keeps finding, so it is asserted here rather than only inside `main`."""
    repo_root = Path(__file__).resolve().parents[2]
    reached, _ = scan_repo(repo_root)
    assert reached >= TEST_FILE_FLOOR, f"only reached {reached} test files, floor is {TEST_FILE_FLOOR}"


def test_scan_repo_reaches_nothing_under_an_empty_tree(tmp_path: Path) -> None:
    """The floor check's precondition: an empty tree reaches zero files."""
    reached, findings = scan_repo(tmp_path)
    assert reached == 0
    assert findings == []


def test_a_walk_below_the_floor_fails_main_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """#15246's own lesson, applied to this guard: a walk that reaches too
    few files must not report success just because it found no findings."""
    import check_git_write_env_scrubbed as guard

    monkeypatch.setattr(guard, "scan_repo", lambda repo_root: (0, []))
    assert guard.main([]) == 1


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["git", "-C", "/r", "init", "-q"], True),
        (["git", "ls-files", "*.py"], False),
        (["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"], True),
        (["bash", "-c", "git commit"], False),
    ],
)
def test_is_git_write_classifies_literal_argv(argv: list[str], expected: bool) -> None:
    tree = ast.parse(f"subprocess.run({argv!r})")
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert _is_git_write(call) is expected


def test_is_git_write_treats_a_dynamic_verb_as_a_write() -> None:
    """`["git", *args]` -- the dominant helper shape this sweep found -- must
    be reported unless scrubbed: the caller decides the verb, not this call."""
    tree = ast.parse('subprocess.run(["git", *args])')
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert _is_git_write(call) is True


def test_trusted_names_resolves_both_a_function_and_a_variable() -> None:
    tree = ast.parse(_LOCAL_WRAPPER_SCRUBBED)
    assert "_test_git_env" in trusted_names(tree)
    tree2 = ast.parse(_MODULE_CONSTANT_SCRUBBED)
    assert "_ENV" in trusted_names(tree2)
