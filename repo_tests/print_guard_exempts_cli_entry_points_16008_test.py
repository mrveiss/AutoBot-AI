# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A CLI entry point may print; a library module may not, and the list is readable (#16008).

The rule used to be a path prefix, and its exempt population was written down
nowhere. `scripts/` was not on the list, yet 15 of its files carried 107 `print(`
calls and passed CI anyway -- the CI wrapper runs `--changed-lines-only`, so an
untouched line is never examined. That is an exemption with no allowlist, no
baseline and no comment, existing only as the intersection of the scan's scope
and nobody having edited those lines. It could not go stale, be audited, or be
argued with, and it made a NEW CLI script a violation while fifteen identical
old ones sat in the tree.

These tests EXECUTE the hook. A test that greps the hook's source for
`is_cli_entry_point` would have passed while the exemption list was being built
in a subshell and silently discarded -- which is what happened, twice, before
this file existed.
"""

from __future__ import annotations

import contextlib
import pathlib
import subprocess

from repo_tests._paths import repo_root
from tools.lint._scan_helpers import tracked_paths

_HOOK = (
    repo_root()
    / "autobot-infrastructure"
    / "shared"
    / "scripts"
    / "hooks"
    / "pre-commit-no-print-console"
)

_LIBRARY = '"""No entry point."""\n\n\ndef emit(msg):\n    print(msg)\n'
_CLI = '"""An entry point."""\n\n\ndef main():\n    print("verdict")\n\n\nif __name__ == "__main__":\n    main()\n'


def _run_hook(relative_path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["bash", str(_HOOK), relative_path],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=repo_root(),
        check=False,
    )


@contextlib.contextmanager
def _with_probe(name: str, body: str):
    """Write a probe under scripts/ and remove it again.

    It has to live at a real `scripts/` path: the rule is about where a file is
    AND what it is, so a probe in a temp directory would test neither half.
    """
    path = repo_root() / "scripts" / name
    path.write_text(body, encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_a_library_module_under_scripts_still_cannot_print():
    """The control. An exemption that swallows everything passes every other test here."""
    with _with_probe("_probe_16008_library.py", _LIBRARY):
        result = _run_hook("scripts/_probe_16008_library.py")
        assert "VIOLATION" in result.stdout, (
            "the guard did not flag a print() in a library module under scripts/ -- "
            f"the exemption is too wide and nothing below means anything:\n{result.stdout}"
        )


def test_a_cli_entry_point_under_scripts_may_print():
    """stdout IS a CLI tool's interface; a logger would make the tool unusable."""
    with _with_probe("_probe_16008_cli.py", _CLI):
        result = _run_hook("scripts/_probe_16008_cli.py")
        assert "VIOLATION" not in result.stdout, (
            f"a standalone CLI entry point was flagged for printing:\n{result.stdout}"
        )


def test_the_exemption_names_the_files_it_declined_to_scan():
    """An exemption a reader never meets is the defect this replaced, not the fix.

    This is the assertion that fails on a subshell: the list is built inside
    `get_staged_python_files`, whose output main() captures with command
    substitution, so a plain variable is set in the child and lost. The hook
    exempted the file correctly and reported nothing at all -- indistinguishable,
    from outside, from the old invisible rule.
    """
    with _with_probe("_probe_16008_cli.py", _CLI):
        result = _run_hook("scripts/_probe_16008_cli.py")
        assert "Not scanned" in result.stdout, f"the exemption was silent:\n{result.stdout}"
        assert "_probe_16008_cli.py" in result.stdout, (
            "the exemption did not name the file it applied to, so a reviewer "
            f"cannot disagree with it:\n{result.stdout}"
        )


def _tracked_scripts() -> list[pathlib.Path]:
    """Non-test scripts, enumerated through the one helper (#15926).

    A raw `git ls-files` here would be the 42nd direct invocation the census in
    `one_git_enumeration_15926_test.py` is ratcheting down, and it would inherit
    any `GIT_DIR` the environment carries -- enumerating another checkout's
    index while `repo_root()` names this one, which exits 0 with plausible
    output (#15176). `tracked_paths` scrubs that and lets git do the excluding.
    """
    # The excludes carry their `scripts/` prefix DELIBERATELY. A git pathspec is
    # rooted, not matched against a basename, and a bare `*_test.py` here excludes
    # the entire enumeration -- measured, git 2.34.1: 48 files -> 0. The docstring
    # invites bare glob fragments and its own example (`*.min.js`) is in that
    # broken class; #16013 has the table.
    listing = tracked_paths(
        repo_root(),
        "scripts/*.py",
        "scripts/**/*.py",
        exclude=("scripts/*_test.py", "scripts/**/*_test.py"),
    )
    return [repo_root() / name for name in listing]


def test_every_printing_script_is_an_entry_point_and_no_library_module_prints():
    """The property must separate the population, or it is a widening dressed as a rule.

    Compared as SETS, not counts: two rules can agree on how many files they
    exempt and disagree on which. The second half is the one that would fail if
    the property were merely convenient rather than true -- a library module
    under `scripts/` that prints would mean the old prefix rule was hiding a
    real violation, not just an undeclared one.
    """
    scripts = _tracked_scripts()
    assert len(scripts) > 20, (
        f"only {len(scripts)} non-test scripts found -- the enumeration is broken "
        "and every assertion below is vacuous"
    )
    entry_points = {
        path for path in scripts if "\nif __name__ == \"__main__\":" in path.read_text(encoding="utf-8")
    }
    printing = {path for path in scripts if "print(" in path.read_text(encoding="utf-8")}
    assert printing, "no script prints -- the population under test is empty"
    assert printing <= entry_points, (
        "these library modules under scripts/ call print(), so the CLI-entry-point "
        "property does not describe the exempt set: "
        f"{sorted(str(p.relative_to(repo_root())) for p in printing - entry_points)}"
    )


_DOCSTRING_DECOY = '''"""A library module whose docstring shows usage, unindented:

if __name__ == "__main__":
    main()

...but this module has no entry point of its own.
"""


def emit(msg):
    print(msg)
'''


def test_a_docstring_that_mentions_the_guard_does_not_earn_the_exemption():
    """The predicate must parse, not match text (#16011's finding, inside its own fix).

    `grep -E '^if __name__ == .__main__.:'` reads raw text, so this module -- a
    library with the guard only in its docstring at column zero -- read as a
    standalone entry point, became exempt, and had its real `print()` call go
    unscanned. A line-oriented scanner cannot see that a line is inside a string,
    which is the same blindness the PR body cited about a different guard.

    The contrast is the other test above: a genuine entry point must still be
    exempt. A predicate that answers "no" to everything passes this test alone
    and reinstates the violation the exemption exists to avoid.
    """
    with _with_probe("_probe_16008_decoy.py", _DOCSTRING_DECOY):
        result = _run_hook("scripts/_probe_16008_decoy.py")
        assert "VIOLATION" in result.stdout, (
            "a module whose docstring merely mentions the __main__ guard was "
            f"exempted, so its real print() call was never scanned:\n{result.stdout}"
        )
