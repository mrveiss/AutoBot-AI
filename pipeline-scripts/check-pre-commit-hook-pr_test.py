# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pipeline-scripts/check-pre-commit-hook-pr.sh (#6785).

Confirms the generic CI wrapper:

1. Routes the right hook based on argv[1].
2. Skips cleanly when no source files changed.
3. Forwards an explicit file list to the hook in argv mode (so the hook's
   allowlist is the only filter that matters).
4. Surfaces hook exit codes (1 = violation, 0 = clean).

Each test creates a tmp git repo, sets up a synthetic PR commit, and runs
the wrapper with BASE_SHA/HEAD_SHA pointing at it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "pipeline-scripts" / "check-pre-commit-hook-pr.sh"
NO_PRINT_CONSOLE_HOOK = (
    REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "hooks" / "pre-commit-no-print-console"
)


def _make_pr(tmp_path: Path, files: dict[str, str]) -> tuple[str, str]:
    """Create a tmp git repo with one base commit + one 'PR' commit.

    Returns (base_sha, head_sha) suitable for BASE_SHA/HEAD_SHA env.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    # Empty base commit so we have something to diff against.
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "add", ".gitkeep"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"],
        cwd=tmp_path,
        check=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    # Add the PR's files in a second commit.
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pr"],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    # Hooks live at <REPO_ROOT>/autobot-infrastructure/...; tmp_path doesn't
    # have those, so we run the wrapper from the real REPO_ROOT and pass
    # the diff endpoints via env. The wrapper does `git diff` on cwd's repo;
    # to make that match tmp_path's diff, we cd to tmp_path AND point GIT_DIR.
    return base, head


def _run_wrapper(tmp_path: Path, hook_name: str, base: str, head: str) -> subprocess.CompletedProcess:
    """Run the wrapper inside ``tmp_path`` so its `git diff` finds the test repo."""
    return subprocess.run(
        ["bash", str(WRAPPER), hook_name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestArgvDispatch:
    """The wrapper's first arg picks which hook to run."""

    def test_unknown_hook_name_exits_2(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"a.py": "x = 1\n"})
        result = subprocess.run(
            ["bash", str(WRAPPER), "pre-commit-does-not-exist"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_missing_arg_exits_2(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["bash", str(WRAPPER)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "Usage" in result.stderr


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestNoChangedFiles:
    """Skip cleanly when the diff has no source files."""

    def test_no_relevant_files_exits_0(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"docs/notes.md": "# unrelated\n"})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode == 0
        assert "No changed source files" in result.stdout


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestUncomputableScopeFailsLoudly:
    """#13880 — an unresolvable ref must FAIL, never read as 'no changed files'.

    A shallow checkout leaves the PR base commit out of the clone. `git diff`
    then fatals, and the old `|| true` turned that into an empty file list —
    so four CI steps reported success having scanned nothing.
    """

    def test_missing_base_sha_exits_nonzero(self, tmp_path: Path) -> None:
        _, head = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        absent = "0" * 40  # well-formed but not in this repo, as in a shallow clone
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", absent, head)
        assert result.returncode != 0, result.stdout
        assert "does not resolve" in result.stderr
        # The dangerous outcome is the one that must NOT appear.
        assert "No changed source files" not in result.stdout

    def test_missing_head_sha_exits_nonzero(self, tmp_path: Path) -> None:
        base, _ = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        absent = "0" * 40
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, absent)
        assert result.returncode != 0
        assert "No changed source files" not in result.stdout

    def test_violation_is_still_caught_when_refs_resolve(self, tmp_path: Path) -> None:
        """The guard must not become so strict it stops catching real violations."""
        base, head = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode != 0
        assert "does not resolve" not in result.stderr


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestPathspecIsNotShellExpanded:
    """#13880 — the extension pathspec must reach git verbatim.

    As an unquoted string, the SHELL expanded `*.py` against the cwd first. In
    CI the cwd is the repo root, where `*.py` matched only root-level files, so
    the pathspec collapsed onto those and every nested change went unscanned.
    """

    def test_nested_violation_found_despite_root_level_decoy(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        # A root-level .py on disk is exactly what `*.py` used to collapse onto.
        # Untracked, so diffing it yields nothing — reproducing the CI shape.
        (tmp_path / "decoy.py").write_text("x = 1\n", encoding="utf-8")
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert "No changed source files" not in result.stdout, result.stdout
        assert result.returncode != 0, "nested violation must still be caught"

    @pytest.mark.parametrize("bad_ext", [".py", " py", "py!", "p y"])
    def test_malformed_ext_exits_2_rather_than_matching_nothing(self, tmp_path: Path, bad_ext: str) -> None:
        """A pathspec like `*..py` matches nothing and would read as 'clean'."""
        validator = tmp_path / "check_always_fail.py"
        validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext=bad_ext)
        assert result.returncode == 2, result.stdout
        assert "No changed source files" not in result.stdout


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestForwardsArgvToHooks:
    """End-to-end: wrapper passes argv to hooks correctly."""

    def test_no_print_console_blocks_print(self, tmp_path: Path) -> None:
        # Production .py with a print() call must trip the no-print hook
        base, head = _make_pr(tmp_path, {"src/worker.py": 'print("hi")\n'})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode != 0

    def test_no_print_console_allows_test_files(self, tmp_path: Path) -> None:
        # Test files are allowlisted by the hook's filter
        base, head = _make_pr(tmp_path, {"src/foo_test.py": 'print("hi")\n'})
        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)
        assert result.returncode == 0

    def test_no_direct_redis_blocks_bare_redis(self, tmp_path: Path) -> None:
        # `redis.Redis()` direct instantiation in production code
        base, head = _make_pr(tmp_path, {"src/r.py": "import redis\nclient = redis.Redis()\n"})
        result = _run_wrapper(tmp_path, "pre-commit-no-direct-redis", base, head)
        assert result.returncode != 0


def _run_wrapper_python(
    tmp_path: Path, validator: Path, base: str, head: str, ext: str = ""
) -> subprocess.CompletedProcess:
    """Run the wrapper in --python mode from tmp_path."""
    args = ["bash", str(WRAPPER), "--python", str(validator)]
    if ext:
        args += ["--ext", ext]
    return subprocess.run(
        args,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestPythonValidatorMode:
    """--python flag: routes to a Python validator instead of a bash hook."""

    def test_missing_validator_exits_2(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"a.py": "x = 1\n"})
        result = subprocess.run(
            ["bash", str(WRAPPER), "--python", "tools/lint/nonexistent.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 2
        assert "not found" in result.stderr.lower()

    def test_no_changed_py_files_skips(self, tmp_path: Path) -> None:
        # Write a dummy validator that always exits 1
        validator = tmp_path / "check_always_fail.py"
        validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"docs/README.md": "# docs\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode == 0
        assert "No changed source files" in result.stdout

    def test_python_validator_exit_code_propagated(self, tmp_path: Path) -> None:
        # A validator that exits 1 must cause the wrapper to exit non-zero
        validator = tmp_path / "check_always_fail.py"
        validator.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode != 0

    def test_python_validator_clean_exit_0(self, tmp_path: Path) -> None:
        # A validator that exits 0 (clean) passes
        validator = tmp_path / "check_always_pass.py"
        validator.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})
        result = _run_wrapper_python(tmp_path, validator, base, head, ext="py")
        assert result.returncode == 0


def _amend_pr(tmp_path: Path, files: dict[str, str]) -> tuple[str, str]:
    """A repo whose BASE already contains *files*, and whose PR edits one line.

    The point of #13950 is the distinction between "in a file this PR touched"
    and "on a line this PR added", so the fixture has to be able to express it:
    the base carries pre-existing content and the PR appends to it.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    return base, ""


def _commit_pr(tmp_path: Path) -> str:
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "pr"], cwd=tmp_path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


def _run_scoped(tmp_path: Path, hook_name: str, base: str, head: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(WRAPPER), "--changed-lines-only", hook_name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


# A violation the hardcoded-values hook reliably reports: a bare port literal.
_OFFENDING = '    URL = "http://127.0.0.1:8001/api/health"\n'
_CLEAN = "    VALUE = compute()\n"


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestChangedLinesOnly:
    """#13950: a PR answers for the lines it added, not for the file it touched."""

    def test_a_pre_existing_violation_in_a_touched_file_does_not_fail(self, tmp_path: Path) -> None:
        """The reported symptom: four PRs red on other commits' violations."""
        base, _ = _amend_pr(tmp_path, {"m.py": "def f():\n" + _OFFENDING})
        (tmp_path / "m.py").write_text("def f():\n" + _OFFENDING + _CLEAN, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-hardcoded-values", base, head)

        assert result.returncode == 0, f"pre-existing violation failed the build:\n{result.stdout}"
        assert "did not touch" in result.stdout, "the suppressed violation was hidden rather than reported"

    def test_a_violation_the_pr_adds_still_fails(self, tmp_path: Path) -> None:
        """The property that must survive: this is a scope change, not an off switch.

        Without this, the whole change is indistinguishable from deleting the
        guard — which is exactly how a loosened check stops catching anything.
        """
        base, _ = _amend_pr(tmp_path, {"m.py": "def f():\n" + _CLEAN})
        (tmp_path / "m.py").write_text("def f():\n" + _CLEAN + _OFFENDING, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-hardcoded-values", base, head)

        assert result.returncode == 1, f"a newly added violation passed:\n{result.stdout}"
        assert "lines this PR added" in result.stdout

    def test_a_clean_pr_stays_clean(self, tmp_path: Path) -> None:
        base, _ = _amend_pr(tmp_path, {"m.py": "def f():\n" + _CLEAN})
        (tmp_path / "m.py").write_text("def f():\n" + _CLEAN + "    OTHER = g()\n", encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-hardcoded-values", base, head)

        assert result.returncode == 0

    def test_the_default_mode_is_unchanged(self, tmp_path: Path) -> None:
        """Without the flag, a pre-existing violation still fails.

        The flag is opt-in precisely so every other hook keeps its behaviour;
        if the default changed too, the blast radius would be every guard that
        runs through this wrapper.
        """
        base, _ = _amend_pr(tmp_path, {"m.py": "def f():\n" + _OFFENDING})
        (tmp_path / "m.py").write_text("def f():\n" + _OFFENDING + _CLEAN, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_wrapper(tmp_path, "pre-commit-hardcoded-values", base, head)

        assert result.returncode == 1


# #14051: a multi-line print()/console.*() call's suppression comment can sit
# on the closing-paren line, several lines below where the guard matches.
_MULTILINE_NOQA_OPEN = (
    "def f():\n"
    "    print(  # noqa: print\n"
    '        "a long message that lives on its own line inside the call"\n'
    "    )\n"
)
_MULTILINE_NOQA_CLOSE = (
    "def f():\n"
    "    print(\n"
    '        "a long message that lives on its own line inside the call"\n'
    "    )  # noqa: print\n"
)
_MULTILINE_NO_NOQA = (
    "def f():\n" "    print(\n" '        "a long message that lives on its own line inside the call"\n' "    )\n"
)
_SINGLELINE_NO_NOQA = 'print("still a violation")\n'


def _run_hook(tmp_path: Path, filename: str) -> subprocess.CompletedProcess:
    """Invoke the hook directly (argv mode) with a RELATIVE filename, cwd=tmp_path."""
    return subprocess.run(["bash", str(NO_PRINT_CONSOLE_HOOK), filename], cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.skipif(not NO_PRINT_CONSOLE_HOOK.exists(), reason="hook script not found")
class TestMultilineNoqaRecognition:
    """The hook's own multi-line scan (#14051), invoked directly (argv mode).

    Independent of --changed-lines-only: this is about the hook understanding
    a suppression that isn't on the line it matched on, whole-file or scoped.
    """

    # Filenames passed as RELATIVE paths, cwd=tmp_path: the hook's own
    # `test_.*\.py$` exclusion matches anywhere in the string it is given, and
    # pytest's own tmp_path is named e.g. "test_noqa_on_opening_line0" — an
    # absolute path would silently fall into that exclusion and report exit 0
    # for "filtered out as a test file", indistinguishable from "recognised".
    # Caught by the mutation check (#14051 workflow step 7): two tests here
    # first passed with the fix REMOVED, because they were filtered, not
    # exercised.

    def test_noqa_on_opening_line_is_recognised(self, tmp_path: Path) -> None:
        """A REGRESSION guard, not forward-scan coverage: this shape is caught
        by the pre-existing same-line check, and passes even with the
        forward scan disabled entirely. See
        test_noqa_on_closing_paren_line_is_recognised for a case that
        actually exercises the scan."""
        (tmp_path / "m.py").write_text(_MULTILINE_NOQA_OPEN, encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 0, result.stdout
        assert "No production files staged" not in result.stdout, "file was filtered, not scanned"

    def test_noqa_on_closing_paren_line_is_recognised(self, tmp_path: Path) -> None:
        """The exact shape from PR #14046: the comment sat on the `)` line.
        Genuinely exercises the forward scan — the opening line carries no
        noqa at all."""
        (tmp_path / "m.py").write_text(_MULTILINE_NOQA_CLOSE, encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 0, result.stdout
        assert "No production files staged" not in result.stdout, "file was filtered, not scanned"

    def test_multiline_call_with_no_noqa_anywhere_still_fails(self, tmp_path: Path) -> None:
        """The scan must not become so permissive it stops catching real calls."""
        (tmp_path / "m.py").write_text(_MULTILINE_NO_NOQA, encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout

    def test_singleline_call_with_no_noqa_still_fails(self, tmp_path: Path) -> None:
        """Regression guard: the single-line path must be untouched by the scan."""
        (tmp_path / "m.py").write_text(_SINGLELINE_NO_NOQA, encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout

    def test_multiline_console_noqa_on_closing_line_is_recognised(self, tmp_path: Path) -> None:
        """Same gap, TypeScript side: `console.*(` can wrap across lines too."""
        (tmp_path / "m.ts").write_text(
            "function f() {\n"
            "  console.log(\n"
            '    "a long message that lives on its own line inside the call"\n'
            "  );  // noqa: console\n"
            "}\n",
            encoding="utf-8",
        )
        result = _run_hook(tmp_path, "m.ts")
        assert result.returncode == 0, result.stdout
        assert "No production files staged" not in result.stdout, "file was filtered, not scanned"


@pytest.mark.skipif(not NO_PRINT_CONSOLE_HOOK.exists(), reason="hook script not found")
class TestMultilineScanDoesNotOverreach:
    """#14051 code review round 2 (PR #14112): the forward scan seeded its
    paren balance from a STRIPPED first line but then read RAW candidate
    lines. Wherever raw parens diverged from real syntax — a trailing
    comment's stray '(', a regex literal, a noqa-shaped string of characters
    inside a string ARGUMENT — the window stayed open past the real closing
    paren and could accept an unrelated noqa or hide a live violation. Every
    case here failed (exit 0 — wrongly suppressed) against the hook at
    63e957e2d and must fail (exit 1) here.
    """

    def test_unrelated_noqa_below_does_not_suppress_backtick_call(self, tmp_path: Path) -> None:
        """A template literal's stray '(' held the scan window open long
        enough to reach an unrelated noqa 19 lines down."""
        lines = ["console.log(`fetching (${url}`);"] + [f"const a{i} = {i};" for i in range(18)]
        lines.append('console.warn("x");  // noqa: console')
        (tmp_path / "m.ts").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _run_hook(tmp_path, "m.ts")
        assert result.returncode == 1, result.stdout

    def test_unrelated_noqa_below_does_not_suppress_regex_literal_call(self, tmp_path: Path) -> None:
        """A regex literal's parenthesis character is not call structure."""
        (tmp_path / "m.ts").write_text(
            'console.log(str.replace(/\\(/g, ""));\nconst a = 1;\nconsole.warn("x");  // noqa: console\n',
            encoding="utf-8",
        )
        result = _run_hook(tmp_path, "m.ts")
        assert result.returncode == 1, result.stdout

    def test_noqa_substring_inside_ts_string_does_not_suppress(self, tmp_path: Path) -> None:
        """A noqa MENTIONED in a string argument, on a line the forward scan
        visits WHILE the call is still open, must not suppress it. A fake
        noqa on a line that never enters the scan window (e.g. because the
        call already closed, or a standalone line elsewhere) proves nothing
        about this bug — it has to be a live forward-scan candidate."""
        (tmp_path / "m.ts").write_text(
            'console.log(\n  "a message",\n  "write // noqa: console to skip"\n);\n',
            encoding="utf-8",
        )
        result = _run_hook(tmp_path, "m.ts")
        assert result.returncode == 1, result.stdout

    def test_noqa_inside_python_string_argument_does_not_suppress(self, tmp_path: Path) -> None:
        """The exact shape the hook's own quick-fix message prints:
        'add # noqa to suppress this rule' — as a STRING, not a comment."""
        (tmp_path / "m.py").write_text('print(\n    "add # noqa to suppress this rule",\n)\n', encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout

    def test_trailing_comment_paren_does_not_open_scan_window(self, tmp_path: Path) -> None:
        """A single-line call's own trailing comment must not be misread as
        leaving the call open, reaching a `# noqa` on the next line down."""
        (tmp_path / "m.py").write_text("print(x)  # emit the value (verbose mode\ny = g()  # noqa\n", encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout

    def test_escaped_quote_does_not_defeat_the_strip(self, tmp_path: Path) -> None:
        (tmp_path / "m.py").write_text('print("say \\" ( hi")\ny = g()  # noqa\n', encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout

    def test_scan_bound_fails_closed(self, tmp_path: Path) -> None:
        """A call that never resolves within the bound must still fail, not
        read as suppressed just because the window ran out."""
        lines = ["print("] + [f"    arg{i}," for i in range(25)] + [")  # noqa: print"]
        (tmp_path / "m.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _run_hook(tmp_path, "m.py")
        assert result.returncode == 1, result.stdout


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestChangedLinesOnlyPrintConsole:
    """#14051 fix (2): the same --changed-lines-only scoping #13950 gave the
    hardcoded-values guard, applied to pre-commit-no-print-console.

    This is what actually made autobot-backend/cli/doctor.py editable again:
    PR #14046 changed a function signature, added zero prints, and still hit
    three violations because the file had pre-existing (suppressed, but
    invisible to the unscoped guard) print() calls elsewhere in it.
    """

    def test_a_pre_existing_violation_in_a_touched_file_does_not_fail(self, tmp_path: Path) -> None:
        base, _ = _amend_pr(tmp_path, {"m.py": _SINGLELINE_NO_NOQA})
        (tmp_path / "m.py").write_text(_SINGLELINE_NO_NOQA + "x = 1\n", encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 0, f"pre-existing violation failed the build:\n{result.stdout}"
        assert "did not touch" in result.stdout

    def test_a_violation_the_pr_adds_still_fails(self, tmp_path: Path) -> None:
        """The property that must survive: this is a scope change, not an off switch."""
        base, _ = _amend_pr(tmp_path, {"m.py": "x = 1\n"})
        (tmp_path / "m.py").write_text("x = 1\n" + _SINGLELINE_NO_NOQA, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 1, f"a newly added violation passed:\n{result.stdout}"
        assert "lines this PR added" in result.stdout

    def test_a_newly_added_multiline_violation_still_fails(self, tmp_path: Path) -> None:
        """Combines both #14051 fixes: scoping must not let a NEW multi-line,
        unsuppressed call slip through just because it spans several lines."""
        base, _ = _amend_pr(tmp_path, {"m.py": "x = 1\n"})
        (tmp_path / "m.py").write_text("x = 1\n" + _MULTILINE_NO_NOQA, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 1, f"a newly added multi-line violation passed:\n{result.stdout}"

    def test_a_newly_added_multiline_call_with_noqa_on_closing_line_passes(self, tmp_path: Path) -> None:
        """The PR #14046 shape, reproduced end-to-end through the CI wrapper."""
        base, _ = _amend_pr(tmp_path, {"m.py": "x = 1\n"})
        (tmp_path / "m.py").write_text("x = 1\n" + _MULTILINE_NOQA_CLOSE, encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 0, result.stdout

    def test_a_clean_pr_stays_clean(self, tmp_path: Path) -> None:
        base, _ = _amend_pr(tmp_path, {"m.py": "x = 1\n"})
        (tmp_path / "m.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 0

    def test_the_default_mode_is_unchanged(self, tmp_path: Path) -> None:
        """Without the flag, a pre-existing violation still fails whole-file."""
        base, _ = _amend_pr(tmp_path, {"m.py": _SINGLELINE_NO_NOQA})
        (tmp_path / "m.py").write_text(_SINGLELINE_NO_NOQA + "x = 1\n", encoding="utf-8")
        head = _commit_pr(tmp_path)

        result = _run_wrapper(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 1

    def test_deleting_a_closing_line_noqa_is_still_caught(self, tmp_path: Path) -> None:
        """#14051 review round 2, finding 4: fix (1) lets a suppression live
        on the CLOSING line; fix (2) scopes CI by the REPORTED line, which
        the guard always put on the OPENING line. Combined, deleting a
        closing-line noqa touched only that line — the diff hunk never
        touches the opening line the guard reports at — so the scoped
        wrapper read it as untouched and passed. The hook now reports a line
        RANGE for multi-line violations so this diff hunk falls inside it."""
        base, _ = _amend_pr(tmp_path, {"m.py": _MULTILINE_NOQA_CLOSE})
        (tmp_path / "m.py").write_text(_MULTILINE_NO_NOQA, encoding="utf-8")
        head = _commit_pr(tmp_path)

        # Confirm the diff really is closing-line-only, or this test proves nothing.
        diff = subprocess.run(
            ["git", "diff", base, head, "--", "m.py"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout
        removed = [ln for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
        added = [ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        assert removed == ["-    )  # noqa: print"], f"expected exactly one removed (noqa) line:\n{diff}"
        assert added == ["+    )"], f"expected exactly one added line:\n{diff}"

        result = _run_scoped(tmp_path, "pre-commit-no-print-console", base, head)

        assert result.returncode == 1, f"deleting a closing-line noqa was not caught:\n{result.stdout}"
